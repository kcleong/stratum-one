"""Ties gpsd, chrony and host stats together and keeps the history (in memory, batched to SQLite)."""

import asyncio
import logging
import sqlite3
import time
from collections import Counter, deque

from . import system
from .chrony import ChronycError, ChronyMonitor
from .config import Settings
from .geo import GeoLookup
from .gpsd import GpsdClient
from .models import Burst, HistoryPoint, HistorySample, Provider, Status
from .pool import PoolMonitor
from .sky import SAMPLE_S as SKY_SAMPLE_S, SkyCounter
from .store import HistoryStore, bucket_samples

log = logging.getLogger(__name__)

MAX_POINTS = 1500
BUCKETS_S = (30, 60, 120, 300, 600, 900, 1800, 3600, 7200)
TOP_PROVIDERS = 10
BURST_WINDOW_S = 60        # burst scans: clients with a request this recent
BURST_FIRST_SCAN_S = 15    # let per-client counters build up before the first scan
BURST_RESCAN_S = 60
BURSTS_KEPT = 50           # in memory, newest; the store keeps HISTORY_DAYS


class Monitor:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.gps = GpsdClient(settings.gpsd_host, settings.gpsd_port)
        self.chrony = ChronyMonitor()
        self.geo = GeoLookup(settings.geoip_dir) if settings.geoip_dir else None
        self.providers: list[Provider] = []   # top networks of active public clients; needs geo
        maxlen = int(settings.history_hours * 3600 / settings.chrony_interval)
        self.history: deque[HistorySample] = deque(maxlen=maxlen)
        self._unsaved: list[HistorySample] = []
        self._flush_lock = asyncio.Lock()
        # Finished (fully flushed) buckets never change: bucket size -> {bucket index: point}.
        self._bucket_cache: dict[float, dict[int, HistoryPoint]] = {}
        self.store: HistoryStore | None = None
        if settings.history_db:
            try:
                self.store = HistoryStore(settings.history_db, settings.history_days * 86400)
                self.history.extend(self.store.load(time.time() - settings.history_hours * 3600))
                log.info("loaded %d history samples from %s", len(self.history), settings.history_db)
            except (sqlite3.Error, OSError) as e:
                log.error("history store %s unusable, keeping history in memory only: %s", settings.history_db, e)
                self.store = None
        self.pool = (
            PoolMonitor(settings.pool_servers, settings.pool_interval, settings.pool_url,
                        settings.history_days * 86400, self.store)
            if settings.pool_servers else None
        )
        self.sky = SkyCounter(settings.sky_hours)
        self.bursts: deque[Burst] = deque(maxlen=BURSTS_KEPT)
        self._burst_task: asyncio.Task | None = None
        if self.store is not None:
            try:
                self.bursts.extend(self.store.load_bursts(time.time() - settings.history_days * 86400))
            except sqlite3.Error as e:
                log.warning("traffic bursts unreadable from history store: %s", e)
        if self.store is not None:
            try:
                self.sky.load(self.store.load_sky(self._sky_first_hour()))
            except sqlite3.Error as e:
                log.warning("sky coverage unreadable from history store: %s", e)

    def _sky_first_hour(self) -> int:
        return int(time.time() // 3600) - int(self.settings.sky_hours) + 1

    async def run_sky(self) -> None:
        while True:
            gps = self.gps.snapshot()
            if gps.connected:
                self.sky.add(gps.satellites)
            await asyncio.sleep(SKY_SAMPLE_S)

    async def run_chrony(self) -> None:
        while True:
            started = time.monotonic()
            await self.chrony.poll()
            self._record()
            self._check_burst()
            await asyncio.sleep(max(0.0, self.settings.chrony_interval - (time.monotonic() - started)))

    async def run_clients(self) -> None:
        while True:
            await self.chrony.poll_clients()
            if self.geo is not None:
                self.chrony.clients = [
                    c.model_copy(update=dict(zip(("country", "asn", "asn_org"), self.geo.lookup(c.address))))
                    for c in self.chrony.clients
                ]
                # One lookup per active client; off the event loop on a busy pool server.
                self.providers = await asyncio.to_thread(self._top_providers, self.chrony.active_public)
            await asyncio.sleep(self.settings.clients_interval)

    def _check_burst(self) -> None:
        rate = self.chrony.ntp_requests_per_s
        threshold = self.settings.burst_req_s
        if threshold <= 0 or rate is None or rate < threshold:
            return
        if self._burst_task is None or self._burst_task.done():
            self._burst_task = asyncio.create_task(self._watch_burst())

    async def _watch_burst(self) -> None:
        """Follow one burst until the load falls below half the threshold, rescanning its clients."""
        threshold = self.settings.burst_req_s
        stats = self.chrony.serverstats
        rx0, drop0 = (stats.ntp_packets_received, stats.ntp_packets_dropped) if stats else (None, None)
        burst = Burst(
            start=round(time.time(), 1), end=None, peak_req_s=self.chrony.ntp_requests_per_s or 0.0,
            ntp_packets=0, ntp_dropped=0, scanned=None, window_s=BURST_WINDOW_S,
            clients=0, clients_ipv6=0, top_clients=[], prefixes=[], providers=[],
        )
        log.warning("traffic burst: %.0f NTP requests/s", burst.peak_req_s)
        self.bursts.append(burst)
        next_scan = time.monotonic() + BURST_FIRST_SCAN_S
        while True:
            await asyncio.sleep(self.settings.chrony_interval)
            rate = self.chrony.ntp_requests_per_s
            ended = rate is not None and rate < threshold / 2
            update: dict = {"peak_req_s": max(burst.peak_req_s, rate or 0.0)}
            stats = self.chrony.serverstats
            if stats and rx0 is not None and stats.ntp_packets_received >= rx0:
                update |= {"ntp_packets": stats.ntp_packets_received - rx0, "ntp_dropped": stats.ntp_packets_dropped - drop0}
            if not ended and time.monotonic() >= next_scan:
                next_scan = time.monotonic() + BURST_RESCAN_S
                update |= await self._scan_burst()
            if ended:
                update["end"] = round(time.time(), 1)
            burst = burst.model_copy(update=update)
            self.bursts[-1] = burst
            await self._save_burst(burst)
            if ended:
                log.warning("traffic burst over: %d requests, %d dropped, %d clients", burst.ntp_packets, burst.ntp_dropped, burst.clients)
                return

    async def _scan_burst(self) -> dict:
        try:
            count, count_v6, top, prefixes, recent = await self.chrony.scan_recent(BURST_WINDOW_S)
        except (ChronycError, IndexError, ValueError) as e:
            log.warning("traffic burst client scan: %s", e)
            return {}
        if self.geo is not None:
            top = [c.model_copy(update=dict(zip(("country", "asn", "asn_org"), self.geo.lookup(c.address)))) for c in top]
        providers = await asyncio.to_thread(self._top_providers, recent) if self.geo is not None else []
        return dict(scanned=round(time.time(), 1), clients=count, clients_ipv6=count_v6,
                    top_clients=top, prefixes=prefixes, providers=providers)

    async def _save_burst(self, burst: Burst) -> None:
        if self.store is None:
            return
        try:
            await asyncio.to_thread(self.store.write_burst, burst)
        except sqlite3.Error as e:
            log.warning("traffic burst not saved: %s", e)

    def _top_providers(self, active: list[tuple[str, int]]) -> list[Provider]:
        by_asn: dict[int | None, list] = {}   # asn -> [org, clients, packets, Counter of countries]
        for address, packets in active:
            country, asn, org = self.geo.lookup(address)
            entry = by_asn.setdefault(asn, [org, 0, 0, Counter()])
            entry[1] += 1
            entry[2] += packets
            entry[3][country] += 1
        top = sorted(by_asn.items(), key=lambda kv: (kv[1][1], kv[1][2]), reverse=True)[:TOP_PROVIDERS]
        return [
            # An AS can span countries: show where most of its clients are.
            Provider(asn=asn, asn_org=org, country=countries.most_common(1)[0][0], clients=n, ntp_packets=p)
            for asn, (org, n, p, countries) in top
        ]

    async def run_flush(self) -> None:
        while True:
            await asyncio.sleep(self.settings.history_flush_minutes * 60)
            await self.flush()

    async def flush(self) -> None:
        """Write unsaved samples in one transaction (off the event loop)."""
        if self.store is None:
            return
        async with self._flush_lock:
            batch, self._unsaved = self._unsaved, []
            if batch:
                try:
                    await asyncio.to_thread(self.store.write, batch)
                    log.debug("flushed %d history samples", len(batch))
                except sqlite3.Error as e:
                    log.warning("history flush failed, will retry: %s", e)
                    self._unsaved = batch + self._unsaved
            hours, self.sky.dirty = self.sky.dirty, set()
            if hours:
                try:
                    await asyncio.to_thread(self.store.write_sky, self.sky.rows(hours), self._sky_first_hour())
                except sqlite3.Error as e:
                    log.warning("sky coverage flush failed, will retry: %s", e)
                    self.sky.dirty |= hours

    def close(self) -> None:
        if self.store is not None:
            self.store.close()

    def _record(self) -> None:
        tracking = self.chrony.tracking
        if tracking is None:
            return
        pps = self.chrony.pps_source
        gps = self.gps.snapshot()
        sample = HistorySample(
            t=round(time.time(), 1),
            system_time_offset_s=tracking.system_time_offset_s,
            last_offset_s=tracking.last_offset_s,
            rms_offset_s=tracking.rms_offset_s,
            frequency_ppm=tracking.frequency_ppm,
            skew_ppm=tracking.skew_ppm,
            pps_offset_s=pps.offset_s if pps else None,
            satellites_used=gps.satellites_used,
            satellites_visible=gps.satellites_visible,
            cpu_temp_c=system.snapshot().cpu_temp_c,
            ntp_requests_per_s=self.chrony.ntp_requests_per_s,
            ntp_dropped_per_s=self.chrony.ntp_dropped_per_s,
        )
        self.history.append(sample)
        if self.store is not None:
            self._unsaved.append(sample)

    def history_since(self, seconds: float) -> list[HistorySample]:
        cutoff = time.time() - seconds
        return [s for s in self.history if s.t >= cutoff]

    @property
    def memory_window_s(self) -> float:
        return self.settings.history_hours * 3600

    async def history_buckets(self, seconds: float) -> tuple[float, list[HistoryPoint]]:
        """Bucket averages over the last `seconds` from SQLite plus unflushed samples."""
        bucket = next((b for b in BUCKETS_S if seconds / b <= MAX_POINTS), BUCKETS_S[-1])
        since = time.time() - seconds
        if self.store is None:
            return bucket, bucket_samples(self.history_since(seconds), bucket)
        cache = self._bucket_cache.setdefault(bucket, {})
        # Hold the flush lock so a batch in flight is either in the DB or still unsaved.
        async with self._flush_lock:
            first_unsaved = self._unsaved[0].t if self._unsaved else time.time()
            done = int(first_unsaved // bucket)   # buckets before this one are fully in the DB
            first = int(since // bucket)
            # Query only what isn't cached, unless this range reaches further back than the cache.
            start = first if not cache or min(cache) > first else max(cache) + 1
            if start < done:
                for point in await asyncio.to_thread(self.store.buckets, start * bucket, done * bucket, bucket):
                    cache[int(point.t // bucket)] = point
        expired = int((time.time() - self.settings.history_days * 86400) // bucket)
        for k in [k for k in cache if k < expired]:
            del cache[k]
        # Unfinished buckets come from the in-memory raw samples (the last 24 h), flushed or not.
        tail_start = max(since, done * bucket)
        tail = bucket_samples([s for s in self.history if s.t >= tail_start], bucket)
        return bucket, [p for k, p in sorted(cache.items()) if first <= k < done] + tail

    def snapshot(self) -> Status:
        return Status(
            time=time.time(),
            gps=self.gps.snapshot(),
            chrony=self.chrony.snapshot(),
            system=system.snapshot(),
        )

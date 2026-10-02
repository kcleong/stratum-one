"""Ties gpsd, chrony and host stats together and keeps the history (in memory, batched to SQLite)."""

import asyncio
import logging
import sqlite3
import time
from collections import deque

from . import system
from .chrony import ChronyMonitor
from .config import Settings
from .geo import GeoLookup
from .gpsd import GpsdClient
from .models import HistoryPoint, HistorySample, Status
from .store import HistoryStore, bucket_samples

log = logging.getLogger(__name__)

MAX_POINTS = 1500
BUCKETS_S = (30, 60, 120, 300, 600, 900, 1800, 3600, 7200)


class Monitor:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.gps = GpsdClient(settings.gpsd_host, settings.gpsd_port)
        self.chrony = ChronyMonitor()
        self.geo = GeoLookup(settings.geoip_dir) if settings.geoip_dir else None
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

    async def run_chrony(self) -> None:
        while True:
            started = time.monotonic()
            await self.chrony.poll()
            self._record()
            await asyncio.sleep(max(0.0, self.settings.chrony_interval - (time.monotonic() - started)))

    async def run_clients(self) -> None:
        while True:
            await self.chrony.poll_clients()
            if self.geo is not None:
                self.chrony.clients = [
                    c.model_copy(update=dict(zip(("country", "asn", "asn_org"), self.geo.lookup(c.address))))
                    for c in self.chrony.clients
                ]
            await asyncio.sleep(self.settings.clients_interval)

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
            if not batch:
                return
            try:
                await asyncio.to_thread(self.store.write, batch)
                log.debug("flushed %d history samples", len(batch))
            except sqlite3.Error as e:
                log.warning("history flush failed, will retry: %s", e)
                self._unsaved = batch + self._unsaved

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

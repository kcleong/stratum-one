"""Ties gpsd, chrony and host stats together and keeps the history (in memory, batched to SQLite)."""

import asyncio
import logging
import sqlite3
import time
from collections import deque

from . import system
from .chrony import ChronyMonitor
from .config import Settings
from .gpsd import GpsdClient
from .models import HistorySample, Status
from .store import HistoryStore

log = logging.getLogger(__name__)


class Monitor:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.gps = GpsdClient(settings.gpsd_host, settings.gpsd_port)
        self.chrony = ChronyMonitor()
        maxlen = int(settings.history_hours * 3600 / settings.chrony_interval)
        self.history: deque[HistorySample] = deque(maxlen=maxlen)
        self._unsaved: list[HistorySample] = []
        self._flush_lock = asyncio.Lock()
        self.store: HistoryStore | None = None
        if settings.history_db:
            try:
                self.store = HistoryStore(settings.history_db, settings.history_hours * 3600)
                self.history.extend(self.store.load())
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

    def snapshot(self) -> Status:
        return Status(
            time=time.time(),
            gps=self.gps.snapshot(),
            chrony=self.chrony.snapshot(),
            system=system.snapshot(),
        )

"""Ties gpsd, chrony and host stats together and keeps an in-memory history."""

import asyncio
import logging
import time
from collections import deque

from . import system
from .chrony import ChronyMonitor
from .config import Settings
from .gpsd import GpsdClient

log = logging.getLogger(__name__)


class Monitor:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.gps = GpsdClient(settings.gpsd_host, settings.gpsd_port)
        self.chrony = ChronyMonitor()
        maxlen = int(settings.history_hours * 3600 / settings.chrony_interval)
        self.history: deque[dict] = deque(maxlen=maxlen)

    async def run_chrony(self) -> None:
        while True:
            started = time.monotonic()
            await self.chrony.poll()
            self._record()
            await asyncio.sleep(max(0.0, self.settings.chrony_interval - (time.monotonic() - started)))

    def _record(self) -> None:
        tracking = self.chrony.tracking
        if tracking is None:
            return
        pps = next((s for s in self.chrony.sources if s["mode"] == "refclock" and s["name"] == "PPS"), None)
        gps = self.gps.snapshot()
        self.history.append({
            "t": round(time.time(), 1),
            "system_time_offset_s": tracking["system_time_offset_s"],
            "last_offset_s": tracking["last_offset_s"],
            "rms_offset_s": tracking["rms_offset_s"],
            "frequency_ppm": tracking["frequency_ppm"],
            "skew_ppm": tracking["skew_ppm"],
            "pps_offset_s": pps["offset_s"] if pps else None,
            "satellites_used": gps["satellites_used"],
            "satellites_visible": gps["satellites_visible"],
            "cpu_temp_c": system.snapshot()["cpu_temp_c"],
        })

    def history_since(self, seconds: float) -> list[dict]:
        cutoff = time.time() - seconds
        return [s for s in self.history if s["t"] >= cutoff]

    def snapshot(self) -> dict:
        return {
            "time": time.time(),
            "gps": self.gps.snapshot(),
            "chrony": self.chrony.snapshot(),
            "system": system.snapshot(),
        }

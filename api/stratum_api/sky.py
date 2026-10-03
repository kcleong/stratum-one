"""Sky coverage: signal strength per patch of sky over the last SKY_HOURS.

Every SAMPLE_S the satellites gpsd reports are binned by azimuth and elevation
(AZ_STEP x EL_STEP degrees). A satellite gpsd lists with SNR 0 is predicted to
be there but not received, so patches that stay at 0 are blocked by walls,
roofs or neighbours. Counts are kept per hour, so the window slides by the
hour and survives restarts through the history store.
"""

import time

from .models import Satellite, SkyCell, SkyCoverage

AZ_STEP = 10
EL_STEP = 10
SAMPLE_S = 30.0


class SkyCounter:
    def __init__(self, hours: float):
        self.hours = hours
        # hour index -> (az, el) bin -> [samples, received, snr_sum, snr_max]
        self.buckets: dict[int, dict[tuple[int, int], list[float]]] = {}
        self.dirty: set[int] = set()   # hours changed since the last save

    def add(self, satellites: list[Satellite], now: float | None = None) -> None:
        now = now or time.time()
        # One entry per satellite: gpsd can list a satellite once per signal; keep the strongest.
        best: dict[tuple[str, int | None], Satellite] = {}
        for s in satellites:
            if s.azimuth is None or s.elevation is None or s.elevation < 0:
                continue
            key = (s.gnss, s.svid if s.svid is not None else s.prn)
            if key not in best or (s.snr or 0) > (best[key].snr or 0):
                best[key] = s
        if not best:
            return
        hour = int(now // 3600)
        bucket = self.buckets.setdefault(hour, {})
        for s in best.values():
            cell = bucket.setdefault(_bin(s.azimuth, s.elevation), [0, 0, 0.0, 0.0])
            cell[0] += 1
            if s.snr:
                cell[1] += 1
                cell[2] += s.snr
                cell[3] = max(cell[3], s.snr)
        self.dirty.add(hour)
        for h in [h for h in self.buckets if h <= hour - self.hours]:
            del self.buckets[h]

    def load(self, rows: list[tuple[int, int, int, int, int, float, float]]) -> None:
        for hour, az, el, n, n_rx, snr_sum, snr_max in rows:
            self.buckets.setdefault(hour, {})[(az, el)] = [n, n_rx, snr_sum, snr_max]

    def rows(self, hours: set[int]) -> list[tuple[int, int, int, int, int, float, float]]:
        return [
            (hour, az, el, n, n_rx, snr_sum, snr_max)
            for hour in hours if hour in self.buckets
            for (az, el), (n, n_rx, snr_sum, snr_max) in self.buckets[hour].items()
        ]

    def coverage(self) -> SkyCoverage:
        totals: dict[tuple[int, int], list[float]] = {}
        for bucket in self.buckets.values():
            for cell, (n, n_rx, snr_sum, snr_max) in bucket.items():
                t = totals.setdefault(cell, [0, 0, 0.0, 0.0])
                t[0] += n
                t[1] += n_rx
                t[2] += snr_sum
                t[3] = max(t[3], snr_max)
        return SkyCoverage(
            hours=self.hours,
            az_step=AZ_STEP,
            el_step=EL_STEP,
            sample_interval_s=SAMPLE_S,
            since=min(self.buckets) * 3600 if self.buckets else None,
            cells=[
                SkyCell(
                    az=az, el=el, samples=int(n), received=int(n_rx),
                    mean_snr=round(snr_sum / n_rx, 1) if n_rx else None,
                    max_snr=snr_max if n_rx else None,
                )
                for (az, el), (n, n_rx, snr_sum, snr_max) in sorted(totals.items())
            ],
        )


def _bin(azimuth: float, elevation: float) -> tuple[int, int]:
    az = int(azimuth // AZ_STEP) * AZ_STEP % 360
    el = min(int(elevation // EL_STEP) * EL_STEP, 90 - EL_STEP)
    return az, el

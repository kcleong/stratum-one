"""SQLite persistence for the history ring, written in batches to spare the SD card.

Samples are buffered in memory and inserted in one transaction per flush
(every HISTORY_FLUSH_MINUTES, and on shutdown), so a restart loses nothing and
a power cut loses at most one flush interval. Rows are kept for HISTORY_DAYS;
long ranges are read back as bucket averages.
"""

import sqlite3
import threading
import time
from pathlib import Path

from pydantic import ValidationError

from .models import HistoryPoint, HistorySample

COLUMNS = list(HistorySample.model_fields)   # t first; the schema follows the model
VALUES = COLUMNS[1:]
INT_FIELDS = {"satellites_used", "satellites_visible"}


class HistoryStore:
    def __init__(self, path: str, retention_s: float):
        self.path = path
        self.retention_s = retention_s
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.Lock()   # flushes and queries run in worker threads
        self.db.execute("PRAGMA journal_mode=WAL")
        # WAL + NORMAL: no fsync per commit; a power cut can drop the last flush but never corrupts the file.
        self.db.execute("PRAGMA synchronous=NORMAL")
        # Sort/GROUP BY scratch space in RAM: the container root filesystem is read-only.
        self.db.execute("PRAGMA temp_store=MEMORY")
        cols = ", ".join(c for c in COLUMNS if c != "t")
        self.db.execute(f"CREATE TABLE IF NOT EXISTS history (t REAL PRIMARY KEY, {cols}) WITHOUT ROWID")
        existing = {row[1] for row in self.db.execute("PRAGMA table_info(history)")}
        for col in COLUMNS:
            if col not in existing:   # a field added to HistorySample
                self.db.execute(f"ALTER TABLE history ADD COLUMN {col}")
        self.db.commit()

    def load(self, since: float) -> list[HistorySample]:
        with self.lock:
            rows = self.db.execute(
                f"SELECT {', '.join(COLUMNS)} FROM history WHERE t >= ? ORDER BY t", (since,)
            ).fetchall()
        samples = []
        for row in rows:
            try:
                samples.append(HistorySample.model_validate(dict(zip(COLUMNS, row))))
            except ValidationError:   # e.g. NULL in a column added after the row was written
                continue
        return samples

    def write(self, samples: list[HistorySample]) -> None:
        """One transaction: insert the batch and drop rows past retention."""
        placeholders = ", ".join("?" for _ in COLUMNS)
        with self.lock, self.db:
            self.db.executemany(
                f"INSERT OR REPLACE INTO history ({', '.join(COLUMNS)}) VALUES ({placeholders})",
                [tuple(getattr(s, c) for c in COLUMNS) for s in samples],
            )
            self.db.execute("DELETE FROM history WHERE t < ?", (time.time() - self.retention_s,))

    def buckets(self, since: float, until: float, bucket_s: float) -> list[HistoryPoint]:
        """Averages per `bucket_s` over [since, until), with offset min/max."""
        means = ", ".join(f"AVG({c})" for c in VALUES)
        sql = f"""
            SELECT CAST(t / :b AS INTEGER) AS k, {means},
                   MIN(system_time_offset_s), MAX(system_time_offset_s), MIN(pps_offset_s), MAX(pps_offset_s)
            FROM history WHERE t >= :since AND t < :until GROUP BY k ORDER BY k"""
        with self.lock:
            rows = self.db.execute(sql, {"b": bucket_s, "since": since, "until": until}).fetchall()
        return [_point(row[0] * bucket_s + bucket_s / 2, row[1:]) for row in rows]

    def close(self) -> None:
        with self.lock:
            self.db.close()


def _point(t: float, row: tuple) -> HistoryPoint:
    values = dict(zip(VALUES, row))
    for f in INT_FIELDS:
        if values[f] is not None:
            values[f] = round(values[f])
    lo_sys, hi_sys, lo_pps, hi_pps = row[len(VALUES):]
    return HistoryPoint(
        t=t, **values,
        system_time_offset_min_s=lo_sys, system_time_offset_max_s=hi_sys,
        pps_offset_min_s=lo_pps, pps_offset_max_s=hi_pps,
    )


def bucket_samples(samples: list[HistorySample], bucket_s: float) -> list[HistoryPoint]:
    """Same aggregation as HistoryStore.buckets, for samples not yet flushed."""
    groups: dict[int, list[HistorySample]] = {}
    for s in samples:
        groups.setdefault(int(s.t // bucket_s), []).append(s)
    out = []
    for k, group in sorted(groups.items()):
        def mean(field: str) -> float | None:
            vals = [v for s in group if (v := getattr(s, field)) is not None]
            return sum(vals) / len(vals) if vals else None
        sys_offsets = [s.system_time_offset_s for s in group]
        pps = [s.pps_offset_s for s in group if s.pps_offset_s is not None]
        row = (*(mean(f) for f in VALUES), min(sys_offsets), max(sys_offsets),
               min(pps) if pps else None, max(pps) if pps else None)
        out.append(_point(k * bucket_s + bucket_s / 2, row))
    return out

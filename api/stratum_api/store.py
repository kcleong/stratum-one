"""SQLite persistence for the history ring, written in batches to spare the SD card.

Samples are buffered in memory and inserted in one transaction per flush
(every HISTORY_FLUSH_MINUTES, and on shutdown), so a restart loses nothing and
a power cut loses at most one flush interval.
"""

import sqlite3
import time
from pathlib import Path

from pydantic import ValidationError

from .models import HistorySample

COLUMNS = list(HistorySample.model_fields)   # t first; the schema follows the model


class HistoryStore:
    def __init__(self, path: str, retention_s: float):
        self.path = path
        self.retention_s = retention_s
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        # WAL + NORMAL: no fsync per commit; a power cut can drop the last flush but never corrupts the file.
        self.db.execute("PRAGMA synchronous=NORMAL")
        cols = ", ".join(c for c in COLUMNS if c != "t")
        self.db.execute(f"CREATE TABLE IF NOT EXISTS history (t REAL PRIMARY KEY, {cols}) WITHOUT ROWID")
        existing = {row[1] for row in self.db.execute("PRAGMA table_info(history)")}
        for col in COLUMNS:
            if col not in existing:   # a field added to HistorySample
                self.db.execute(f"ALTER TABLE history ADD COLUMN {col}")
        self.db.commit()

    def load(self) -> list[HistorySample]:
        cutoff = time.time() - self.retention_s
        rows = self.db.execute(
            f"SELECT {', '.join(COLUMNS)} FROM history WHERE t >= ? ORDER BY t", (cutoff,)
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
        with self.db:
            self.db.executemany(
                f"INSERT OR REPLACE INTO history ({', '.join(COLUMNS)}) VALUES ({placeholders})",
                [tuple(getattr(s, c) for c in COLUMNS) for s in samples],
            )
            self.db.execute("DELETE FROM history WHERE t < ?", (time.time() - self.retention_s,))

    def close(self) -> None:
        self.db.close()

"""NTP Pool score of this server's addresses, fetched from the pool's public score pages.

Each address in POOL_SERVERS is looked up every POOL_INTERVAL seconds at
<POOL_URL>/scores/<address>/json. The overall score is the pool's own
"recentmedian" entry (the median of its monitors); above 10 the address is
handed out in the pool DNS. Scores are kept for HISTORY_DAYS, in SQLite when
the history store is enabled.
"""

import asyncio
import json
import logging
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request

from .models import PoolScore
from .store import HistoryStore

log = logging.getLogger(__name__)

USER_AGENT = "stratum_one (+https://github.com/kcleong/stratum-one)"


class PoolMonitor:
    def __init__(self, servers: tuple[str, ...], interval_s: float, url: str, retention_s: float,
                 store: HistoryStore | None):
        self.servers = servers
        self.interval_s = interval_s
        self.url = url
        self.retention_s = retention_s
        self.store = store
        self.scores: list[PoolScore] = []
        self._errors: dict[str, str] = {}   # server -> last logged error, to log changes only
        if store is not None:
            try:
                self.scores = store.load_pool(time.time() - retention_s)
            except sqlite3.Error as e:
                log.warning("pool scores unreadable from history store: %s", e)

    async def run(self) -> None:
        while True:
            fetched = [s for s in await asyncio.gather(*(self._fetch(server) for server in self.servers)) if s]
            if fetched:
                cutoff = time.time() - self.retention_s
                self.scores = [s for s in self.scores if s.t >= cutoff] + fetched
                if self.store is not None:
                    try:
                        await asyncio.to_thread(self.store.write_pool, fetched)
                    except sqlite3.Error as e:
                        log.warning("pool scores not saved: %s", e)
            await asyncio.sleep(self.interval_s)

    def since(self, seconds: float) -> list[PoolScore]:
        cutoff = time.time() - seconds
        return [s for s in self.scores if s.t >= cutoff]

    async def _fetch(self, server: str) -> PoolScore | None:
        try:
            score = await asyncio.to_thread(_score, f"{self.url}/scores/{urllib.parse.quote(server)}/json?limit=1")
        except (OSError, urllib.error.URLError, ValueError, KeyError) as e:
            error = str(e)
            if self._errors.get(server) != error:
                log.warning("pool score for %s: %s", server, error)
                self._errors[server] = error
            return None
        if self._errors.pop(server, None):
            log.info("pool score for %s available again", server)
        if score is None:   # address not (yet) scored by the pool
            return None
        return PoolScore(t=round(time.time(), 1), server=server, score=round(score, 2))


def _score(url: str) -> float | None:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    overall = [m["score"] for m in data["monitors"] if m.get("type") == "score"]
    return min(overall) if overall else None

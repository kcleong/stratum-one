"""Country and provider (ASN) of client addresses, from DB-IP Lite databases on local disk.

The databases (CC BY 4.0, https://db-ip.com) are downloaded monthly into GEOIP_DIR, so
lookups never send client addresses anywhere.
"""

import asyncio
import gzip
import ipaddress
import logging
import os
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

import maxminddb

log = logging.getLogger(__name__)

DATABASES = ("country", "asn")
URL = "https://download.db-ip.com/free/dbip-{kind}-lite-{month}.mmdb.gz"
MAX_AGE_S = 35 * 86400        # DB-IP publishes monthly
RETRY_S = 6 * 3600            # after a failed download
USER_AGENT = "stratum_one (+https://github.com/kcleong/stratum-one)"   # DB-IP rejects Python-urllib


class GeoLookup:
    def __init__(self, directory: str):
        self.dir = Path(directory)
        self.readers: dict[str, maxminddb.Reader] = {}
        self._opened: dict[str, float] = {}   # kind -> mtime of the file the reader has open

    def lookup(self, address: str) -> tuple[str | None, int | None, str | None]:
        """(ISO country code, AS number, AS organisation); all None for LAN or unknown addresses."""
        try:
            if ipaddress.ip_address(address).is_private:
                return None, None, None
        except ValueError:
            return None, None, None
        country = asn = None
        try:
            if r := self.readers.get("country"):
                country = r.get(address)
            if r := self.readers.get("asn"):
                asn = r.get(address)
        except (ValueError, maxminddb.InvalidDatabaseError) as e:
            log.debug("geo lookup %s: %s", address, e)
        return (
            (country or {}).get("country", {}).get("iso_code"),
            (asn or {}).get("autonomous_system_number"),
            (asn or {}).get("autonomous_system_organization"),
        )

    async def run(self) -> None:
        """Open what is on disk, then keep the databases fresh."""
        while True:
            ok = True
            for kind in DATABASES:
                path = self.dir / f"dbip-{kind}-lite.mmdb"
                if not path.exists() or time.time() - path.stat().st_mtime > MAX_AGE_S:
                    try:
                        await asyncio.to_thread(_download, kind, path)
                        log.info("downloaded DB-IP %s database", kind)
                    except (OSError, urllib.error.URLError) as e:
                        log.warning("DB-IP %s download failed: %s", kind, e)
                        ok = False
                if path.exists() and path.stat().st_mtime != self._opened.get(kind):
                    self._open(kind, path)
            await asyncio.sleep(86400 if ok else RETRY_S)

    def _open(self, kind: str, path: Path) -> None:
        mtime = path.stat().st_mtime
        try:
            reader = maxminddb.open_database(str(path))
        except (OSError, maxminddb.InvalidDatabaseError) as e:
            log.warning("DB-IP %s database unusable: %s", kind, e)
            return
        old, self.readers[kind] = self.readers.get(kind), reader
        self._opened[kind] = mtime
        if old:
            old.close()


def _download(kind: str, path: Path) -> None:
    """This month's file, or last month's early in the month before it is published."""
    path.parent.mkdir(parents=True, exist_ok=True)
    today = date.today()
    previous = date(today.year - (today.month == 1), (today.month - 2) % 12 + 1, 1)
    last_error: Exception | None = None
    for month in (today, previous):
        url = URL.format(kind=kind, month=month.strftime("%Y-%m"))
        tmp = path.with_suffix(".tmp")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=60) as resp, open(tmp, "wb") as out:
                out.write(gzip.decompress(resp.read()))
            os.replace(tmp, path)
            return
        except urllib.error.HTTPError as e:
            last_error = e
            tmp.unlink(missing_ok=True)
    raise last_error or OSError("no DB-IP release found")

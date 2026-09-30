"""Streaming gpsd client: keeps the latest TPV (fix) and SKY (satellites)."""

import asyncio
import json
import logging
import time

log = logging.getLogger(__name__)

WATCH = b'?WATCH={"enable":true,"json":true};\n'
FIX_MODES = {0: "unknown", 1: "no_fix", 2: "2d", 3: "3d"}
GNSS = {0: "GPS", 1: "SBAS", 2: "Galileo", 3: "BeiDou", 4: "IMES", 5: "QZSS", 6: "GLONASS", 7: "NavIC"}


class GpsdClient:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.connected = False
        self.version: str | None = None
        self.device: dict = {}
        self.tpv: dict = {}
        self.sky: dict = {}          # DOPs and counts, merged from partial SKY reports
        self.satellites: list = []   # from the last SKY report that listed them
        self.last_message: float | None = None

    async def run(self) -> None:
        backoff = 1
        while True:
            try:
                reader, writer = await asyncio.open_connection(self.host, self.port)
            except OSError as e:
                log.warning("gpsd connect to %s:%s failed: %s", self.host, self.port, e)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)
                continue
            backoff = 1
            self.connected = True
            log.info("connected to gpsd at %s:%s", self.host, self.port)
            try:
                writer.write(WATCH)
                await writer.drain()
                # gpsd reports every second; silence means a stuck connection.
                while line := await asyncio.wait_for(reader.readline(), timeout=15):
                    self._handle(line)
                log.warning("gpsd closed the connection")
            except (OSError, TimeoutError, ValueError) as e:
                log.warning("gpsd connection lost: %r", e)
            finally:
                self.connected = False
                writer.close()
            await asyncio.sleep(1)

    def _handle(self, line: bytes) -> None:
        try:
            msg = json.loads(line)
        except ValueError:
            return
        self.last_message = time.time()
        match msg.get("class"):
            case "TPV":
                self.tpv = msg
            case "SKY":
                if "satellites" in msg:
                    self.satellites = msg["satellites"]
                self.sky.update({k: v for k, v in msg.items() if k != "satellites"})
            case "DEVICES":
                if msg.get("devices"):
                    self.device = msg["devices"][0]
            case "DEVICE":
                self.device = msg
            case "VERSION":
                self.version = msg.get("release")

    def snapshot(self) -> dict:
        tpv, sky = self.tpv, self.sky
        sats = [
            {
                "prn": s.get("PRN"),
                "gnss": GNSS.get(s.get("gnssid"), "unknown"),
                "svid": s.get("svid"),
                "azimuth": s.get("az"),
                "elevation": s.get("el"),
                "snr": s.get("ss"),
                "used": bool(s.get("used")),
            }
            for s in self.satellites
        ]
        constellations: dict[str, dict] = {}
        for s in sats:
            c = constellations.setdefault(s["gnss"], {"visible": 0, "used": 0})
            c["visible"] += 1
            c["used"] += s["used"]
        return {
            "connected": self.connected,
            "age_s": round(time.time() - self.last_message, 1) if self.last_message else None,
            "gpsd_version": self.version,
            "device": {k: self.device.get(k) for k in ("path", "driver", "subtype", "subtype1", "bps")},
            "fix": {
                "mode": FIX_MODES.get(tpv.get("mode", 0), "unknown"),
                "time": tpv.get("time"),
                "leapseconds": tpv.get("leapseconds"),
                "lat": tpv.get("lat"),
                "lon": tpv.get("lon"),
                "alt_msl_m": tpv.get("altMSL"),
                "alt_hae_m": tpv.get("altHAE"),
                "eph_m": tpv.get("eph"),
                "epv_m": tpv.get("epv"),
                "ept_s": tpv.get("ept"),
                "speed_mps": tpv.get("speed"),
            },
            "dop": {k: sky.get(k) for k in ("gdop", "pdop", "hdop", "vdop", "tdop")},
            "satellites_visible": sky.get("nSat", len(sats)),
            "satellites_used": sky.get("uSat", sum(s["used"] for s in sats)),
            "constellations": constellations,
            "satellites": sats,
        }

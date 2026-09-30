"""Streaming gpsd client: keeps the latest TPV (fix) and SKY (satellites)."""

import asyncio
import json
import logging
import time

from .models import ConstellationCount, Dop, GpsDevice, GpsFix, GpsStatus, Satellite

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
        self.sky: dict = {}          # DOPs, merged from SKY reports
        self.satellites: list = []   # complete satellite list of the last finished epoch
        # gpsd sends several SKY lists per second, growing as each constellation's GSV/GSA
        # arrives; only the last one of an epoch is complete. Hold it until the epoch ends.
        self._pending: tuple[str | None, list] | None = None
        self._receiver_dops = False   # seen DOPs reported by the receiver itself
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
                self._commit_pending()   # TPV follows the epoch's last SKY list
            case "SKY":
                if "satellites" in msg:
                    if self._pending and self._pending[0] != msg.get("time"):
                        self._commit_pending()   # a new epoch started without a TPV
                    self._pending = (msg.get("time"), msg["satellites"])
                # uSat/nSat in SKY reports without a list come from a single talker's
                # GSA (e.g. 6 while 18 are used), so counts are taken from the list instead.
                # DOPs: reports without a list carry the receiver's own (as in GGA/GSA);
                # list reports carry gpsd's recomputation, used only if the receiver sends none.
                if "satellites" not in msg:
                    self._receiver_dops = True
                elif self._receiver_dops:
                    return
                self.sky.update({k: v for k, v in msg.items() if k not in ("satellites", "uSat", "nSat")})
            case "DEVICES":
                if msg.get("devices"):
                    self.device = msg["devices"][0]
            case "DEVICE":
                self.device = msg
            case "VERSION":
                self.version = msg.get("release")

    def _commit_pending(self) -> None:
        if self._pending:
            self.satellites = self._pending[1]
            self._pending = None

    def snapshot(self) -> GpsStatus:
        tpv, sky = self.tpv, self.sky
        sats = [
            Satellite(
                prn=s.get("PRN"),
                gnss=GNSS.get(s.get("gnssid"), "unknown"),
                svid=s.get("svid"),
                azimuth=s.get("az"),
                elevation=s.get("el"),
                snr=s.get("ss"),
                used=bool(s.get("used")),
            )
            for s in self.satellites
        ]
        constellations: dict[str, ConstellationCount] = {}
        for s in sats:
            c = constellations.setdefault(s.gnss, ConstellationCount(visible=0, used=0))
            c.visible += 1
            c.used += s.used
        return GpsStatus(
            connected=self.connected,
            age_s=round(time.time() - self.last_message, 1) if self.last_message else None,
            gpsd_version=self.version,
            device=GpsDevice.model_validate(self.device),
            fix=GpsFix(
                mode=FIX_MODES.get(tpv.get("mode", 0), "unknown"),
                time=tpv.get("time"),
                leapseconds=tpv.get("leapseconds"),
                lat=tpv.get("lat"),
                lon=tpv.get("lon"),
                alt_msl_m=tpv.get("altMSL"),
                alt_hae_m=tpv.get("altHAE"),
                eph_m=tpv.get("eph"),
                epv_m=tpv.get("epv"),
                ept_s=tpv.get("ept"),
                speed_mps=tpv.get("speed"),
            ),
            dop=Dop.model_validate(sky),
            satellites_visible=len(sats),
            satellites_used=sum(s.used for s in sats),
            constellations=constellations,
            satellites=sats,
        )

"""Publishes stats to MQTT with Home Assistant device discovery."""

import asyncio
import contextlib
import json
import logging

import aiomqtt

from .config import Settings
from .monitor import Monitor

log = logging.getLogger(__name__)

MEASUREMENT = {"state_class": "measurement"}
DIAGNOSTIC = {"entity_category": "diagnostic"}
MICROSECONDS = {"unit_of_measurement": "µs", "suggested_display_precision": 3, **MEASUREMENT}

# (key in state payload, entity name, platform, extra discovery options)
ENTITIES = [
    ("fix", "GPS fix", "sensor", {"icon": "mdi:crosshairs-gps"}),
    ("satellites_used", "Satellites used", "sensor", {"icon": "mdi:satellite-variant", **MEASUREMENT}),
    ("satellites_visible", "Satellites visible", "sensor", {"icon": "mdi:satellite-variant", **MEASUREMENT}),
    ("hdop", "HDOP", "sensor", {**MEASUREMENT, **DIAGNOSTIC}),
    ("pdop", "PDOP", "sensor", {**MEASUREMENT, **DIAGNOSTIC}),
    ("latitude", "Latitude", "sensor", {"unit_of_measurement": "°", **DIAGNOSTIC}),
    ("longitude", "Longitude", "sensor", {"unit_of_measurement": "°", **DIAGNOSTIC}),
    ("altitude", "Altitude", "sensor",
     {"device_class": "distance", "unit_of_measurement": "m", **MEASUREMENT, **DIAGNOSTIC}),
    ("reference", "Reference", "sensor", {"icon": "mdi:clock-check-outline"}),
    ("stratum", "Stratum", "sensor", {"icon": "mdi:layers-outline", **MEASUREMENT}),
    ("system_offset_us", "System time offset", "sensor", {"icon": "mdi:timer-outline", **MICROSECONDS}),
    ("last_offset_us", "Last offset", "sensor", {"icon": "mdi:timer-outline", **MICROSECONDS}),
    ("rms_offset_us", "RMS offset", "sensor", {"icon": "mdi:timer-outline", **MICROSECONDS}),
    ("pps_offset_us", "PPS offset", "sensor", {"icon": "mdi:pulse", **MICROSECONDS}),
    ("root_dispersion_us", "Root dispersion", "sensor", {**MICROSECONDS, **DIAGNOSTIC}),
    ("frequency_ppm", "Frequency", "sensor",
     {"unit_of_measurement": "ppm", "suggested_display_precision": 3, **MEASUREMENT}),
    ("skew_ppm", "Frequency skew", "sensor",
     {"unit_of_measurement": "ppm", "suggested_display_precision": 3, **MEASUREMENT, **DIAGNOSTIC}),
    ("leap_status", "Leap status", "sensor", DIAGNOSTIC),
    ("ntp_clients", "NTP clients", "sensor", {"icon": "mdi:lan-connect", **MEASUREMENT}),
    ("ntp_packets_received", "NTP packets received", "sensor", {"state_class": "total_increasing"}),
    ("ntp_packets_dropped", "NTP packets dropped", "sensor", {"state_class": "total_increasing", **DIAGNOSTIC}),
    ("cpu_temp", "CPU temperature", "sensor",
     {"device_class": "temperature", "unit_of_measurement": "°C", **MEASUREMENT, **DIAGNOSTIC}),
    ("load_1m", "Load (1 min)", "sensor", {"suggested_display_precision": 2, **MEASUREMENT, **DIAGNOSTIC}),
    ("pps_locked", "PPS locked", "binary_sensor", {"icon": "mdi:lock-clock"}),
    ("gpsd_connected", "gpsd connected", "binary_sensor", {"device_class": "connectivity", **DIAGNOSTIC}),
    ("chrony_ok", "chrony reachable", "binary_sensor", {"device_class": "connectivity", **DIAGNOSTIC}),
]


def _us(seconds: float | None) -> float | None:
    return None if seconds is None else round(seconds * 1e6, 3)


def _on_off(value: bool) -> str:
    return "ON" if value else "OFF"


def state_payload(monitor: Monitor) -> dict:
    snap = monitor.snapshot()
    gps, chrony, host = snap["gps"], snap["chrony"], snap["system"]
    tracking = chrony["tracking"] or {}
    selected = monitor.chrony.selected_source or {}
    pps = next((s for s in chrony["sources"] if s["mode"] == "refclock" and s["name"] == "PPS"), {})
    return {
        "fix": gps["fix"]["mode"],
        "satellites_used": gps["satellites_used"],
        "satellites_visible": gps["satellites_visible"],
        "hdop": gps["dop"]["hdop"],
        "pdop": gps["dop"]["pdop"],
        "latitude": gps["fix"]["lat"],
        "longitude": gps["fix"]["lon"],
        "altitude": gps["fix"]["alt_msl_m"],
        "reference": tracking.get("ref_name"),
        "stratum": tracking.get("stratum"),
        "system_offset_us": _us(tracking.get("system_time_offset_s")),
        "last_offset_us": _us(tracking.get("last_offset_s")),
        "rms_offset_us": _us(tracking.get("rms_offset_s")),
        "pps_offset_us": _us(pps.get("offset_s")),
        "root_dispersion_us": _us(tracking.get("root_dispersion_s")),
        "frequency_ppm": tracking.get("frequency_ppm"),
        "skew_ppm": tracking.get("skew_ppm"),
        "leap_status": tracking.get("leap_status"),
        "ntp_clients": chrony["client_count"],
        "ntp_packets_received": (chrony["serverstats"] or {}).get("ntp_packets_received"),
        "ntp_packets_dropped": (chrony["serverstats"] or {}).get("ntp_packets_dropped"),
        "cpu_temp": host["cpu_temp_c"],
        "load_1m": host["load"][0] if host["load"] else None,
        "pps_locked": _on_off(selected.get("mode") == "refclock" and selected.get("name") == "PPS"),
        "gpsd_connected": _on_off(gps["connected"]),
        "chrony_ok": _on_off(chrony["ok"]),
    }


class MqttPublisher:
    def __init__(self, settings: Settings, monitor: Monitor):
        self.settings = settings
        self.monitor = monitor
        self.uid = f"{settings.mqtt_topic_prefix}_{settings.node_id}".replace("-", "_")
        base = f"{settings.mqtt_topic_prefix}/{settings.node_id}"
        self.state_topic = f"{base}/state"
        self.availability_topic = f"{base}/availability"
        self.discovery_topic = f"{settings.ha_discovery_prefix}/device/{self.uid}/config"
        self.ha_status_topic = f"{settings.ha_discovery_prefix}/status"

    def discovery(self) -> dict:
        gps = self.monitor.gps
        components = {
            f"{self.uid}_{key}": {
                "platform": platform,
                "name": name,
                "unique_id": f"{self.uid}_{key}",
                "value_template": f"{{{{ value_json.{key} }}}}",
                **extra,
            }
            for key, name, platform, extra in ENTITIES
        }
        return {
            "device": {
                "identifiers": [self.uid],
                "name": self.settings.node_id,
                "manufacturer": "stratum_one",
                "model": f"GPS/PPS stratum-1 NTP ({gps.device.get('driver') or 'GPS'})",
                # u-blox subtype1 starts with "FWVER=SPG 5.10,..."
                "sw_version": (gps.device.get("subtype1") or "").split(",")[0].removeprefix("FWVER=") or None,
            },
            "origin": {"name": "stratum_one"},
            "state_topic": self.state_topic,
            "availability_topic": self.availability_topic,
            "components": components,
        }

    async def run(self) -> None:
        s = self.settings
        backoff = 1
        while True:
            try:
                async with aiomqtt.Client(
                    hostname=s.mqtt_host,
                    port=s.mqtt_port,
                    username=s.mqtt_user,
                    password=s.mqtt_password,
                    identifier=self.uid,
                    will=aiomqtt.Will(self.availability_topic, "offline", qos=1, retain=True),
                ) as client:
                    log.info("connected to MQTT broker %s:%s", s.mqtt_host, s.mqtt_port)
                    backoff = 1
                    await client.subscribe(self.ha_status_topic)
                    await self._announce(client)
                    try:
                        async with asyncio.TaskGroup() as tg:
                            tg.create_task(self._publish_loop(client))
                            tg.create_task(self._listen(client))
                    finally:
                        # A clean disconnect skips the will, so mark offline ourselves.
                        with contextlib.suppress(aiomqtt.MqttError):
                            await client.publish(self.availability_topic, "offline", qos=1, retain=True)
            except* aiomqtt.MqttError as eg:
                log.warning("MQTT: %s; retrying in %ss", eg.exceptions[0], backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)

    async def _announce(self, client: aiomqtt.Client) -> None:
        await client.publish(self.discovery_topic, json.dumps(self.discovery()), qos=1, retain=True)
        await client.publish(self.availability_topic, "online", qos=1, retain=True)
        await self._publish_state(client)

    async def _publish_state(self, client: aiomqtt.Client) -> None:
        await client.publish(self.state_topic, json.dumps(state_payload(self.monitor)))

    async def _publish_loop(self, client: aiomqtt.Client) -> None:
        while True:
            await asyncio.sleep(self.settings.mqtt_interval)
            await self._publish_state(client)

    async def _listen(self, client: aiomqtt.Client) -> None:
        async for message in client.messages:
            # HA restarted: resend discovery so entities come back without waiting.
            if message.payload == b"online":
                await self._announce(client)

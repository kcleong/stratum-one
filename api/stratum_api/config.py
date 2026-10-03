import os
import socket
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    api_host: str
    api_port: int
    log_level: str
    gpsd_host: str
    gpsd_port: int
    chrony_interval: float     # seconds between chronyc polls (also history resolution)
    clients_interval: float    # seconds between `chronyc clients` polls (large on a public server)
    history_hours: float       # in memory at full resolution
    history_days: float        # kept in SQLite, served as bucket averages
    history_db: str | None     # SQLite path; history is memory-only when unset
    history_flush_minutes: float
    geoip_dir: str | None      # DB-IP Lite country/ASN databases for client lookups; unset = off
    sky_hours: float           # sky coverage window, sliding by the hour
    pool_servers: tuple[str, ...]  # addresses registered in the NTP Pool; empty = no pool score tracking
    pool_interval: float       # seconds between pool score fetches
    pool_url: str              # NTP Pool site serving /scores/<ip>/json
    node_id: str               # device name in HA and MQTT topics
    mqtt_host: str | None      # MQTT disabled when unset
    mqtt_port: int
    mqtt_user: str | None
    mqtt_password: str | None
    mqtt_interval: float
    mqtt_topic_prefix: str
    ha_discovery_prefix: str


def load_settings() -> Settings:
    env = os.environ.get
    return Settings(
        api_host=env("API_HOST", "0.0.0.0"),
        api_port=int(env("API_PORT", "8000")),
        log_level=env("LOG_LEVEL", "INFO").upper(),
        gpsd_host=env("GPSD_HOST", "127.0.0.1"),
        gpsd_port=int(env("GPSD_PORT", "2947")),
        chrony_interval=float(env("CHRONY_INTERVAL", "5")),
        clients_interval=float(env("CLIENTS_INTERVAL", "60")),
        history_hours=float(env("HISTORY_HOURS", "24")),
        history_days=float(env("HISTORY_DAYS", "30")),
        history_db=env("HISTORY_DB", "/data/history.db") or None,
        history_flush_minutes=float(env("HISTORY_FLUSH_MINUTES", "15")),
        geoip_dir=env("GEOIP_DIR", "/data/geoip") or None,
        sky_hours=float(env("SKY_HOURS", "24")),
        pool_servers=tuple(env("POOL_SERVERS", "").replace(",", " ").split()),
        pool_interval=float(env("POOL_INTERVAL", "900")),
        pool_url=env("POOL_URL", "https://www.ntppool.org").rstrip("/"),
        node_id=env("NODE_ID") or socket.gethostname(),
        mqtt_host=env("MQTT_HOST") or None,
        mqtt_port=int(env("MQTT_PORT", "1883")),
        mqtt_user=env("MQTT_USER") or None,
        mqtt_password=env("MQTT_PASSWORD") or None,
        mqtt_interval=float(env("MQTT_INTERVAL", "10")),
        mqtt_topic_prefix=env("MQTT_TOPIC_PREFIX", "stratum_one"),
        ha_discovery_prefix=env("HA_DISCOVERY_PREFIX", "homeassistant"),
    )

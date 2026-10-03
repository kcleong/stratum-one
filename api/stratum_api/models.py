"""Response models. Units are in the field names: _s seconds, _m metres, _ppm, _c °C."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# --- GPS (gpsd) ---

FixMode = Literal["unknown", "no_fix", "2d", "3d"]


class Satellite(BaseModel):
    prn: int | None = Field(description="gpsd PRN (unique across constellations)")
    gnss: str = Field(description="GPS, SBAS, Galileo, BeiDou, IMES, QZSS, GLONASS, NavIC")
    svid: int | None = Field(description="Satellite id within its constellation")
    azimuth: float | None = Field(description="Degrees from true north")
    elevation: float | None = Field(description="Degrees above the horizon")
    snr: float | None = Field(description="Signal strength, dBHz")
    used: bool = Field(description="Used in the navigation solution")


class ConstellationCount(BaseModel):
    visible: int
    used: int


class GpsDevice(BaseModel):
    path: str | None = None
    driver: str | None = None
    subtype: str | None = None
    subtype1: str | None = None
    bps: int | None = None


class GpsFix(BaseModel):
    mode: FixMode
    time: datetime | None = Field(description="GPS time of the fix (UTC)")
    leapseconds: int | None = None
    lat: float | None = None
    lon: float | None = None
    alt_msl_m: float | None = Field(None, description="Altitude above mean sea level")
    alt_hae_m: float | None = Field(None, description="Altitude above the WGS84 ellipsoid")
    eph_m: float | None = Field(None, description="Estimated horizontal error (95%)")
    epv_m: float | None = Field(None, description="Estimated vertical error (95%)")
    ept_s: float | None = Field(None, description="Estimated time error (95%)")
    speed_mps: float | None = None


class Dop(BaseModel):
    gdop: float | None = None
    pdop: float | None = None
    hdop: float | None = None
    vdop: float | None = None
    tdop: float | None = None


class GpsStatus(BaseModel):
    connected: bool = Field(description="Connected to gpsd")
    age_s: float | None = Field(description="Seconds since the last gpsd report")
    gpsd_version: str | None
    device: GpsDevice
    fix: GpsFix
    dop: Dop
    satellites_visible: int
    satellites_used: int
    constellations: dict[str, ConstellationCount]
    satellites: list[Satellite]


# --- chrony ---

SourceMode = Literal["server", "peer", "refclock"]
SourceState = Literal["selected", "combined", "not_combined", "unusable", "falseticker", "too_variable"]


class Tracking(BaseModel):
    ref_id: str = Field(description="Reference id, hex")
    ref_name: str = Field(description="Reference source name or address")
    stratum: int
    ref_time: float = Field(description="Unix time of the last reference update")
    system_time_offset_s: float = Field(description="System clock minus true time: + means the clock is ahead")
    last_offset_s: float = Field(description="Offset measured at the last clock update")
    rms_offset_s: float = Field(description="Long-term average of the offset")
    frequency_ppm: float = Field(description="Local oscillator error: + means it runs fast")
    residual_freq_ppm: float
    skew_ppm: float = Field(description="Error bound of the frequency estimate")
    root_delay_s: float
    root_dispersion_s: float
    update_interval_s: float
    leap_status: str = Field(description="Normal, Insert second, Delete second or Not synchronised")


class Source(BaseModel):
    mode: SourceMode
    state: SourceState
    name: str
    stratum: int
    poll: int = Field(description="Poll interval, log2 seconds")
    reach: int = Field(description="Bitmask of the last 8 polls (255 = all answered)")
    last_rx_s: int | None = Field(description="Seconds since the last sample")
    offset_s: float = Field(description="Last sample offset, adjusted for clock changes since")
    measured_offset_s: float
    error_s: float = Field(description="Error margin of the last sample")


class SourceStats(BaseModel):
    name: str
    samples: int
    runs: int
    span_s: int
    frequency_ppm: float
    freq_skew_ppm: float
    offset_s: float
    std_dev_s: float


class ServerStats(BaseModel):
    ntp_packets_received: int | None = None
    ntp_packets_dropped: int | None = None
    cmd_packets_received: int | None = None
    cmd_packets_dropped: int | None = None
    client_log_records_dropped: int | None = None
    nts_ke_accepted: int | None = None
    nts_ke_dropped: int | None = None
    authenticated_ntp_packets: int | None = None
    interleaved_ntp_packets: int | None = None
    ntp_timestamps_held: int | None = None
    ntp_timestamp_span: int | None = None
    ntp_daemon_rx_timestamps: int | None = None
    ntp_daemon_tx_timestamps: int | None = None
    ntp_kernel_rx_timestamps: int | None = None
    ntp_kernel_tx_timestamps: int | None = None
    ntp_hw_rx_timestamps: int | None = None
    ntp_hw_tx_timestamps: int | None = None


class Activity(BaseModel):
    online: int
    offline: int
    burst_online: int
    burst_offline: int
    unresolved: int


class Client(BaseModel):
    address: str
    ntp_packets: int
    ntp_dropped: int
    ntp_interval: int | None = Field(description="Average request interval, log2 seconds")
    ntp_last_rx_s: int | None = Field(description="Seconds since the last NTP request")
    cmd_packets: int
    cmd_dropped: int
    cmd_last_rx_s: int | None
    country: str | None = Field(None, description="ISO 3166 country code (DB-IP Lite); none for LAN")
    asn: int | None = Field(None, description="Autonomous system number of the network (DB-IP Lite)")
    asn_org: str | None = Field(None, description="Provider owning that network (DB-IP Lite)")


class Provider(BaseModel):
    asn: int | None = Field(description="Autonomous system number (DB-IP Lite); null = not in the database")
    asn_org: str | None = Field(description="Provider owning that network")
    country: str | None = Field(description="Most common ISO 3166 country code among those clients (DB-IP Lite)")
    clients: int = Field(description="Public clients of this provider active in the last hour")
    ntp_packets: int = Field(description="NTP requests from those clients since chronyd started")


class ChronyStatus(BaseModel):
    ok: bool = Field(description="Last poll of chronyd succeeded")
    error: str | None
    updated: float | None = Field(description="Unix time of the last successful poll")
    tracking: Tracking | None
    selected_source: str | None
    sources: list[Source]
    sourcestats: list[SourceStats]
    serverstats: ServerStats | None
    activity: Activity | None
    client_count: int = Field(description="Clients in chronyd's client log (since start, bounded by clientloglimit)")
    active_clients: int | None = Field(description="Clients with an NTP request in the last hour; null until the first clients poll")
    active_clients_ipv6: int | None = Field(description="Of active_clients, those using IPv6")
    ntp_requests_per_s: float | None = Field(description="NTP requests per second over the last poll interval")


# --- host, aggregate, history ---


class SystemStatus(BaseModel):
    hostname: str
    cpu_temp_c: float | None
    load: list[float] | None = Field(description="1, 5 and 15 minute load averages")
    uptime_s: float | None
    mem_total_bytes: int | None
    mem_available_bytes: int | None


class Status(BaseModel):
    time: float = Field(description="Unix time of this snapshot")
    gps: GpsStatus
    chrony: ChronyStatus
    system: SystemStatus


class HistorySample(BaseModel):
    t: float = Field(description="Unix time")
    system_time_offset_s: float
    last_offset_s: float
    rms_offset_s: float
    frequency_ppm: float
    skew_ppm: float
    pps_offset_s: float | None
    satellites_used: int
    satellites_visible: int
    cpu_temp_c: float | None
    ntp_requests_per_s: float | None = None   # added later: NULL in older rows


class HistoryPoint(HistorySample):
    """A raw sample (ranges up to 24 h) or a bucket average (longer ranges).

    For bucket averages `t` is the bucket centre, the other fields are means,
    and the offset min/max fields bound what the mean hides.
    """

    system_time_offset_min_s: float | None = None
    system_time_offset_max_s: float | None = None
    pps_offset_min_s: float | None = None
    pps_offset_max_s: float | None = None


# --- Sky coverage ---


class SkyCell(BaseModel):
    az: int = Field(description="Lower azimuth edge of the patch, degrees from true north")
    el: int = Field(description="Lower elevation edge of the patch, degrees above the horizon")
    samples: int = Field(description="Satellite sightings in this patch (predicted positions included)")
    received: int = Field(description="Sightings with a signal (SNR > 0)")
    mean_snr: float | None = Field(description="Average SNR of the received sightings, dBHz")
    max_snr: float | None = Field(description="Strongest SNR seen, dBHz")


class SkyCoverage(BaseModel):
    hours: float = Field(description="Window length (SKY_HOURS)")
    az_step: int
    el_step: int
    sample_interval_s: float
    since: float | None = Field(description="Unix time of the oldest data in the window")
    cells: list[SkyCell]


# --- NTP Pool ---


class PoolScore(BaseModel):
    t: float = Field(description="Unix time the score was fetched")
    server: str = Field(description="Server address as configured in POOL_SERVERS")
    score: float = Field(description="Overall pool score (recent median of the monitors); > 10 is in the pool DNS")


class PoolHistory(BaseModel):
    servers: list[str] = Field(description="POOL_SERVERS; empty when pool tracking is off")
    interval_s: float = Field(description="Seconds between score fetches")
    scores: list[PoolScore]


class Health(BaseModel):
    gpsd: bool
    chrony: bool

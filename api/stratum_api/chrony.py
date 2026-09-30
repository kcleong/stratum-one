"""chronyd stats via `chronyc -c` (CSV output) over the shared /run/chrony socket."""

import asyncio
import logging
import time

from .models import Activity, ChronyStatus, Client, ServerStats, Source, SourceStats, Tracking

log = logging.getLogger(__name__)

SOURCE_MODES = {"^": "server", "=": "peer", "#": "refclock"}
SOURCE_STATES = {
    "*": "selected",
    "+": "combined",
    "-": "not_combined",
    "?": "unusable",
    "x": "falseticker",
    "~": "too_variable",
}
SERVERSTATS_FIELDS = (
    "ntp_packets_received",
    "ntp_packets_dropped",
    "cmd_packets_received",
    "cmd_packets_dropped",
    "client_log_records_dropped",
    "nts_ke_accepted",
    "nts_ke_dropped",
    "authenticated_ntp_packets",
    "interleaved_ntp_packets",
    "ntp_timestamps_held",
    "ntp_timestamp_span",
    "ntp_daemon_rx_timestamps",
    "ntp_daemon_tx_timestamps",
    "ntp_kernel_rx_timestamps",
    "ntp_kernel_tx_timestamps",
    "ntp_hw_rx_timestamps",
    "ntp_hw_tx_timestamps",
)
UNSET_INTERVAL = 127        # clients: interval not known yet
UNSET_LAST = 4294967295     # clients: never seen


class ChronycError(Exception):
    pass


async def chronyc(*args: str, timeout: float = 5.0) -> list[list[str]]:
    proc = await asyncio.create_subprocess_exec(
        "chronyc", "-c", *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        raise ChronycError(f"chronyc {' '.join(args)}: timed out") from None
    if proc.returncode:
        raise ChronycError(f"chronyc {' '.join(args)}: {err.decode().strip() or proc.returncode}")
    return [line.split(",") for line in out.decode().splitlines() if line]


def _int(value: str, unset: int | None = None) -> int | None:
    try:
        n = int(value)
    except ValueError:
        return None
    return None if n == unset else n


def parse_tracking(row: list[str]) -> Tracking:
    return Tracking(
        ref_id=row[0],
        ref_name=row[1],
        stratum=int(row[2]),
        ref_time=float(row[3]),
        # chronyc prints the correction still to apply; negate so + means the clock is ahead.
        system_time_offset_s=-float(row[4]),
        last_offset_s=float(row[5]),
        rms_offset_s=float(row[6]),
        frequency_ppm=float(row[7]),       # + means the local clock runs fast
        residual_freq_ppm=float(row[8]),
        skew_ppm=float(row[9]),
        root_delay_s=float(row[10]),
        root_dispersion_s=float(row[11]),
        update_interval_s=float(row[12]),
        leap_status=row[13],
    )


def parse_source(row: list[str]) -> Source:
    return Source(
        mode=SOURCE_MODES.get(row[0], row[0]),
        state=SOURCE_STATES.get(row[1], row[1]),
        name=row[2],
        stratum=int(row[3]),
        poll=int(row[4]),                  # log2 seconds
        reach=int(row[5], 8),              # bitmask of the last 8 polls
        last_rx_s=_int(row[6], UNSET_LAST),
        offset_s=float(row[7]),            # adjusted for clock changes since last sample
        measured_offset_s=float(row[8]),
        error_s=float(row[9]),
    )


def parse_sourcestats(row: list[str]) -> SourceStats:
    return SourceStats(
        name=row[0],
        samples=int(row[1]),
        runs=int(row[2]),
        span_s=int(row[3]),
        frequency_ppm=float(row[4]),
        freq_skew_ppm=float(row[5]),
        offset_s=float(row[6]),
        std_dev_s=float(row[7]),
    )


def parse_client(row: list[str]) -> Client:
    return Client(
        address=row[0],
        ntp_packets=int(row[1]),
        ntp_dropped=int(row[2]),
        ntp_interval=_int(row[3], UNSET_INTERVAL),     # log2 seconds
        ntp_last_rx_s=_int(row[5], UNSET_LAST),
        cmd_packets=int(row[6]),
        cmd_dropped=int(row[7]),
        cmd_last_rx_s=_int(row[9], UNSET_LAST),
    )


def parse_serverstats(row: list[str]) -> ServerStats:
    return ServerStats(**{name: _int(value) for name, value in zip(SERVERSTATS_FIELDS, row)})


def parse_activity(row: list[str]) -> Activity:
    keys = ("online", "offline", "burst_online", "burst_offline", "unresolved")
    return Activity(**{k: int(v) for k, v in zip(keys, row)})


class ChronyMonitor:
    def __init__(self) -> None:
        self.tracking: Tracking | None = None
        self.sources: list[Source] = []
        self.sourcestats: list[SourceStats] = []
        self.serverstats: ServerStats | None = None
        self.activity: Activity | None = None
        self.clients: list[Client] = []
        self.error: str | None = None
        self.updated: float | None = None

    async def poll(self) -> None:
        # -N: configured source names instead of addresses; -n: no reverse DNS for clients.
        results = await asyncio.gather(
            chronyc("tracking"),
            chronyc("-N", "sources"),
            chronyc("-N", "sourcestats"),
            chronyc("serverstats"),
            chronyc("activity"),
            chronyc("-n", "clients"),
            return_exceptions=True,
        )
        errors = [str(r) for r in results if isinstance(r, Exception)]
        tracking, sources, sourcestats, serverstats, activity, clients = results
        try:
            if not isinstance(tracking, Exception) and tracking:
                self.tracking = parse_tracking(tracking[0])
            if not isinstance(sources, Exception):
                self.sources = [parse_source(r) for r in sources]
            if not isinstance(sourcestats, Exception):
                self.sourcestats = [parse_sourcestats(r) for r in sourcestats]
            if not isinstance(serverstats, Exception) and serverstats:
                self.serverstats = parse_serverstats(serverstats[0])
            if not isinstance(activity, Exception) and activity:
                self.activity = parse_activity(activity[0])
            if not isinstance(clients, Exception):
                self.clients = [parse_client(r) for r in clients]
        except (IndexError, ValueError) as e:
            errors.append(f"unexpected chronyc output: {e!r}")
        error = "; ".join(errors) or None
        if error and error != self.error:   # log changes only, not every poll
            log.warning("chrony poll: %s", error)
        self.error = error
        if not errors:
            self.updated = time.time()

    @property
    def selected_source(self) -> Source | None:
        return next((s for s in self.sources if s.state == "selected"), None)

    @property
    def pps_source(self) -> Source | None:
        return next((s for s in self.sources if s.mode == "refclock" and s.name == "PPS"), None)

    def snapshot(self) -> ChronyStatus:
        selected = self.selected_source
        return ChronyStatus(
            ok=self.error is None,
            error=self.error,
            updated=self.updated,
            tracking=self.tracking,
            selected_source=selected.name if selected else None,
            sources=self.sources,
            sourcestats=self.sourcestats,
            serverstats=self.serverstats,
            activity=self.activity,
            client_count=len(self.clients),
        )

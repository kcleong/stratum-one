"""chronyd stats via `chronyc -c` (CSV output) over the shared /run/chrony socket."""

import asyncio
import heapq
import ipaddress
import logging
import time
from collections.abc import AsyncIterator

from .models import Activity, BurstClient, BurstPrefix, ChronyStatus, Client, ServerStats, Source, SourceStats, Tracking

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
CLIENTS_TOP = 50            # busiest clients kept; a public pool server sees tens of thousands
ACTIVE_WINDOW_S = 3600      # a client counts as active with an NTP request this recent
SCAN_TOP = 20               # burst scans: busiest addresses and networks kept
BASELINE_MIN_PACKETS = 32   # burst baseline keeps busier records only; smaller ones count in full (error < 32)


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


async def chronyc_rows(*args: str, timeout: float = 30.0) -> AsyncIterator[list[list[str]]]:
    """Like chronyc(), but yields batches of rows as they arrive, for output too large to hold."""
    proc = await asyncio.create_subprocess_exec(
        "chronyc", "-c", *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    rest = b""
    try:
        # 64 KiB reads, not readline(): per-line awaits cost ~0.1 ms each on a Pi.
        while chunk := await asyncio.wait_for(proc.stdout.read(65536), max(0.0, deadline - loop.time())):
            *lines, rest = (rest + chunk).split(b"\n")
            yield [line.decode().split(",") for line in lines if line]
        if rest.strip():
            yield [rest.decode().split(",")]
        await asyncio.wait_for(proc.wait(), max(0.0, deadline - loop.time()))
    except TimeoutError:
        raise ChronycError(f"chronyc {' '.join(args)}: timed out") from None
    finally:
        if proc.returncode is None:
            proc.kill()
            await proc.wait()
    if proc.returncode:
        err = await proc.stderr.read()
        raise ChronycError(f"chronyc {' '.join(args)}: {err.decode().strip() or proc.returncode}")


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
        self.client_count = 0
        self.active_clients: int | None = None
        self.active_clients_ipv6: int | None = None
        self.active_public: list[tuple[str, int]] = []   # (address, ntp_packets) of active non-LAN clients
        # address -> (ntp_packets, ntp_dropped) at the last client poll: a burst ranks clients
        # by what they sent since then, not by their totals since the record was created.
        self.counters: dict[str, tuple[int, int]] = {}
        self.ntp_requests_per_s: float | None = None
        self.ntp_dropped_per_s: float | None = None
        self._last_rx: tuple[float, int, int] | None = None   # (monotonic time, ntp_packets_received, ntp_packets_dropped)
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
            return_exceptions=True,
        )
        errors = [str(r) for r in results if isinstance(r, Exception)]
        tracking, sources, sourcestats, serverstats, activity = results
        try:
            if not isinstance(tracking, Exception) and tracking:
                self.tracking = parse_tracking(tracking[0])
            if not isinstance(sources, Exception):
                self.sources = [parse_source(r) for r in sources]
            if not isinstance(sourcestats, Exception):
                self.sourcestats = [parse_sourcestats(r) for r in sourcestats]
            if not isinstance(serverstats, Exception) and serverstats:
                self.serverstats = parse_serverstats(serverstats[0])
                self._update_rate(self.serverstats.ntp_packets_received, self.serverstats.ntp_packets_dropped)
            if not isinstance(activity, Exception) and activity:
                self.activity = parse_activity(activity[0])
        except (IndexError, ValueError) as e:
            errors.append(f"unexpected chronyc output: {e!r}")
        error = "; ".join(errors) or None
        if error and error != self.error:   # log changes only, not every poll
            log.warning("chrony poll: %s", error)
        self.error = error
        if not errors:
            self.updated = time.time()

    def _update_rate(self, received: int | None, dropped: int | None) -> None:
        now = time.monotonic()
        ok = received is not None and dropped is not None
        last, self._last_rx = self._last_rx, (now, received, dropped) if ok else None
        # No rate on the first poll or after chronyd restarted (counters went back).
        if last is None or not ok or received < last[1] or dropped < last[2] or now <= last[0]:
            self.ntp_requests_per_s = self.ntp_dropped_per_s = None
        else:
            self.ntp_requests_per_s = (received - last[1]) / (now - last[0])
            self.ntp_dropped_per_s = (dropped - last[2]) / (now - last[0])

    async def poll_clients(self) -> None:
        """Count all clients but keep only the busiest public ones plus every LAN client.

        A public pool server's client log holds up to clientloglimit worth of rows (hundreds of
        thousands), so rows are streamed and only a small heap is ever held in memory.
        """
        count = active = active_v6 = 0
        busiest: list[tuple[int, int, list[str]]] = []   # min-heap of (ntp_packets, seq, row)
        lan: list[list[str]] = []
        active_public: list[tuple[str, int]] = []
        counters: dict[str, tuple[int, int]] = {}
        try:
            async for rows in chronyc_rows("-n", "clients"):
                for row in rows:
                    count += 1
                    packets = int(row[1])
                    is_lan = _is_lan(row[0])
                    if packets >= BASELINE_MIN_PACKETS and not is_lan:
                        counters[row[0]] = (packets, int(row[2]))
                    if packets and (last := _int(row[5], UNSET_LAST)) is not None and last <= ACTIVE_WINDOW_S:
                        active += 1
                        active_v6 += ":" in row[0]
                        if not is_lan:
                            active_public.append((row[0], packets))
                    if is_lan:
                        lan.append(row)
                    elif len(busiest) < CLIENTS_TOP:
                        heapq.heappush(busiest, (packets, count, row))
                    elif packets > busiest[0][0]:
                        heapq.heapreplace(busiest, (packets, count, row))
                await asyncio.sleep(0)   # a full pipe buffer doesn't yield; let the API serve meanwhile
            clients = [parse_client(r) for _, _, r in sorted(busiest, reverse=True)] + [parse_client(r) for r in lan]
        except (ChronycError, IndexError, ValueError) as e:
            log.warning("chrony clients: %s", e)
            return
        self.client_count = count
        self.active_clients = active
        self.active_clients_ipv6 = active_v6
        self.active_public = active_public
        self.counters = counters
        self.clients = clients

    async def scan_recent(
        self, window_s: int, baseline: dict[str, tuple[int, int]]
    ) -> tuple[int, int, list[BurstClient], list[BurstPrefix], list[tuple[str, int]]]:
        """Clients with an NTP request in the last `window_s`: (count, IPv6 count, busiest,
        networks with the most addresses, every (address, ntp_packets) for an ASN breakdown).
        Requests count from `baseline` (address -> (ntp_packets, ntp_dropped), see `counters`);
        an address not in it counts in full.

        Raises ChronycError when chronyc fails.
        """
        count = count_v6 = 0
        busiest: list[tuple[int, int, list[str], int]] = []   # min-heap of (packets, seq, row, dropped)
        prefixes: dict[str, list[int]] = {}               # prefix -> [addresses, packets]
        recent: list[tuple[str, int]] = []
        async for rows in chronyc_rows("-n", "clients"):
            for row in rows:
                last = _int(row[5], UNSET_LAST)
                if last is None or last > window_s or _is_lan(row[0]):
                    continue
                count += 1
                # max(0, ...): a record recreated since the baseline restarts its counters
                before = baseline.get(row[0], (0, 0))
                packets = max(0, int(row[1]) - before[0])
                dropped = max(0, int(row[2]) - before[1])
                v6 = ":" in row[0]
                count_v6 += v6
                recent.append((row[0], packets))
                entry = prefixes.setdefault(_prefix(row[0], v6), [0, 0])
                entry[0] += 1
                entry[1] += packets
                if len(busiest) < SCAN_TOP:
                    heapq.heappush(busiest, (packets, count, row, dropped))
                elif packets > busiest[0][0]:
                    heapq.heapreplace(busiest, (packets, count, row, dropped))
            await asyncio.sleep(0)
        top = [
            BurstClient(address=r[0], ntp_packets=packets, ntp_dropped=dropped, ntp_interval=_int(r[3], UNSET_INTERVAL))
            for packets, _, r, dropped in sorted(busiest, reverse=True)
        ]
        nets = sorted(prefixes.items(), key=lambda kv: (kv[1][0], kv[1][1]), reverse=True)[:SCAN_TOP]
        return count, count_v6, top, [BurstPrefix(prefix=p, clients=n, ntp_packets=k) for p, (n, k) in nets], recent

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
            client_count=self.client_count,
            active_clients=self.active_clients,
            active_clients_ipv6=self.active_clients_ipv6,
            ntp_requests_per_s=self.ntp_requests_per_s,
            ntp_dropped_per_s=self.ntp_dropped_per_s,
        )


def _prefix(address: str, v6: bool) -> str:
    """/24 for IPv4, /48 for IPv6: roughly one customer or site."""
    try:
        return str(ipaddress.ip_network(f"{address}/{48 if v6 else 24}", strict=False))
    except ValueError:
        return address


def _is_lan(address: str) -> bool:
    # Cheap prefix test first: ip_address() on every row of a large client log is the slow part.
    if not address.startswith(("10.", "172.", "192.168.", "127.", "fc", "fd", "fe80:", "::1")):
        return False
    try:
        return ipaddress.ip_address(address).is_private
    except ValueError:
        return False

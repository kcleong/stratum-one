"""Host stats. /proc and /sys are host-wide, so this works from a container."""

import socket
from pathlib import Path

from .models import SystemStatus


def _read(path: str) -> str | None:
    try:
        return Path(path).read_text().strip()
    except OSError:
        return None


def _udp_rcvbuf_errors() -> int | None:
    """Receive-buffer drops, IPv4 + IPv6. /proc/net/snmp has a header line and a value line per protocol."""
    total = None
    udp = [line.split()[1:] for line in (_read("/proc/net/snmp") or "").splitlines() if line.startswith("Udp:")]
    if len(udp) == 2:
        total = int(dict(zip(*udp))["RcvbufErrors"])
    for line in (_read("/proc/net/snmp6") or "").splitlines():
        key, _, value = line.partition(" ")
        if key == "Udp6RcvbufErrors":
            total = (total or 0) + int(value)
    return total


def _softnet_dropped() -> int | None:
    """Backlog drops: column 2 (hex) of /proc/net/softnet_stat, one line per CPU."""
    stat = _read("/proc/net/softnet_stat")
    return sum(int(line.split()[1], 16) for line in stat.splitlines()) if stat else None


def snapshot() -> SystemStatus:
    temp = _read("/sys/class/thermal/thermal_zone0/temp")
    load = _read("/proc/loadavg")
    uptime = _read("/proc/uptime")
    meminfo = {}
    for line in (_read("/proc/meminfo") or "").splitlines():
        key, _, value = line.partition(":")
        meminfo[key] = int(value.split()[0]) * 1024
    return SystemStatus(
        hostname=socket.gethostname(),
        cpu_temp_c=int(temp) / 1000 if temp else None,
        load=[float(x) for x in load.split()[:3]] if load else None,
        uptime_s=float(uptime.split()[0]) if uptime else None,
        mem_total_bytes=meminfo.get("MemTotal"),
        mem_available_bytes=meminfo.get("MemAvailable"),
        udp_rcvbuf_errors=_udp_rcvbuf_errors(),
        softnet_dropped=_softnet_dropped(),
    )

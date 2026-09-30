"""Host stats. /proc and /sys are host-wide, so this works from a container."""

import socket
from pathlib import Path


def _read(path: str) -> str | None:
    try:
        return Path(path).read_text().strip()
    except OSError:
        return None


def snapshot() -> dict:
    temp = _read("/sys/class/thermal/thermal_zone0/temp")
    load = _read("/proc/loadavg")
    uptime = _read("/proc/uptime")
    meminfo = {}
    for line in (_read("/proc/meminfo") or "").splitlines():
        key, _, value = line.partition(":")
        meminfo[key] = int(value.split()[0]) * 1024
    return {
        "hostname": socket.gethostname(),
        "cpu_temp_c": int(temp) / 1000 if temp else None,
        "load": [float(x) for x in load.split()[:3]] if load else None,
        "uptime_s": float(uptime.split()[0]) if uptime else None,
        "mem_total_bytes": meminfo.get("MemTotal"),
        "mem_available_bytes": meminfo.get("MemAvailable"),
    }

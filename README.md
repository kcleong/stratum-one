# stratum_one

GPS + PPS disciplined stratum-1 NTP server on a Raspberry Pi 4 (`lobsang`),
run with Docker Compose.

- **gpsd** reads NMEA from the GPS over UART (`/dev/ttyAMA2`) and publishes
  coarse time via shared memory (SHM 0).
- **chrony** uses NMEA to number the seconds and the kernel PPS signal
  (`/dev/pps0`) for the precise edge, then serves NTP on UDP 123.

Expected accuracy: ~1–5 µs local, LAN clients typically < 0.1 ms.

## Hardware / wiring

Use a 3.3 V logic GPS module with a PPS output (e.g. u-blox NEO-M8N).
**Do not connect 5 V logic to the GPIO pins.**

| GPS pin | Pi GPIO | Physical pin | Notes            |
|---------|---------|--------------|------------------|
| VCC     | 3.3 V   | 1            | or 5 V (pin 2) if the module requires 5 V supply (logic still 3.3 V) |
| GND     | GND     | 6            |                  |
| TX      | GPIO1   | 28           | uart2 RX         |
| RX      | GPIO0   | 27           | uart2 TX         |
| PPS     | GPIO18  | 12           | pps-gpio         |

uart2 uses GPIO0/1 (the HAT ID EEPROM pins), so don't combine with a HAT
that has an ID EEPROM. uart2 is a full PL011 UART, unlike the mini UART,
so its baud rate does not depend on the core clock.

Give the antenna a clear sky view; first fix can take several minutes.

## Host setup (manual, once, needs sudo)

1. **Enable UART and PPS** in `/boot/firmware/config.txt`, under `[all]`:
   ```
   enable_uart=1
   dtoverlay=uart2
   dtoverlay=pps-gpio,gpiopin=18
   ```
   (`enable_uart=1` and `uart2` are already present on lobsang.)

2. **No serial console** on the GPS UART: `/boot/firmware/cmdline.txt` must
   not contain `console=serial0,...` or `console=ttyAMA2,...`.

3. **Enable memory cgroup** so `mem_limit` works: append to the single line in
   `/boot/firmware/cmdline.txt`:
   ```
   cgroup_enable=memory
   ```

4. **Disable host chrony** (two NTP daemons fight over the clock):
   ```
   sudo systemctl disable --now chrony
   sudo systemctl mask chrony
   ```

5. **Docker**: install `docker-ce` + `docker-compose-plugin` from
   download.docker.com (Debian trixie, arm64), then keep container logs off
   the SD card (journald is volatile on Pi OS):
   ```
   echo '{ "log-driver": "journald" }' | sudo tee /etc/docker/daemon.json
   sudo systemctl enable --now docker
   sudo usermod -aG docker $USER   # re-login afterwards
   ```

6. **PPS keeps CPU0 to itself**: the PPS timestamp is taken in its hard IRQ on
   CPU0 (chained through the GPIO controller, so it cannot move). Move the eth0
   IRQs to CPU2:
   ```
   sudo cp host/eth0-irq-affinity.service /etc/systemd/system/
   sudo systemctl enable --now eth0-irq-affinity
   ```

7. **Reboot**, then verify:
   ```
   ls -l /dev/pps0 /dev/ttyAMA2
   grep -E "eth0|pps" /proc/interrupts      # eth0 counts grow on CPU2, pps on CPU0
   grep memory /sys/fs/cgroup/cgroup.controllers
   sudo apt install pps-tools && sudo ppstest /dev/pps0   # one line per second once GPS has a fix
   ```

## Run

```
docker compose up -d --build
docker compose logs -f
```

Containers restart automatically on boot (`restart: unless-stopped`).

To redeploy only the api (dashboard or API changes) without touching chronyd:
```
docker compose up -d --build --no-deps api
```

## Check

```
docker compose exec chrony chronyc sources -v     # PPS should show '*' after a few minutes
docker compose exec chrony chronyc sourcestats
docker compose exec chrony chronyc tracking       # RMS offset: a few µs
docker compose exec chrony chronyc clients        # who is querying
```

### Tune the NMEA offset

NMEA sentences arrive late by a module-specific amount. After ~1 h with a
fix, look at the `GPS` line in `chronyc sourcestats` (Offset column) and
set `offset` in `chrony.conf` so the GPS offset is near 0 relative to PPS.
Then `docker compose restart chrony`.

## Stats API and Home Assistant

The `api` service (FastAPI, `api/`) serves GPS and chrony stats on port 8000
and optionally publishes them to MQTT with Home Assistant discovery.
Python 3.14, dependencies in `api/pyproject.toml` locked with uv
(`api/uv.lock`); the image is built on `ghcr.io/astral-sh/uv:python3.14-alpine`.
After changing dependencies run `uv lock` in `api/`.

- Interactive docs: `http://lobsang.local:8000/docs` (OpenAPI at `/openapi.json`)
- `GET /api/status`: everything below in one document
- `GET /api/gps`, `/api/gps/satellites`: fix, DOPs, per-satellite az/el/SNR
- `GET /api/gps/sky`: sky coverage, average SNR and share received per
  10° x 10° patch over the last `SKY_HOURS` (24), sampled every 30 s
- `GET /api/chrony`, `/api/chrony/clients`: tracking, sources, sourcestats,
  serverstats, clients (busiest 50 plus LAN, with country and provider from the
  [DB-IP](https://db-ip.com) Lite databases, CC BY 4.0, downloaded monthly to `GEOIP_DIR`)
- `GET /api/chrony/providers`: top 10 networks (ASN) of all public clients
  active in the last hour
- `GET /api/system`: CPU temperature, load, uptime, memory
- `GET /api/history?minutes=60`: offsets, frequency, satellites,
  temperature and NTP request rate; raw 5 s samples up to 24 h, bucket
  averages with offset min/max up to 30 days (see History below)
- `GET /api/pool?minutes=60`: NTP Pool score history of `POOL_SERVERS` (see
  NTP Pool score below)
- `WS /api/ws?interval=1`: pushes `/api/status` every second
- `GET /healthz`: 503 when gpsd or chronyd is unreachable

Offsets are in seconds. `system_time_offset_s` is positive when the clock is
ahead; `frequency_ppm` is positive when the local oscillator runs fast.

chronyc reaches chronyd over `/run/chrony/chronyd.sock`, shared through the
`chrony-run` tmpfs volume. The api container runs as chrony's uid/gid
(100:101), read-only and without capabilities.

**History**: the last `HISTORY_HOURS` (24) are kept in memory at full 5 s
resolution; everything is saved to SQLite (`api-data` volume,
`/data/history.db`) in one transaction every `HISTORY_FLUSH_MINUTES` (15) and
on shutdown, so restarts and deploys keep it; a power cut loses at most one
interval. Rows older than `HISTORY_DAYS` (30) are pruned, so the database
levels off at ~45 MiB and does not grow further; writes are ~5 MiB/day
regardless of retention. Ranges over 24 h are served as ≤ ~1500 bucket
averages with offset min/max (finished buckets are cached). Long-term history
lives in Home Assistant's recorder via MQTT.

**NTP Pool score**: set `POOL_SERVERS` in `.env` to the addresses registered
in the pool (comma-separated, e.g. `POOL_SERVERS=192.0.2.10,2001:db8::123`).
Every `POOL_INTERVAL` seconds (900) the api fetches each address's overall
score (the pool's "recentmedian" of its monitors) from
`https://www.ntppool.org/scores/<address>/json` and keeps it for
`HISTORY_DAYS` in the same SQLite file. Leave it unset to disable; the
dashboard then hides the chart.

**Traffic bursts**: when the NTP load reaches `BURST_REQ_S` (100 req/s), the
api scans chronyd's client log for the addresses active in the last 60 s:
the busiest ones, the /24 and /48 networks with the most addresses, and their
providers (with `GEOIP_DIR`). It rescans while the burst lasts (every minute
at first, then less often, at most every 10 min) until the load falls below
half the threshold or chronyd restarts, records requests and rate-limit drops
during the burst, and keeps each burst for `HISTORY_DAYS` (`GET /api/bursts`,
the dashboard's Traffic bursts card). Drops per second are charted with the NTP
load. Set `BURST_REQ_S=0` to turn the scans off.

The API has no authentication and shows the GPS position and NTP client
addresses; keep port 8000 on the LAN.

### Dashboard

`http://lobsang.local:8000/`: live UTC clock, lock/fix status, history charts
of offsets, frequency, satellites, temperature, NTP load and pool score
(1 h to 30 d, ctrl+scroll or pinch to zoom), sky
plot (live satellites, or a 24 h coverage map showing where the antenna's
view is open or blocked), signal strength per satellite, chrony sources, NTP clients (busiest 10),
top client providers and host
stats. Vue 3 + ECharts in `web/`, built into the api image by the first
stage of `api/Dockerfile` (no Node needed on the host).

Develop on another machine with the API still on the Pi:

```
cd web
npm install
npm run dev            # http://localhost:5173, proxies /api to lobsang.local:8000
npm run gen:api        # regenerate src/api/schema.d.ts after API model changes
```

Set `API_TARGET=http://<ip>:8000` if `lobsang.local` doesn't resolve.

### MQTT

```
cp .env.example .env   # set MQTT_HOST (an IP), MQTT_USER, MQTT_PASSWORD
docker compose up -d api
```

The device `lobsang` appears in Home Assistant under MQTT with sensors for
fix, satellites, stratum, offsets (µs), frequency, NTP clients and CPU
temperature, plus "PPS locked". State is published every 10 s to
`stratum_one/lobsang/state`; discovery is resent when HA restarts.

## Clients

Point clients at the Pi, e.g. for chrony:
```
server lobsang.local iburst prefer
```
or for systemd-timesyncd (`/etc/systemd/timesyncd.conf`): `NTP=lobsang.local`.

`chrony.conf` answers any client (set up for the public NTP Pool, with `ratelimit` and a bounded
`clientloglimit`); what can reach UDP 123 is decided by the router. For a LAN-only server,
restrict it with `allow <your LAN>/24`.

## Notes

- **Docker does not hurt timing**: PPS is timestamped in the kernel IRQ,
  `network_mode: host` avoids NAT, no CPU limits are set, and
  `SYS_NICE`/`IPC_LOCK` allow real-time priority and locked memory.
- **Load and temperature**: sustained 100 % CPU load heats the SoC and shifts
  the crystal frequency, causing µs-level wander. Avoid long full-load jobs
  next to this; keep cooling steady.
- **Boot**: the Pi 4 has no RTC. Until Docker starts, the clock runs from the
  last saved time; `makestep 1 3` corrects it on the first updates.
- **No `CAP_SYS_TIME` elsewhere**: never run another time daemon in other
  containers.

## License

MIT, see [LICENSE](LICENSE).

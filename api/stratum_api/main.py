import asyncio
import contextlib
import logging
from pathlib import Path

from fastapi import FastAPI, Query, Response, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from pydantic import TypeAdapter

from .config import load_settings
from .models import (
    ChronyStatus,
    Client,
    GpsStatus,
    Health,
    HistoryPoint,
    HistorySample,
    Satellite,
    Status,
    SystemStatus,
)
from .monitor import Monitor
from .mqtt import MqttPublisher

log = logging.getLogger(__name__)
HISTORY_RAW_JSON = TypeAdapter(list[HistorySample])
HISTORY_BUCKET_JSON = TypeAdapter(list[HistoryPoint])
MAX_HISTORY_MINUTES = 30 * 24 * 60
STATIC_DIR = Path(__file__).parent.parent / "static"   # web UI, built by the Dockerfile web stage


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    settings = load_settings()
    monitor = Monitor(settings)
    app.state.monitor = monitor
    tasks = [
        asyncio.create_task(monitor.gps.run()),
        asyncio.create_task(monitor.run_chrony()),
        asyncio.create_task(monitor.run_flush()),
    ]
    if settings.mqtt_host:
        tasks.append(asyncio.create_task(MqttPublisher(settings, monitor).run()))
    else:
        log.info("MQTT_HOST not set, MQTT publishing disabled")
    yield
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    await monitor.flush()   # keep everything since the last flush across restarts
    monitor.close()


app = FastAPI(title="stratum_one", summary="GPS and NTP stats for the stratum-1 server", lifespan=lifespan)


def _monitor() -> Monitor:
    return app.state.monitor


@app.get("/api/status", summary="Everything: GPS, chrony and host stats")
def status() -> Status:
    return _monitor().snapshot()


@app.get("/api/gps", summary="GPS fix, DOPs and satellites")
def gps() -> GpsStatus:
    return _monitor().gps.snapshot()


@app.get("/api/gps/satellites", summary="Satellites in view")
def satellites() -> list[Satellite]:
    return _monitor().gps.snapshot().satellites


@app.get("/api/chrony", summary="chrony tracking, sources, sourcestats, serverstats")
def chrony() -> ChronyStatus:
    return _monitor().chrony.snapshot()


@app.get("/api/chrony/clients", summary="NTP clients seen by chrony")
def clients() -> list[Client]:
    return _monitor().chrony.clients


@app.get("/api/system", summary="Host temperature, load, uptime, memory")
def system() -> SystemStatus:
    return _monitor().snapshot().system


@app.get(
    "/api/history",
    summary="Time series of offsets, frequency, satellites and temperature",
    description=(
        "Up to HISTORY_HOURS (24 h): raw 5 s samples. Longer, up to HISTORY_DAYS (30 d): bucket "
        "averages of at most ~1500 points with offset min/max. The `X-History-Bucket-Seconds` "
        "header gives the resolution."
    ),
    response_model=list[HistoryPoint],
)
async def history(minutes: float = Query(60, gt=0, le=MAX_HISTORY_MINUTES)) -> Response:
    # Samples are already validated models; dumping them directly skips FastAPI's
    # response re-validation, which costs ~2 s of CPU for a full 24 h on the Pi.
    monitor = _monitor()
    seconds = min(minutes * 60, monitor.settings.history_days * 86400)
    if seconds <= monitor.memory_window_s:
        body = HISTORY_RAW_JSON.dump_json(monitor.history_since(seconds))
        bucket = monitor.settings.chrony_interval
    else:
        bucket, points = await monitor.history_buckets(seconds)
        body = HISTORY_BUCKET_JSON.dump_json(points)
    return Response(body, media_type="application/json", headers={"X-History-Bucket-Seconds": f"{bucket:g}"})


@app.get(
    "/healthz",
    summary="200 when gpsd and chrony are reachable, else 503",
    responses={503: {"model": Health, "description": "gpsd or chronyd unreachable"}},
)
def healthz(response: Response) -> Health:
    monitor = _monitor()
    health = Health(gpsd=monitor.gps.connected, chrony=monitor.chrony.error is None)
    if not (health.gpsd and health.chrony):
        response.status_code = 503
    return health


@app.websocket("/api/ws")
async def ws(websocket: WebSocket, interval: float = 1.0) -> None:
    """Pushes a `Status` document (as /api/status) every `interval` seconds (min 0.5)."""
    await websocket.accept()
    try:
        while True:
            await websocket.send_text(_monitor().snapshot().model_dump_json())
            await asyncio.sleep(max(interval, 0.5))
    except WebSocketDisconnect:
        pass


if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="ui")

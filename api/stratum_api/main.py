import asyncio
import contextlib
import logging
from pathlib import Path

from fastapi import FastAPI, Query, Response, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from .config import load_settings
from .models import ChronyStatus, Client, GpsStatus, Health, HistorySample, Satellite, Status, SystemStatus
from .monitor import Monitor
from .mqtt import MqttPublisher

log = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).parent.parent / "static"   # web UI, once it exists


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    settings = load_settings()
    monitor = Monitor(settings)
    app.state.monitor = monitor
    tasks = [asyncio.create_task(monitor.gps.run()), asyncio.create_task(monitor.run_chrony())]
    if settings.mqtt_host:
        tasks.append(asyncio.create_task(MqttPublisher(settings, monitor).run()))
    else:
        log.info("MQTT_HOST not set, MQTT publishing disabled")
    yield
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


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


@app.get("/api/history", summary="Time series of offsets, frequency, satellites and temperature")
def history(minutes: float = Query(60, gt=0, le=24 * 60)) -> list[HistorySample]:
    return _monitor().history_since(minutes * 60)


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

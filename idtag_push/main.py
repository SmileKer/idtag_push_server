import asyncio
import hmac
import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Request, status

from .config import Settings, get_settings
from .db import Database
from .providers import APNSProvider, DryRunProvider, FCMProvider, UnavailableProvider
from .repository import Repository
from .schemas import (
    DeviceRegistration,
    DeviceRegistrationResponse,
    DeviceUnregister,
    PushRequest,
    PushResponse,
)
from .socket_server import SocketServer
from .worker import PushWorker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


def require_api_key(request: Request, x_api_key: str = Header(default="")) -> None:
    settings: Settings = request.app.state.settings
    if not hmac.compare_digest(x_api_key, settings.api_key.get_secret_value()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid API key")


def build_providers(settings: Settings, client: httpx.AsyncClient) -> dict[str, object]:
    if settings.dry_run:
        provider = DryRunProvider()
        return {"ios": provider, "android": provider}

    providers: dict[str, object] = {
        "android": UnavailableProvider("FCM"),
        "ios": UnavailableProvider("APNs"),
    }
    if settings.fcm_project_id and settings.fcm_service_account_file:
        fcm_provider = FCMProvider(
            settings.fcm_project_id,
            settings.fcm_service_account_file,
            client,
        )
        providers["android"] = fcm_provider
        # Firebase forwards iOS messages to APNs when the APNs key is uploaded
        # in Firebase Console, so one service account can serve both platforms.
        providers["ios"] = fcm_provider
    if all([settings.apns_team_id, settings.apns_key_id, settings.apns_key_file, settings.apns_topic]):
        providers["ios"] = APNSProvider(
            settings.apns_team_id,
            settings.apns_key_id,
            settings.apns_key_file,
            settings.apns_topic,
            settings.apns_use_sandbox,
            client,
        )  # type: ignore[arg-type]
    return providers


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    database = Database(settings.database_url)
    await database.connect()
    await database.migrate()
    repository = Repository(database.require_pool())
    http_client = httpx.AsyncClient(http2=True, timeout=15)
    worker = PushWorker(
        repository,
        build_providers(settings, http_client),
        settings.worker_poll_seconds,
        settings.max_attempts,
    )
    socket_server = SocketServer(
        settings.socket_host,
        settings.socket_port,
        settings.socket_secret.get_secret_value(),
        repository.enqueue,
    )
    await socket_server.start()
    worker_task = asyncio.create_task(worker.run(), name="push-worker")
    app.state.settings, app.state.repository = settings, repository
    try:
        yield
    finally:
        worker.stop()
        await worker_task
        await socket_server.close()
        await http_client.aclose()
        await database.close()


app = FastAPI(title="IDTag Push Service", version="1.0.0", lifespan=lifespan)


@app.get("/health")
async def health(request: Request) -> dict[str, str]:
    await request.app.state.repository.pool.fetchval("SELECT 1")
    return {"status": "ok"}


@app.post("/v1/devices", response_model=DeviceRegistrationResponse, dependencies=[Depends(require_api_key)])
async def register_device(payload: DeviceRegistration, request: Request) -> DeviceRegistrationResponse:
    device_id = await request.app.state.repository.register_device(
        payload.community_code,
        payload.card_number,
        payload.platform,
        payload.push_token,
    )
    return DeviceRegistrationResponse(device_id=device_id)


@app.delete("/v1/devices", dependencies=[Depends(require_api_key)])
async def unregister_device(payload: DeviceUnregister, request: Request) -> dict[str, bool]:
    deleted = await request.app.state.repository.unregister_device(payload.platform, payload.push_token)
    return {"deleted": deleted}


@app.post("/v1/push", response_model=PushResponse, dependencies=[Depends(require_api_key)])
async def enqueue_push(payload: PushRequest, request: Request) -> PushResponse:
    try:
        notification_id, count = await request.app.state.repository.enqueue(
            payload.community_code,
            payload.card_number,
            payload.title,
            payload.body,
            payload.data,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return PushResponse(notification_id=notification_id, target_count=count)

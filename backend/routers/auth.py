"""Authentication endpoints for Plex OAuth PIN login."""

import asyncio
import logging
import os
import pathlib
import secrets

from fastapi import APIRouter, Header, HTTPException, BackgroundTasks
from plexapi.myplex import MyPlexAccount, MyPlexPinLogin
from pydantic import BaseModel

from backend.config import settings
from backend.services.plex import (
    get_plex_connection,
    pre_warm_all_caches,
    reinitialize_plex,
    fetch_accessible_plex_servers,
    get_enabled_server_ids,
    set_enabled_server_ids,
    _plex_connection_cache,
    _failed_connection_cache,
)
from backend.services.redis import cache_data, get_cached_data
from backend.services.indexer import sync_all_servers
from backend.db.library_db import get_db_connection
from backend.websockets import send_indexing_status, broadcast_json_threadsafe
from backend import websockets as ws

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Store active PIN login handlers in memory
active_pins = {}

MOCK_PIN_ID = 9999
MOCK_TOKEN = "mock_token_12345"  # noqa: S105


def resolve_env_write_path() -> pathlib.Path:
    """Resolve the .env file path for persisting settings."""
    data_dir = settings.data_dir or os.getenv("DATA_DIR", "").strip()
    if data_dir:
        dir_path = pathlib.Path(data_dir)
        dir_path.mkdir(parents=True, exist_ok=True)
        return dir_path / ".env"
    app_env = pathlib.Path("/app/.env")
    if app_env.exists():
        return app_env
    return pathlib.Path(".env")


def write_settings_to_env(
    token: str,
    server_name: str,
    client_name: str,
    plex_username: str = "",
    admin_token: str = "",
    instance_name: str = "",
):
    """Write settings back to the .env file."""
    try:
        path_obj = resolve_env_write_path()
        content = path_obj.read_text(encoding="utf-8") if path_obj.exists() else ""
        lines = content.splitlines()

        updates = {
            "PLEX_TOKEN": token,
            "PLEX_SERVER_NAME": server_name,
            "CLIENT_NAME": client_name,
            "PLEX_USERNAME": plex_username,
            "ADMIN_TOKEN": admin_token or settings.admin_token,
            "INSTANCE_NAME": instance_name or settings.instance_name,
        }

        new_lines = []
        for line in lines:
            line_key = line.split("=", 1)[0].strip() if "=" in line else ""
            if line_key in updates:
                new_lines.append(f"{line_key}={updates.pop(line_key)}")
            else:
                new_lines.append(line)

        for key, val in updates.items():
            new_lines.append(f"{key}={val}")

        path_obj.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        logger.info("Successfully updated settings in env file.")
    except Exception:
        logger.exception("Failed to write settings to .env file.")


def write_token_to_env(token: str):
    """Write the Plex authToken back to the .env file."""
    write_settings_to_env(
        token,
        settings.plex_server_name,
        settings.client_name,
        settings.plex_username,
        settings.admin_token,
        settings.instance_name,
    )


@router.get("/status")
async def status():
    """Retrieve the current connection and authentication status."""
    # Testing-mode bypass: if mock setup was already completed (admin_token is set),
    # skip the wizard and return a fully authenticated mock state. This lets developers
    # do day-to-day work without re-running the wizard on every reload.
    # Fresh starts (empty admin_token) still show the wizard so the flow can be tested.
    if settings.testing and settings.admin_token:
        return {
            "authenticated": True,
            "username": settings.plex_username or "MockUser",
            "plex_server_name": settings.plex_server_name or "[Mock] Local Jukebox Server",
            "client_name": settings.client_name or "Mock Jukebox",
            "instance_name": settings.instance_name,
            "is_configured": True,
            "testing": True,
        }

    is_configured = bool(
        settings.plex_token and settings.plex_server_name and settings.client_name
    ) or bool(
        settings.plex_username
        and settings.plex_password
        and settings.plex_server_name
        and settings.client_name
    )

    if not settings.plex_token and not (
        settings.plex_username and settings.plex_password
    ):
        return {
            "authenticated": False,
            "username": "",
            "plex_server_name": settings.plex_server_name,
            "client_name": settings.client_name,
            "instance_name": settings.instance_name,
            "is_configured": is_configured,
            "testing": settings.testing,
        }
    username = settings.plex_username
    if not username and settings.plex_token and not settings.testing:
        try:
            account = MyPlexAccount(token=settings.plex_token)
            username = account.username
            if username:
                settings.plex_username = username
                write_settings_to_env(
                    settings.plex_token,
                    settings.plex_server_name,
                    settings.client_name,
                    username,
                    settings.admin_token,
                    settings.instance_name,
                )
        except Exception as ex:  # noqa: BLE001
            logger.debug("Failed fetching MyPlexAccount username: %s", ex)
            try:
                plex = get_plex_connection()
                username = plex.myPlexAccount().username
                if username:
                    settings.plex_username = username
            except Exception as ex2:  # noqa: BLE001
                logger.debug("Failed fetching plex connection username: %s", ex2)

    final_username = username or settings.plex_username or "Plex User"
    return {
        "authenticated": True,
        "plex_username": final_username,
        "plex_server_name": settings.plex_server_name,
        "client_name": settings.client_name,
        "instance_name": settings.instance_name,
        "is_configured": is_configured,
        "testing": settings.testing,
    }


@router.post("/pin")
async def request_pin(simulate: bool = False):
    """Request a new login PIN from Plex or start a simulation session."""
    if simulate and not settings.testing:
        raise HTTPException(
            status_code=400,
            detail="Simulation mode is only allowed when testing is enabled.",
        )

    if settings.testing or simulate:
        code = "MOCK"
        url = "http://localhost/api/auth/mock-claim"
        cache_data(
            "mock_pin_active",
            {"pin_id": MOCK_PIN_ID, "code": code, "authorized": False},
        )
        return {"pin_id": MOCK_PIN_ID, "code": code, "url": url}

    try:
        pinlogin = MyPlexPinLogin(oauth=False)
        # Accessing the .pin property fetches the code from Plex.tv and populates self._id.
        # We run this in a threadpool since it performs a blocking HTTP request.
        code = await asyncio.to_thread(lambda: pinlogin.pin)
        active_pins[pinlogin._id] = pinlogin
        active_pins[str(pinlogin._id)] = pinlogin
        logger.debug(
            "Stored PIN ID: %s (type: %s) in active_pins. Current keys: %s",
            pinlogin._id,
            type(pinlogin._id),
            list(active_pins.keys()),
        )
        return {
            "pin_id": pinlogin._id,
            "code": code,
            "url": "https://plex.tv/link",
        }
    except Exception as e:
        logger.exception("Plex PIN request failed.")
        raise HTTPException(
            status_code=502, detail="Failed to connect to Plex authentication servers."
        ) from e


@router.get("/check")
async def check_pin(pin_id: int):
    """Check if the PIN has been claimed/authorized by the user."""
    logger.debug(
        "Checking PIN ID: %s (type: %s). Current keys in active_pins: %s",
        pin_id,
        type(pin_id),
        list(active_pins.keys()),
    )
    if pin_id == MOCK_PIN_ID:
        if settings.testing:
            settings.plex_token = MOCK_TOKEN
            settings.plex_username = "MockUser"
            write_token_to_env(MOCK_TOKEN)
            get_plex_connection.cache_clear()
            return {"authenticated": True, "token": MOCK_TOKEN}

        mock_data = get_cached_data("mock_pin_active")
        if mock_data and mock_data.get("authorized"):
            settings.plex_token = MOCK_TOKEN
            settings.plex_username = "MockUser"
            write_token_to_env(MOCK_TOKEN)
            get_plex_connection.cache_clear()
            return {"authenticated": True, "token": MOCK_TOKEN}
        return {"authenticated": False}

    pinlogin = active_pins.get(str(pin_id)) or active_pins.get(pin_id)
    if not pinlogin:
        raise HTTPException(status_code=404, detail="PIN session not found or expired.")

    authorized = await asyncio.to_thread(pinlogin.checkLogin)
    if authorized:
        token = pinlogin.token
        settings.plex_token = token

        try:
            account = MyPlexAccount(token=token)
            if account.username:
                settings.plex_username = account.username
        except Exception:  # noqa: BLE001
            settings.plex_username = settings.plex_username or "Plex User"

        write_token_to_env(token)
        reinitialize_plex()
        active_pins.pop(str(pin_id), None)
        active_pins.pop(pin_id, None)

        return {
            "authenticated": True,
            "token": token,
            "plex_username": settings.plex_username,
        }

    return {"authenticated": False}


@router.get("/mock-claim")
@router.post("/mock-claim")
async def mock_claim():
    """Simulate a successful login authorization for offline testing."""
    if not settings.testing:
        raise HTTPException(
            status_code=400,
            detail="Simulation mode is only allowed when testing is enabled.",
        )
    mock_data = get_cached_data("mock_pin_active")
    if not mock_data:
        raise HTTPException(
            status_code=404, detail="No active simulated PIN request found."
        )

    mock_data["authorized"] = True
    cache_data("mock_pin_active", mock_data)
    return {"message": "Simulated PIN authorized successfully!"}


def fetch_and_cache_resources(refresh: bool = False):
    """Fetch list of available Plex Media Servers and Player Clients, caching results in Redis."""
    cache_key = "plex_resources"

    if not refresh:
        cached = get_cached_data(cache_key)
        if cached:
            logger.info("Fetched Plex resources from Redis cache.")
            return cached

    if settings.plex_token == MOCK_TOKEN or not settings.plex_token:
        mock_data = {
            "servers": ["[Mock] Local Jukebox Server", "[Mock] Home NAS"],
            "players": ["[Mock] Living Room Plexamp", "[Mock] Kitchen Speaker"],
        }
        cache_data(cache_key, mock_data, ttl=180)
        return mock_data

    try:
        account = MyPlexAccount(token=settings.plex_token)
        servers = []
        players = []
        for resource in account.resources():
            provides = resource.provides.lower() if resource.provides else ""
            if "server" in provides:
                servers.append(resource.name)
            if "player" in provides or "client" in provides or "controller" in provides:
                players.append(resource.name)

        resources_data = {
            "servers": sorted(set(servers)),
            "players": sorted(set(players)),
        }
        cache_data(cache_key, resources_data, ttl=180)
        return resources_data
    except Exception as e:
        logger.exception("Failed to query Plex resources")
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch resources from Plex: {e}"
        ) from e


@router.get("/resources")
async def get_resources(refresh: bool = False):
    """Get list of available Plex Media Servers and Player Clients."""
    return fetch_and_cache_resources(refresh=refresh)


class ConfigurationRequest(BaseModel):
    """Pydantic model representing Plex Server and Player Client onboarding configurations."""

    plex_username: str
    client_name: str
    plex_server_name: str
    instance_name: str = "TuneBox"


@router.post("/configure")
async def configure_resources(req: ConfigurationRequest):
    """Save selected Plex Server and Client Player to .env and settings."""
    token = settings.admin_token or secrets.token_hex(16)
    settings.admin_token = token
    settings.plex_username = req.plex_username
    settings.client_name = req.client_name
    settings.plex_server_name = req.plex_server_name
    settings.instance_name = req.instance_name

    write_settings_to_env(
        settings.plex_token,
        req.plex_server_name,
        req.client_name,
        req.plex_username,
        admin_token=token,
        instance_name=req.instance_name,
    )

    reinitialize_plex()
    if not settings.testing:
        set_enabled_server_ids([req.plex_server_name])
        asyncio.create_task(asyncio.to_thread(sync_all_servers))

    return {
        "message": "Configuration successfully saved and reinitialized!",
        "admin_token": token,
    }


class SettingsUpdateRequest(BaseModel):
    """Schema for settings modifications request payload."""

    plex_username: str
    client_name: str
    plex_server_name: str
    instance_name: str = "TuneBox"


@router.get("/settings")
async def get_settings(x_admin_token: str | None = Header(None)):
    """Fetch current instance config settings."""
    if not settings.admin_token or x_admin_token != settings.admin_token:
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid admin token")
    return {
        "plex_username": settings.plex_username,
        "client_name": settings.client_name,
        "plex_server_name": settings.plex_server_name,
        "instance_name": settings.instance_name,
    }


@router.post("/settings")
async def update_settings(
    req: SettingsUpdateRequest,
    background_tasks: BackgroundTasks,
    x_admin_token: str | None = Header(None),
):
    """Save updated connection/instance settings live."""
    if not settings.admin_token or x_admin_token != settings.admin_token:
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid admin token")

    settings.plex_username = req.plex_username
    settings.client_name = req.client_name
    settings.plex_server_name = req.plex_server_name
    settings.instance_name = req.instance_name

    write_settings_to_env(
        settings.plex_token,
        req.plex_server_name,
        req.client_name,
        req.plex_username,
        settings.admin_token,
        req.instance_name,
    )
    reinitialize_plex()

    # Trigger pre-warming task in background
    background_tasks.add_task(pre_warm_all_caches)


class LibrariesToggleRequest(BaseModel):
    enabled_server_ids: list[str]


@router.get("/libraries")
async def get_libraries():
    """Get list of accessible Plex servers with enabled state for unified catalog (fast 0.5ms return)."""
    servers = await asyncio.to_thread(fetch_accessible_plex_servers)
    enabled_set = {str(x).lower() for x in get_enabled_server_ids()}

    results = []
    for s in servers:
        s_id_raw = s.get("server_id")
        s_id_lower = str(s_id_raw or "").lower()
        s_name_lower = s.get("name", "").lower()
        is_enabled = s_id_lower in enabled_set or s_name_lower in enabled_set

        if not is_enabled:
            status = "disabled"
            error_msg = None
        elif s.get("is_primary") or settings.testing or s_id_raw in _plex_connection_cache:
            status = "connected"
            error_msg = None
        elif s_id_raw in _failed_connection_cache:
            status = "offline"
            error_msg = "Remote server unreachable"
        else:
            status = "connected"
            error_msg = None

        results.append({
            **s,
            "enabled": is_enabled,
            "status": status,
            "error": error_msg,
        })

    return results


@router.post("/libraries")
async def update_libraries(
    req: LibrariesToggleRequest,
    x_admin_token: str | None = Header(None),
):
    """Toggle enabled servers for the unified catalog and trigger indexing."""
    if not settings.admin_token or x_admin_token != settings.admin_token:
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid admin token")
    set_enabled_server_ids(req.enabled_server_ids)

    # Emit indexing status start for newly enabled servers right from the main event loop
    try:
        all_servers = fetch_accessible_plex_servers()
        enabled_set = {str(x).lower() for x in req.enabled_server_ids}

        conn = get_db_connection()
        cursor = conn.cursor()

        for s in all_servers:
            s_id = s.get("server_id")
            s_name = s.get("name", "Plex")
            if s_id and str(s_id).lower() in enabled_set:
                cursor.execute("SELECT COUNT(*) FROM tracks WHERE server_id = ?;", (s_id,))
                count = cursor.fetchone()[0]
                if count == 0:
                    await send_indexing_status(is_indexing=True, is_initial=True, server_name=s_name)
        conn.close()
    except Exception as ex:
        logger.debug("Failed emitting instant indexing status start: %s", ex)

    # Trigger background indexing for newly enabled servers
    asyncio.create_task(asyncio.to_thread(sync_all_servers))

    # Broadcast WebSocket event to all connected UI clients to trigger live dynamic library re-fetch
    try:
        broadcast_json_threadsafe({"type": "server_settings_updated", "enabled_server_ids": req.enabled_server_ids})
    except Exception as ws_ex:
        logger.debug("Failed sending server_settings_updated WS broadcast: %s", ws_ex)

    return {"message": "Enabled libraries updated successfully", "enabled_server_ids": req.enabled_server_ids}


def _is_nickname_taken(username: str, exclude_client_id: str | None = None) -> bool:
    """Return True if the nickname is already used by another connected client or the host admin."""
    target = username.strip().lower()
    if not target:
        return False
    if settings.plex_username and target == settings.plex_username.strip().lower():
        return True
    for cid, info in ws.client_registry.items():
        if exclude_client_id and cid == exclude_client_id:
            continue
        existing_name = str(info.get("name", "")).strip().lower()
        if existing_name and existing_name == target:
            return True
    return False


@router.get("/verify-username")
async def verify_username(username: str, client_id: str | None = None):
    """Verify that a guest nickname is available and not already in use."""
    if not settings.plex_token:
        raise HTTPException(status_code=503, detail="TuneBox not configured yet")

    cleaned = username.strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="Nickname cannot be empty")

    if _is_nickname_taken(cleaned, exclude_client_id=client_id):
        raise HTTPException(status_code=409, detail="Nickname is already in use")

    return {
        "username": cleaned,
        "role": "guest",
    }


@router.get("/clients")
async def get_clients(x_admin_token: str | None = Header(None)):
    """Get active connected client sessions. Requires admin token."""
    if not settings.admin_token or x_admin_token != settings.admin_token:
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid admin token")

    return [{"client_id": cid, **info} for cid, info in ws.client_registry.items()]


@router.post("/clients/{client_id}/set-display")
async def set_client_display(client_id: str, x_admin_token: str | None = Header(None)):
    """Designate a client session as a shared display. Requires admin token."""
    if not settings.admin_token or x_admin_token != settings.admin_token:
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid admin token")

    if client_id not in ws.client_registry:
        raise HTTPException(status_code=404, detail="Client not found")

    ws.client_registry[client_id]["is_display"] = True
    await ws.send_to_client_id(client_id, {"type": "set_display_mode"})
    return {"message": f"Client {client_id} set as shared display"}


@router.post("/clients/{client_id}/unset-display")
async def unset_client_display(client_id: str, x_admin_token: str | None = Header(None)):
    """Remove designation as a shared display. Requires admin token."""
    if not settings.admin_token or x_admin_token != settings.admin_token:
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid admin token")

    if client_id not in ws.client_registry:
        raise HTTPException(status_code=404, detail="Client not found")

    ws.client_registry[client_id]["is_display"] = False
    await ws.send_to_client_id(client_id, {"type": "unset_display_mode"})
    return {"message": f"Client {client_id} display mode removed"}


@router.post("/clients/{client_id}/set-admin")
async def set_client_admin(client_id: str, x_admin_token: str | None = Header(None)):
    """Grant admin privileges to a connected client session. Requires admin token."""
    if not settings.admin_token or x_admin_token != settings.admin_token:
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid admin token")

    if client_id not in ws.client_registry:
        raise HTTPException(status_code=404, detail="Client not found")

    ws.client_registry[client_id]["role"] = "admin"
    await ws.send_to_client_id(
        client_id,
        {
            "type": "set_admin_mode",
            "admin_token": settings.admin_token,
            "plex_username": settings.plex_username,
        },
    )
    return {"message": f"Client {client_id} granted admin access"}


@router.post("/clients/{client_id}/unset-admin")
async def unset_client_admin(client_id: str, x_admin_token: str | None = Header(None)):
    """Revoke admin privileges from a connected client session. Requires admin token."""
    if not settings.admin_token or x_admin_token != settings.admin_token:
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid admin token")

    if client_id not in ws.client_registry:
        raise HTTPException(status_code=404, detail="Client not found")

    ws.client_registry[client_id]["role"] = "guest"
    await ws.send_to_client_id(client_id, {"type": "unset_admin_mode"})
    return {"message": f"Client {client_id} admin access removed"}


class RenameClientRequest(BaseModel):
    name: str


@router.post("/clients/{client_id}/rename")
async def rename_client(client_id: str, req: RenameClientRequest, x_admin_token: str | None = Header(None)):
    """Rename a connected client session. Requires admin token."""
    if not settings.admin_token or x_admin_token != settings.admin_token:
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid admin token")

    if client_id not in ws.client_registry:
        raise HTTPException(status_code=404, detail="Client not found")

    new_name = req.name.strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="Nickname cannot be empty")

    if _is_nickname_taken(new_name, exclude_client_id=client_id):
        raise HTTPException(status_code=409, detail="Nickname is already in use")

    ws.client_registry[client_id]["name"] = new_name
    await ws.send_to_client_id(client_id, {"type": "rename_client", "name": new_name})
    return {"message": f"Client {client_id} renamed to {new_name}"}


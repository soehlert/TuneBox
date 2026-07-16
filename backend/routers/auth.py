"""Authentication endpoints for Plex OAuth PIN login."""

import asyncio
import logging
import pathlib
import secrets

from fastapi import APIRouter, Header, HTTPException
from plexapi.myplex import MyPlexAccount, MyPlexPinLogin
from pydantic import BaseModel

from backend.config import settings
from backend.services.plex import get_plex_connection, reinitialize_plex
from backend.services.redis import cache_data, get_cached_data
from backend import websockets as ws

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Store active PIN login handlers in memory
active_pins = {}

MOCK_PIN_ID = 9999
MOCK_TOKEN = "mock_token_12345"  # noqa: S105


def write_settings_to_env(
    token: str,
    server_name: str,
    client_name: str,
    plex_username: str = "",
    admin_token: str = "",
):
    """Write settings back to the .env file."""
    env_path = "/app/.env"
    if not pathlib.Path(env_path).exists():
        env_path = ".env"

    try:
        path_obj = pathlib.Path(env_path)
        content = path_obj.read_text(encoding="utf-8") if path_obj.exists() else ""
        lines = content.splitlines()

        updates = {
            "PLEX_TOKEN": token,
            "PLEX_SERVER_NAME": server_name,
            "CLIENT_NAME": client_name,
            "PLEX_USERNAME": plex_username,
            "ADMIN_TOKEN": admin_token or settings.admin_token,
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
            "is_configured": True,
            "testing": True,
            "admin_token": settings.admin_token,
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
            "is_configured": is_configured,
            "testing": settings.testing,
        }
    try:
        plex = get_plex_connection()
        username = plex.myPlexAccount().username
        return {
            "authenticated": True,
            "username": username,
            "plex_server_name": settings.plex_server_name,
            "client_name": settings.client_name,
            "is_configured": is_configured,
            "testing": settings.testing,
        }
    except Exception:  # noqa: BLE001
        fallback_user = settings.plex_username or "Plex User"
        return {
            "authenticated": True,
            "username": fallback_user,
            "plex_server_name": settings.plex_server_name,
            "client_name": settings.client_name,
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
            settings.plex_username = account.username
        except Exception:  # noqa: BLE001
            settings.plex_username = "Plex User"

        write_token_to_env(token)
        get_plex_connection.cache_clear()
        active_pins.pop(str(pin_id), None)
        active_pins.pop(pin_id, None)

        return {"authenticated": True, "token": token}

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


@router.get("/resources")
async def get_resources():
    """Get list of available Plex Media Servers and Player Clients."""
    if settings.plex_token == MOCK_TOKEN or not settings.plex_token:
        return {
            "servers": ["[Mock] Local Jukebox Server", "[Mock] Home NAS"],
            "players": ["[Mock] Living Room Plexamp", "[Mock] Kitchen Speaker"],
        }

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

        return {"servers": sorted(set(servers)), "players": sorted(set(players))}
    except Exception as e:
        logger.exception("Failed to query Plex resources")
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch resources from Plex: {e}"
        ) from e


class ConfigurationRequest(BaseModel):
    """Pydantic model representing Plex Server and Player Client onboarding configurations."""

    plex_username: str
    client_name: str
    plex_server_name: str


@router.post("/configure")
async def configure_resources(req: ConfigurationRequest):
    """Save selected Plex Server and Client Player to .env and settings."""
    token = settings.admin_token or secrets.token_hex(16)
    settings.admin_token = token
    settings.plex_username = req.plex_username
    settings.client_name = req.client_name
    settings.plex_server_name = req.plex_server_name

    write_settings_to_env(
        settings.plex_token,
        req.plex_server_name,
        req.client_name,
        req.plex_username,
        admin_token=token,
    )

    reinitialize_plex()

    return {
        "message": "Configuration successfully saved and reinitialized!",
        "admin_token": token,
    }


class SettingsUpdateRequest(BaseModel):
    """Schema for settings modifications request payload."""

    plex_username: str
    client_name: str
    plex_server_name: str


@router.get("/settings")
async def get_settings(x_admin_token: str | None = Header(None)):
    """Fetch current instance config settings."""
    if not settings.admin_token or x_admin_token != settings.admin_token:
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid admin token")
    return {
        "plex_username": settings.plex_username,
        "client_name": settings.client_name,
        "plex_server_name": settings.plex_server_name,
    }


@router.post("/settings")
async def update_settings(
    req: SettingsUpdateRequest, x_admin_token: str | None = Header(None)
):
    """Save updated connection/instance settings live."""
    if not settings.admin_token or x_admin_token != settings.admin_token:
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid admin token")

    settings.plex_username = req.plex_username
    settings.client_name = req.client_name
    settings.plex_server_name = req.plex_server_name

    write_settings_to_env(
        settings.plex_token,
        req.plex_server_name,
        req.client_name,
        req.plex_username,
        settings.admin_token,
    )
    reinitialize_plex()

    return {"message": "Settings successfully updated!"}


@router.get("/verify-username")
async def verify_username(username: str):
    """Check if a display name matches a Plex friend or home user of the owner."""
    if not settings.plex_token:
        raise HTTPException(status_code=503, detail="Jukebox not configured yet")

    if settings.testing:
        # In testing mode, treat usernames starting with "friend_" as verified
        is_member = username.lower().startswith("friend_")
        return {
            "username": username,
            "is_member": is_member,
            "role": "member" if is_member else "guest",
        }

    try:
        account = MyPlexAccount(token=settings.plex_token)
        friend_names = {u.username.lower() for u in account.users() if getattr(u, "username", None)}
        home_names = set()
        try:
            for u in account.home().users:
                name = getattr(u, "title", None) or getattr(u, "username", None)
                if name:
                    home_names.add(name.lower())
        except Exception as home_err:
            logger.warning("Failed to fetch Plex Home users: %s", home_err)

        verified_names = friend_names | home_names
        is_member = username.lower() in verified_names
        return {
            "username": username,
            "is_member": is_member,
            "role": "member" if is_member else "guest",
        }
    except Exception as e:
        logger.exception("Failed to look up Plex friends list")
        raise HTTPException(
            status_code=500, detail=f"Failed to verify username: {e}"
        ) from e


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

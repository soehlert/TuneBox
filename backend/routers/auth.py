"""Authentication endpoints for Plex OAuth PIN login."""

import asyncio
import logging
import pathlib

from fastapi import APIRouter, HTTPException
from plexapi.myplex import MyPlexAccount, MyPlexPinLogin

from backend.config import settings
from backend.services.plex import get_plex_connection
from backend.services.redis import cache_data, get_cached_data

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Store active PIN login handlers in memory
active_pins = {}

MOCK_PIN_ID = 9999
MOCK_TOKEN = "mock_token_12345"  # noqa: S105


def write_token_to_env(token: str):
    """Write the Plex authToken back to the .env file."""
    env_path = "/app/.env"
    if not pathlib.Path(env_path).exists():
        env_path = ".env"

    try:
        content = ""
        path_obj = pathlib.Path(env_path)
        if path_obj.exists():
            with path_obj.open(encoding="utf-8") as f:
                content = f.read()

        lines = content.splitlines()
        token_line_found = False
        new_lines = []

        for line in lines:
            if line.strip().startswith("PLEX_TOKEN="):
                new_lines.append(f"PLEX_TOKEN={token}")
                token_line_found = True
            else:
                new_lines.append(line)

        if not token_line_found:
            new_lines.append(f"PLEX_TOKEN={token}")

        with path_obj.open("w", encoding="utf-8") as f:
            f.write("\n".join(new_lines) + "\n")

        logger.info("Successfully persisted PLEX_TOKEN to %s", env_path)
    except Exception:
        logger.exception("Failed to write PLEX_TOKEN to .env")


@router.get("/status")
async def status():
    """Retrieve the current connection and authentication status."""
    if not settings.plex_token and not (settings.plex_username and settings.plex_password):
        return {"authenticated": False, "username": ""}
    try:
        plex = get_plex_connection()
        # MyPlexAccount username retrieval
        username = plex.myPlexAccount().username
        return {"authenticated": True, "username": username}
    except Exception:  # noqa: BLE001
        # Return fallback username if offline but credentials exist
        fallback_user = settings.plex_username or "Plex User"
        return {"authenticated": True, "username": fallback_user}


@router.post("/pin")
async def request_pin(simulate: bool = False):
    """Request a new login PIN from Plex or start a simulation session."""
    if simulate:
        code = "MOCK"
        url = "http://localhost/api/auth/mock-claim"
        cache_data("mock_pin_active", {"pin_id": MOCK_PIN_ID, "code": code, "authorized": False})
        return {"pin_id": MOCK_PIN_ID, "code": code, "url": url}

    try:
        pinlogin = MyPlexPinLogin(oauth=True)
        await asyncio.to_thread(pinlogin.run)
        active_pins[pinlogin.pinId] = pinlogin
        return {
            "pin_id": pinlogin.pinId,
            "code": pinlogin.code,
            "url": pinlogin.oauthUrl()
        }
    except Exception:
        logger.exception("Plex PIN request failed. Falling back to simulation mode.")
        code = "MOCK"
        url = "http://localhost/api/auth/mock-claim"
        cache_data("mock_pin_active", {"pin_id": MOCK_PIN_ID, "code": code, "authorized": False})
        return {"pin_id": MOCK_PIN_ID, "code": code, "url": url}


@router.get("/check")
async def check_pin(pin_id: int):
    """Check if the PIN has been claimed/authorized by the user."""
    if pin_id == MOCK_PIN_ID:
        mock_data = get_cached_data("mock_pin_active")
        if mock_data and mock_data.get("authorized"):
            settings.plex_token = MOCK_TOKEN
            settings.plex_username = "MockUser"
            write_token_to_env(MOCK_TOKEN)
            get_plex_connection.cache_clear()
            return {"authenticated": True, "token": MOCK_TOKEN}
        return {"authenticated": False}

    pinlogin = active_pins.get(pin_id)
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
        active_pins.pop(pin_id, None)

        return {"authenticated": True, "token": token}

    return {"authenticated": False}


@router.post("/mock-claim")
async def mock_claim():
    """Simulate a successful login authorization for offline testing."""
    mock_data = get_cached_data("mock_pin_active")
    if not mock_data:
        raise HTTPException(status_code=404, detail="No active simulated PIN request found.")

    mock_data["authorized"] = True
    cache_data("mock_pin_active", mock_data)
    return {"message": "Simulated PIN authorized successfully!"}

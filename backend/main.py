"""Set up the basics of TuneBox backend."""

import asyncio
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import settings
from backend.routers import music
from backend.websockets import router as websockets_router
from backend.websockets import update_websocket_clients

# Logging configuration
logging.basicConfig(level=logging.DEBUG)
logging.getLogger("urllib3").setLevel(logging.WARNING)

# Initialize the FastAPI backend
app = FastAPI(title="TuneBox API", description="A Jukebox experience, using your local music", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://frontend:80", "http://localhost", "http://localhost:5173", settings.tunebox_url],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(music.router)

app.include_router(websockets_router)


@app.on_event("startup")
async def start_background_tasks():
    """Start background tasks for periodic updates."""
    # We need to assign the async tasks to something otherwise it could get garbage collected, thought that upsets ruff
    # ruff: noqa: F841
    tasks = await asyncio.create_task(update_websocket_clients())


# Root endpoint
@app.get("/", tags=["Root"])
def read_root():
    """Set up our base path.

    Returns:
        A JSON message so you know it worked.
    """
    return {"message": "Welcome to the Tunebox API!"}

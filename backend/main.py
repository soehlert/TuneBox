"""Set up the basics of TuneBox backend."""

import asyncio
import contextlib
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import settings
from backend.routers import auth, music
from backend.websockets import router as websockets_router
from backend.websockets import update_websocket_clients

# Logging configuration
logging.basicConfig(level=logging.DEBUG)
logging.getLogger("urllib3").setLevel(logging.WARNING)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown lifecycle."""
    from backend.services.plex import playback_orchestrator  # noqa: PLC0415

    # Start background tasks
    ws_task = asyncio.create_task(update_websocket_clients())
    orch_task = asyncio.create_task(playback_orchestrator())
    try:
        yield
    finally:
        # Cleanup tasks on shutdown
        ws_task.cancel()
        orch_task.cancel()
        for task in [ws_task, orch_task]:
            with contextlib.suppress(asyncio.CancelledError):
                await task


# Initialize the FastAPI backend
app = FastAPI(
    title="TuneBox API",
    description="A Jukebox experience, using your local music",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://frontend:80", "http://localhost", "http://localhost:5173", settings.tunebox_url],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(music.router)
app.include_router(websockets_router)


# Root endpoint
@app.get("/", tags=["Root"])
def read_root():
    """Set up our base path.

    Returns:
        A JSON message so you know it worked.
    """
    return {"message": "Welcome to the Tunebox API!"}

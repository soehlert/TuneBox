"""Set up the basics of TuneBox backend."""

import asyncio
import contextlib
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import settings
from backend.routers import auth, music, stats
from backend.websockets import router as websockets_router, update_websocket_clients
import backend.websockets
from backend.services.plex import playback_orchestrator, pre_warm_all_caches
from backend.services.library import clean_library_deduplication
from backend.db.library_db import get_db_connection

# Logging configuration
logging.basicConfig(level=logging.DEBUG)
logging.getLogger("urllib3").setLevel(logging.WARNING)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown lifecycle."""
    backend.websockets.main_loop = asyncio.get_running_loop()

    # Start background tasks
    ws_task = asyncio.create_task(update_websocket_clients())
    orch_task = asyncio.create_task(playback_orchestrator())

    # Start periodic library indexer for enabled servers
    from backend.services.indexer import periodic_library_indexer, sync_all_servers  # noqa: PLC0415
    indexer_task = asyncio.create_task(periodic_library_indexer())
    if settings.plex_token and not settings.testing:
        asyncio.create_task(asyncio.to_thread(sync_all_servers))

    # Pre-warm caches asynchronously in a background thread
    clean_library_deduplication()
    asyncio.create_task(asyncio.to_thread(pre_warm_all_caches))

    # Register mDNS zeroconf local discovery (tunebox.local)
    from backend.services.mdns import register_mdns_service, unregister_mdns_service  # noqa: PLC0415
    asyncio.create_task(asyncio.to_thread(register_mdns_service, "tunebox.local", 8000))

    try:
        yield
    finally:
        unregister_mdns_service()
        # Cleanup tasks on shutdown
        ws_task.cancel()
        orch_task.cancel()
        indexer_task.cancel()
        for task in [ws_task, orch_task, indexer_task]:
            with contextlib.suppress(asyncio.CancelledError):
                await task

        # Checkpoint & flush SQLite WAL journal on container shutdown to prevent corruption
        try:
            conn = get_db_connection()
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
            conn.close()
        except Exception as wal_ex:
            logging.getLogger(__name__).debug("WAL checkpoint on shutdown: %s", wal_ex)


# Initialize the FastAPI backend
app = FastAPI(
    title="TuneBox API",
    description="A Jukebox experience, using your local music",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://frontend:80",
        "http://localhost",
        "http://localhost:5173",
        "http://tunebox.local",
        "http://tunebox.local:8000",
        "http://tunebox.local:80",
        "https://tunebox.soehlert.com",
        settings.tunebox_url,
    ],
    allow_origin_regex=r"https?://(.*\.local|.*\.soehlert\.com)(:[0-9]+)?",
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(music.router)
app.include_router(stats.router)
app.include_router(websockets_router)


# Root endpoint
@app.get("/", tags=["Root"])
def read_root():
    """Set up our base path.

    Returns:
        A JSON message so you know it worked.
    """
    return {"message": "Welcome to the Tunebox API!"}

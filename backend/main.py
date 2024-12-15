import asyncio
import logging

from fastapi import FastAPI
from backend.routers import music
from backend.websockets import router as websockets_router
from backend.websockets import update_websocket_clients

from fastapi.middleware.cors import CORSMiddleware

# Logging configuration
logging.basicConfig(level=logging.DEBUG)
logging.getLogger('urllib3').setLevel(logging.WARNING)

# Initialize the FastAPI backend
app = FastAPI(
    title="Plex Jukebox API",
    description="A TouchTunes-like backend using Plex as the backend",
    version="1.0.0"
)

# Add CORS middleware to allow WebSocket connections from the frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://frontend:80",
        "http://localhost",
        "http://localhost:5173"
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(music.router)

app.include_router(websockets_router)

# Start the background task for periodic updates
@app.on_event("startup")
async def start_background_tasks():
    asyncio.create_task(update_websocket_clients())

# Root endpoint
@app.get("/", tags=["Root"])
def read_root():
    return {"message": "Welcome to the Tunebox API!"}

# 🛠️ TuneBox Developer Guide

This document outlines the local development setup, code standards, project structure, and step-by-step developer walkthroughs for contributing to **TuneBox**.

---

## 🚀 Quickstart Development Environment

TuneBox includes a **Mock Library Mode** (`TESTING=true`) so you can develop and test features locally without needing a live Plex Media Server or Plex account credentials.

### 1. Prerequisites
- **Python**: `3.13` or `3.14` (managed via [`uv`](https://github.com/astral-sh/uv))
- **Node.js**: `v20+` & `npm`
- **Docker**: Docker Desktop or Docker Engine with `docker compose`

### 2. Running Local Dev Workflows

- **Mock Mode (Default for Dev Work)**:
  ```bash
  make dev
  ```
  *(Starts the containers with `TESTING=true`, populating mock artists, albums, and tracks so you can code immediately without Plex credentials).*

- **Live Plex Dev Mode**:
  ```bash
  TESTING=false make dev
  ```
  *(Starts the containers with `TESTING=false`, allowing local developers to test against a live Plex Media Server).*

Access the application in your browser:
- **Frontend App**: `http://localhost`
- **Backend Swagger API Docs**: `http://localhost:8000/docs`

### 3. Useful `Makefile` Commands

| Command | Description |
| :--- | :--- |
| `make dev` | Starts full Docker stack in mock mode (`TESTING=true`). |
| `TESTING=false make dev` | Starts full Docker stack in live Plex dev mode. |
| `make reset` | Factory resets `.env`, rebuilds containers, flushes Redis, and restarts backend. |
| `make reset-redis` | Flushes all keys in Redis without restarting containers. |
| `make logs` | Streams live logs from the backend container (`docker compose logs -f backend`). |

---

## 📏 Coding Standards & Tooling

### Python & Backend Standards
- **Package Management**: Managed via `uv` (`pyproject.toml` and `uv.lock`). Add new dependencies using `uv add <package>`.
- **Linting & Formatting**: Enforced via **Ruff**. Run `uv run ruff check .` and `uv run ruff format .`.
- **Type Annotations**: Use PEP 585 standard generic types (`list[str]`, `dict[str, Any]`, `str | None`).
- **Docstrings**: Use single-line docstrings for concise function documentation.
- **Testing**: Tests are located in `backend/tests/` using `pytest` and `pytest-asyncio`. Run tests locally with:
  ```bash
  uv run pytest
  ```

### Frontend Standards
- **TypeScript**: Strict type checking enforced (`tsconfig.json`). Avoid using `any`.
- **Styling**: Vanilla CSS per component (`Component.css` alongside `Component.tsx`).
- **HTTP Client**: All REST API calls must use the centralized Axios instance (`frontend/src/api/axiosInstance.ts`).
- **Settings & Admin Controls**: See ⚙️ **[Frontend Settings Guide](settings.md)** for details on admin authorization (`x-admin-token`), player release modes, and the Settings gear button on the bottom bar.

---

## 💡 Key Concept: Axios HTTP Instance Configuration

### What is it?
Located at `frontend/src/api/axiosInstance.ts`, the **Axios HTTP Instance** is a pre-configured instance of the Axios HTTP client library.

```typescript
// frontend/src/api/axiosInstance.ts
import axios from 'axios';

const axiosInstance = axios.create({
  baseURL: '/api',
  headers: {
    'Content-Type': 'application/json',
  },
});

export default axiosInstance;
```

### Why do we use it?
1. **DRY URL Configuration**: Prepend `/api` to all requests automatically.
2. **Centralized Interceptors**: Enables attaching global error handlers or authentication tokens to every request in one place.
3. **Clean Component Code**: Instead of writing `axios.get('http://localhost:8000/api/music/tracks')`, components simply write `axiosInstance.get('/music/tracks')`.

---

## 📂 Frontend Directory Map

Understanding where different parts of the frontend live:

```
frontend/src/
├── main.tsx             # Application entry point & DOM mount
├── App.tsx              # Main layout shell, audio player state, & WebSocket event listener
├── App.css              # Main application layout styles
├── theme.tsx            # Theme provider (dark/light theme tokens)
├── api/
│   └── axiosInstance.ts # Centralized Axios HTTP client instance
└── components/
    ├── ArtistList.tsx   # Artist browser grid & search input (.css paired)
    ├── ArtistAlbums.tsx # Album list for selected artist (.css paired)
    ├── TrackList.tsx    # Track list for selected album (.css paired)
    ├── Queue.tsx        # Read-only "Up Next" queue list (.css paired)
    └── MusicControls.tsx# Bottom Now-Playing bar, playback buttons, & Settings gear icon (.css paired)
```

---

## 📖 Developer Walkthroughs

### Walkthrough 1: Adding a New REST API Route

Goal: Add a new endpoint `GET /api/music/stats` returning total track count and active listener count.

1. **Define Schema (if applicable)**:
   In `backend/routers/music.py`:
   ```python
   from pydantic import BaseModel

   class MusicStatsResponse(BaseModel):
       total_tracks: int
       active_listeners: int
   ```

2. **Add Router Endpoint**:
   In `backend/routers/music.py`:
   ```python
   @router.get("/stats", response_model=MusicStatsResponse)
   async def get_music_stats():
       """Returns current library stats and active listener count."""
       return MusicStatsResponse(total_tracks=1250, active_listeners=4)
   ```

3. **Verify Endpoint in FastAPI**:
   FastAPI automatically registers router endpoints defined on `router = APIRouter(prefix="/api/music")`. Test via Swagger UI at `http://localhost:8000/docs`.

4. **Add Unit Test**:
   In `backend/tests/test_music.py`:
   ```python
   @pytest.mark.asyncio
   async def test_get_music_stats(async_client):
       response = await async_client.get("/api/music/stats")
       assert response.status_code == 200
       assert "total_tracks" in response.json()
   ```

---

### Walkthrough 2: Hooking Up a Frontend Method to the New API Route

Goal: Fetch `/api/music/stats` from the React frontend and display it.

1. **Add API Call in Component or Custom Hook**:
   In `frontend/src/components/MusicControls.tsx` (or a dedicated service file):
   ```typescript
   import { useEffect, useState } from 'react';
   import axiosInstance from '../api/axiosInstance';

   interface MusicStats {
     total_tracks: number;
     active_listeners: number;
   }

   export const MusicStatsBadge = () => {
     const [stats, setStats] = useState<MusicStats | null>(null);

     useEffect(() => {
       axiosInstance.get<MusicStats>('/music/stats')
         .then((res) => setStats(res.data))
         .catch((err) => console.error('Failed to fetch stats:', err));
     }, []);

     if (!stats) return null;
     return <span>🎵 {stats.total_tracks} tracks | 🎧 {stats.active_listeners} listening</span>;
   };
   ```

---

### Walkthrough 3: Broadcasting & Listening to WebSocket Events

Goal: Broadcast a custom real-time event when a user triggers an action.

1. **Backend Broadcast (`backend/websockets.py`)**:
   ```python
   from backend.websockets import manager

   # Broadcast JSON event to all connected clients
   await manager.broadcast({
       "type": "stats_updated",
       "data": {"active_listeners": 5}
   })
   ```

2. **Frontend Listener (`frontend/src/App.tsx`)**:
   ```typescript
   useEffect(() => {
     const ws = new WebSocket(`ws://${window.location.host}/ws`);

     ws.onmessage = (event) => {
       const message = JSON.parse(event.data);
       if (message.type === 'stats_updated') {
         console.log('New listener count:', message.data.active_listeners);
       }
     };

     return () => ws.close();
   }, []);
   ```

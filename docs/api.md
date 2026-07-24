# 🔌 TuneBox API & WebSocket Reference

This document provides a comprehensive technical specification for the TuneBox REST API endpoints and real-time WebSocket messaging protocol.

---

## 📡 REST API Reference

All REST API endpoints are prefixed with `/api`. Interactive OpenAPI (Swagger) documentation is available at `http://localhost:8000/docs`.

### Authentication Endpoints (`/api/auth`)

#### `GET /api/auth/status`
Checks whether TuneBox has been configured with valid Plex credentials.
- **Response `200 OK`**:
  ```json
  {
    "authenticated": true,
    "username": "host_user",
    "plex_server_name": "MyPlexServer",
    "client_name": "MyClient",
    "instance_name": "TuneBox",
    "is_configured": true,
    "testing": false
  }
  ```

#### `POST /api/auth/pin`
Requests a new OAuth login PIN from Plex.
- **Query Parameters**:
  - `simulate` *(optional, boolean)*: Set to `true` to generate a mock PIN (only available when testing mode is enabled).
- **Response `200 OK`**:
  ```json
  {
    "pin_id": 12345678,
    "code": "ABCD",
    "url": "https://plex.tv/link"
  }
  ```

#### `GET /api/auth/check`
Checks whether the user has authorized the requested PIN.
- **Query Parameters**:
  - `pin_id` *(required, integer)*: The PIN ID returned from `POST /api/auth/pin`.
- **Response `200 OK`**:
  ```json
  {
    "authenticated": true,
    "token": "plex_auth_token_string"
  }
  ```

#### `POST /api/auth/configure`
Saves selected Plex Server and Client Player configuration.
- **Request Body**:
  ```json
  {
    "plex_username": "host_user",
    "client_name": "MyClient",
    "plex_server_name": "MyPlexServer"
  }
  ```
- **Response `200 OK`**:
  ```json
  {
    "message": "Configuration successfully saved and reinitialized!",
    "admin_token": "admin_token_hex_string"
  }
  ```

---

### Music Endpoints (`/api/music`)

#### `GET /api/music/servers`
Retrieves all accessible Plex servers for the configured account (including primary home server and shared servers).
- **Response `200 OK`**:
  ```json
  [
    {
      "server_id": "primary-server-uuid",
      "name": "plex-so",
      "is_primary": true
    },
    {
      "server_id": "shared-server-uuid",
      "name": "NAS",
      "is_primary": false
    }
  ]
  ```

#### `GET /api/music/search`
Searches artists, albums, and tracks across selected Plex servers.
- **Query Parameters**:
  - `query` *(required, string)*: Search string.
  - `selected_servers` *(optional, string)*: Comma-separated server IDs to limit search scope.
- **Response `200 OK`**: Search result array with `server_id` and `server_name` attributes.

#### `GET /api/music/artists`
Retrieves a list of indexed music artists.
- **Query Parameters**:
  - `query` *(optional, string)*: Filter artists by name search.
- **Response `200 OK`**:
  ```json
  [
    {
      "id": "101",
      "title": "Daft Punk",
      "thumb": "/api/music/art/101"
    }
  ]
  ```

#### `GET /api/music/artists/{artist_id}/albums`
Retrieves all albums for a specific artist.
- **Response `200 OK`**:
  ```json
  [
    {
      "id": "501",
      "title": "Discovery",
      "year": 2001,
      "thumb": "/api/music/art/501"
    }
  ]
  ```

#### `GET /api/music/albums/{album_id}/tracks`
Retrieves tracks belonging to an album.
- **Response `200 OK`**:
  ```json
  [
    {
      "id": "9001",
      "title": "One More Time",
      "duration": 320,
      "artist": "Daft Punk",
      "album": "Discovery"
    }
  ]
  ```

#### `GET /api/music/queue`
Fetches the current active track queue.
- **Response `200 OK`**:
  ```json
  [
    {
      "item_id": "9001",
      "title": "One More Time",
      "artist": "Daft Punk",
      "duration": 320,
      "queued_by": "Guest Phone"
    }
  ]
  ```

#### `POST /api/music/queue`
Adds a track to the active playback queue.
- **Request Body**:
  ```json
  {
    "track_id": "9001",
    "client_name": "Guest Phone"
  }
  ```
- **Response `200 OK`**:
  ```json
  {
    "status": "success",
    "message": "Track added to queue"
  }
  ```

#### `DELETE /api/music/queue/{item_id}`
Removes a specific track from the active playback queue.
- **Headers**:
  - `X-Admin-Token` *(required, string)*: Valid host admin token.
- **Response `200 OK`**:
  ```json
  {
    "message": "Removed Track Title from the queue."
  }
  ```

#### `POST /api/music/queue/reorder`
Reorders an upcoming track in the queue (restricted to admin).
- **Headers**:
  - `X-Admin-Token` *(required, string)*: Valid host admin token.
- **Request Body**:
  ```json
  {
    "from_index": 3,
    "to_index": 1
  }
  ```
- **Response `200 OK`**:
  ```json
  {
    "message": "Queue reordered successfully."
  }
  ```

#### `POST /api/music/queue/move-top`
Moves an upcoming track to index 1 (next track up) in the queue (restricted to admin).
- **Headers**:
  - `X-Admin-Token` *(required, string)*: Valid host admin token.
- **Request Body**:
  ```json
  {
    "from_index": 4
  }
  ```
- **Response `200 OK`**:
  ```json
  {
    "message": "Queue reordered successfully."
  }
  ```

#### `GET /api/music/playlists`
Retrieves a list of available Plex playlists (restricted to admin).
- **Headers**:
  - `X-Admin-Token` *(required, string)*: Valid host admin token.
- **Response `200 OK`**:
  ```json
  [
    {
      "playlist_id": 5001,
      "title": "Party Hits"
    }
  ]
  ```

#### `POST /api/music/playlists/{playlist_id}/seed`
Imports, shuffles, and seeds the playback queue with tracks from the selected playlist.
- **Headers**:
  - `X-Admin-Token` *(required, string)*: Valid host admin token.
- **Response `200 OK`**:
  ```json
  {
    "message": "Successfully seeded 10 tracks from playlist 'Party Hits'."
  }

#### `GET /api/music/autoplay`
Retrieves the current state of Smart Autoplay Mode.
- **Response `200 OK`**:
  ```json
  {
    "autoplay_enabled": true
  }
  ```

#### `POST /api/music/autoplay`
Enables or disables Smart Autoplay Mode (restricted to admin).
- **Headers**:
  - `X-Admin-Token` *(required, string)*: Valid host admin token.
- **Request Body**:
  ```json
  {
    "enabled": true
  }
  ```
- **Response `200 OK`**:
  ```json
  {
    "autoplay_enabled": true
  }
  ```

#### `POST /api/music/skip-vote`
Submits a vote to skip the currently playing track.
- **Request Body**:
  ```json
  {
    "client_id": "browser-uuid-1234"
  }
  ```
- **Response `200 OK`**:
  ```json
  {
    "votes_current": 3,
    "votes_required": 5,
    "skipped": false
  }
  ```

### Stats Endpoints (`/api/stats`)

#### `GET /api/stats`
Retrieves sorted lists of session and all-time leaderboard rankings.
- **Response `200 OK`**:
  ```json
  {
    "session": {
      "adds": [
        { "username": "guest1", "count": 4, "role": "guest" }
      ],
      "skips_cast": [
        { "username": "guest2", "count": 2, "role": "guest" }
      ],
      "skips_received": [
        { "username": "guest3", "count": 1, "role": "guest" }
      ]
    },
    "all_time": {
      "adds": [
        { "username": "guest1", "count": 12, "role": "guest" }
      ],
      "skips_cast": [
        { "username": "guest2", "count": 8, "role": "guest" }
      ],
      "skips_received": [
        { "username": "guest3", "count": 3, "role": "guest" }
      ]
    }
  }
  ```

#### `POST /api/stats/reset`
Wipes the active party session leaderboard metrics in Redis (restricted to admin).
- **Headers**:
  - `X-Admin-Token` *(required, string)*: Valid host admin token.
- **Response `200 OK`**:
  ```json
  {
    "message": "Session stats successfully reset."
  }
  ```

---

## ⚡ WebSocket Protocol (`ws://<host>/ws/{message_type}/{session_id}`)

TuneBox uses WebSockets for instant, real-time push updates across guest phones and host displays.

### Connection URL & Parameters
- **Endpoint**: `ws://<host>/ws/{message_type}/{session_id}`
- **Parameters**:
  - `message_type`:
    - `music_control`: Receives currently playing track updates and progress ticks.
    - `queue_update`: Receives real-time queue changes.
    - `client_control`: Receives per-browser target playback commands.
  - `session_id`: Unique client session UUID generated by the frontend.

---

### Real-Time Event Message Payloads

#### 1. `queue_update` Event
Broadcast whenever a track is queued, removed, re-ordered, or skipped.

```json
{
  "type": "queue_update",
  "message": "Queue update",
  "queue": [
    {
      "item_id": "9001",
      "title": "One More Time",
      "artist": "Daft Punk",
      "duration": 320,
      "queued_by": "Guest Phone"
    }
  ]
}
```

#### 2. `music_control` Event (Current Track Update)
Broadcast periodically (every 1 second tick or when playback state changes).

```json
{
  "message": "Current track update",
  "current_track": {
    "item_id": "9001",
    "title": "One More Time",
    "artist": "Daft Punk",
    "total_time": 320,
    "elapsed_time": 45,
    "remaining_time": 275,
    "remaining_percentage": 85.9,
    "track_state": "playing"
  }
}
```

# Walkthrough: Dynamic replacement & Autoplay Mode Verification

This guide outlines the completed implementations and details the steps required to verify the new queueing features.

## What Was Added
1. **Fallback Track Annotation**: Tracks queued via pre-seeding or autoplay have `is_fallback: true` in their metadata.
2. **Leapfrog Insertion & Trimming**: Guest track additions jump ahead of all fallback tracks and trigger the deletion of the last fallback track.
3. **History-Based Autoplay**: Generates 10 vibe tracks (based on Plex related tracks or cached playlist fallback) when the queue drops to 5 or fewer tracks.
4. **Admin UI Toggle**: Added a toggle switch in settings modal to enable/disable autoplay.

## Automated Validation
All 71 backend tests passed successfully:
* `backend/tests/test_redis.py::test_add_to_queue_redis_dynamic_replacement` (Verified insertion and trimming index math).
* `backend/tests/test_mock_music.py::test_get_and_set_autoplay` (Verified API endpoints with authentication).
* `frontend/src/App.tsx` compiles with zero typescript warnings.

## Step-by-Step Manual Verification Plan

### Step 1: Initialize the Queue
1. Log into the Host dashboard at `http://localhost:5173`.
2. Open Settings (admin mode), select a playlist, and click **Seed Jukebox**.
3. **Check**: Ensure exactly 10 tracks are populated.

### Step 2: Toggle Autoplay Mode
1. In the settings panel, check the **Smart Autoplay Mode** toggle.
2. Verify the API successfully updates (shows visual success message `✓ Autoplay is now enabled!`).

### Step 3: Trigger Autoplay Vibe Check
1. Start playing the queue.
2. Delete tracks or let them play until there are **5 or fewer** tracks remaining.
3. **Check**: The queue should dynamically append 10 new related tracks in the background.

### Step 4: Verify Guest Leapfrog
1. Open a new window as a guest and add a track.
2. **Check**: The guest song sits ahead of the fallback tracks. The bottom-most fallback track is dropped from the list.

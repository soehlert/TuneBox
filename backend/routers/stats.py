from fastapi import APIRouter, Header, HTTPException
from backend.services import stats
from backend.config import settings

router = APIRouter(prefix="/api/stats", tags=["stats"])

@router.get("")
def get_leaderboards():
    """Retrieve session and all-time statistics leaderboards."""
    return {
        "session": stats.get_session_stats(),
        "all_time": stats.get_alltime_stats()
    }

@router.post("/reset")
def reset_session_stats(x_admin_token: str | None = Header(None)):
    """Reset the current party/session statistics (Admin only)."""
    if not settings.admin_token or x_admin_token != settings.admin_token:
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid admin token")
    stats.clear_session_stats()
    return {"message": "Session stats successfully reset."}


@router.get("/library")
def get_library_health_stats():
    """Retrieve catalog counts, missing artwork metrics, and per-server breakdown."""
    from backend.services.library import get_library_health_stats as fetch_stats  # noqa: PLC0415
    return fetch_stats()


from pydantic import BaseModel  # noqa: E402


class RefetchArtPayload(BaseModel):
    type: str
    id: int


@router.get("/missing-artwork")
def get_missing_artwork(type: str, query: str | None = None):
    """Retrieve primary server items missing artwork."""
    if type not in ("artist", "album"):
        raise HTTPException(status_code=400, detail="Invalid item type")
    from backend.services.library import get_missing_artwork_items  # noqa: PLC0415
    return {"items": get_missing_artwork_items(item_type=type, query=query)}


@router.post("/refetch-artwork")
def refetch_item_artwork_endpoint(payload: RefetchArtPayload):
    """Attempt to re-sync thumbnail URL from Plex for an item missing artwork."""
    if payload.type not in ("artist", "album"):
        raise HTTPException(status_code=400, detail="Invalid item type")
    from backend.services.library import refetch_item_artwork  # noqa: PLC0415
    success = refetch_item_artwork(item_type=payload.type, item_id=payload.id)
    return {"success": success}


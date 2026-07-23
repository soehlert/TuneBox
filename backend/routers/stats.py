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

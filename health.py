from fastapi import APIRouter
from datetime import datetime, timezone

router = APIRouter()


@router.get("/health")
async def health():
    """
    Health endpoint required by the spec:
    Always 200, no DB dependency.
    """
    return {
        "status": "ok",
        "service": "problemsolver-backend",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "1.0.0",
    }
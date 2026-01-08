from fastapi import APIRouter, status
from app.db.session import async_engine
from app.core.config import settings
import aioredis
import asyncio

router = APIRouter()


async def check_db():
    try:
        async with async_engine.begin() as conn:
            # simple lightweight query to test connectivity
            await conn.execute("SELECT 1")
        return True, None
    except Exception as e:
        return False, str(e)


async def check_redis():
    if not settings.REDIS_URL:
        # Treat missing redis as unhealthy in readiness (configurable)
        return False, "REDIS_URL not configured"
    try:
        redis = await aioredis.from_url(settings.REDIS_URL)
        pong = await redis.ping()
        await redis.close()
        return pong, None
    except Exception as e:
        return False, str(e)


@router.get("/ready")
async def ready():
    """
    Readiness check verifies DB & Redis connectivity; return non-200 if dependencies unhealthy.
    """
    db_ok, db_err = await check_db()
    redis_ok, redis_err = await check_redis()
    status_code = status.HTTP_200_OK if db_ok and redis_ok else status.HTTP_503_SERVICE_UNAVAILABLE
    body = {
        "status": "ok" if db_ok and redis_ok else "degraded",
        "dependencies": {
            "database": {"ok": db_ok, "error": db_err},
            "redis": {"ok": redis_ok, "error": redis_err},
        },
    }
    return body if status_code == 200 else body, status_code
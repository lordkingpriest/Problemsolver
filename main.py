from fastapi import FastAPI
from app.api import health, ready
from app.core.config import settings
import logging

logger = logging.getLogger("problemsolver")
app = FastAPI(title="Problemsolver Backend", version="1.0.0")

app.include_router(health.router, prefix="/api")
app.include_router(ready.router, prefix="/api")


@app.on_event("startup")
async def startup_event():
    # Initialize DB, Redis, metrics, etc. (non-blocking stubs)
    logger.info("Starting Problemsolver backend")
    # e.g., await db.init(), await redis.init() - left for implementation


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down Problemsolver backend")
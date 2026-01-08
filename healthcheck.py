"""
Simple DB healthcheck script intended for Kubernetes readiness/liveness exec probes.

Usage: python -m app.bin.healthcheck
Exits 0 if DB connection succeeds; exits non-zero otherwise.

This script must not log secrets.
"""
import sys
import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings

async def main():
    db_url = settings.DATABASE_URL
    if not db_url:
        print("DATABASE_URL not set", file=sys.stderr)
        return 2
    try:
        engine = create_async_engine(db_url, echo=False)
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        await engine.dispose()
        return 0
    except Exception as exc:
        # Do not print secrets
        print("DB connection failed", file=sys.stderr)
        return 3

if __name__ == "__main__":
    code = asyncio.run(main())
    sys.exit(code)
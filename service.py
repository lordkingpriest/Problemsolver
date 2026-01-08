"""
PollerService updates: start a Prometheus metrics server and update metrics.

Metrics:
- problemsolver_poller_last_success_unixtime (Gauge)
- problemsolver_deposits_processed_total, deposits_errors_total, collisions_total are emitted in processor
"""
import asyncio
import logging
import time
from typing import Optional
from prometheus_client import start_http_server, Gauge

from app.poller.binance_client import BinanceClient
from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.db.poller_models import PollerCheckpoint, DepositRaw
from app.poller.processor import ingest_deposit, try_match_and_credit
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, insert, update

logger = logging.getLogger("problemsolver.poller.service")

CHECKPOINT_KEY = "binance_deposit"
DEFAULT_POLL_INTERVAL = int(getattr(settings, "POLLER_POLL_INTERVAL_SECONDS", 20))
MAX_LIMIT = 200  # Binance limit controlled (subject to API docs)

# Poller metrics
POLLER_METRICS_PORT = int(getattr(settings, "POLLER_METRICS_PORT", 8002))
MET_POLLER_LAST_SUCCESS = Gauge("problemsolver_poller_last_success_unixtime", "Unix time of last successful poll")

class PollerService:
    def __init__(self, client: BinanceClient, poll_interval: int = DEFAULT_POLL_INTERVAL):
        self.client = client
        self.poll_interval = poll_interval
        self.running = False
        # Start metrics server
        try:
            start_http_server(POLLER_METRICS_PORT)
            logger.info("Prometheus metrics server started on port %s", POLLER_METRICS_PORT)
        except Exception as exc:
            logger.warning("Failed to start metrics server: %s", exc)

    async def _load_checkpoint(self, session: AsyncSession) -> dict:
        row = (await session.execute(select(PollerCheckpoint).where(PollerCheckpoint.key == CHECKPOINT_KEY))).scalar_one_or_none()
        if row:
            return {"last_insert_time_ms": row.last_insert_time_ms, "last_tx_id": row.last_tx_id}
        return {"last_insert_time_ms": None, "last_tx_id": None}

    async def _save_checkpoint(self, session: AsyncSession, last_insert_time_ms: int, last_tx_id: str):
        existing = (await session.execute(select(PollerCheckpoint).where(PollerCheckpoint.key == CHECKPOINT_KEY))).scalar_one_or_none()
        if existing:
            existing.last_insert_time_ms = last_insert_time_ms
            existing.last_tx_id = last_tx_id
        else:
            session.add(PollerCheckpoint(key=CHECKPOINT_KEY, last_insert_time_ms=last_insert_time_ms, last_tx_id=last_tx_id))
        await session.flush()

    async def run_once_window(self, start_ms: Optional[int], end_ms: Optional[int]):
        logger.debug("Polling Binance deposit history start=%s end=%s", start_ms, end_ms)
        try:
            deposits = await self.client.get_deposit_history(start_time_ms=start_ms, end_time_ms=end_ms, limit=MAX_LIMIT)
        except Exception as exc:
            logger.exception("Binance deposit history fetch failed: %s", exc)
            raise

        deposits_sorted = sorted(deposits, key=lambda r: int(r.get("insertTime", 0)))
        if not deposits_sorted:
            return None

        async with AsyncSessionLocal() as session:
            last_insert_ms = None
            last_txid = None
            for dep in deposits_sorted:
                try:
                    async with session.begin():
                        raw_rec, inserted = await ingest_deposit(session, dep)
                        if inserted:
                            try:
                                await try_match_and_credit(session, raw_rec)
                            except Exception:
                                # processor re-raises on fatal errors; transaction will rollback
                                logger.exception("Processor error for tx=%s", raw_rec.tx_id)
                                # continue to next deposit to avoid blocking ingestion
                        last_insert_ms = raw_rec.insert_time_ms
                        last_txid = raw_rec.tx_id
                        await self._save_checkpoint(session, last_insert_ms, last_txid)
                except Exception:
                    logger.exception("Failed to process deposit tx=%s", dep.get("txId"))
                    continue
            # update poller last success metric
            MET_POLLER_LAST_SUCCESS.set(int(time.time()))
            return {"last_insert_time_ms": last_insert_ms, "last_tx_id": last_txid}

    async def run(self):
        self.running = True
        try:
            await self.client.sync_time()
        except Exception:
            logger.exception("Time sync failed; continuing with local clock.")
        consecutive_errors = 0
        while self.running:
            try:
                async with AsyncSessionLocal() as session:
                    checkpoint = await self._load_checkpoint(session)
                start_ms = checkpoint.get("last_insert_time_ms")
                if start_ms is None:
                    lookback_ms = int(getattr(settings, "POLLER_INITIAL_LOOKBACK_MS", 3600 * 1000 * 24))  # 24h
                    start_ms = int(time.time() * 1000) - lookback_ms
                end_ms = int(time.time() * 1000) + (self.client._time_offset_ms or 0)
                window_ms = int(getattr(settings, "POLLER_WINDOW_MS", 5 * 60 * 1000))
                window_start = start_ms
                while window_start < end_ms:
                    window_end = min(window_start + window_ms - 1, end_ms)
                    await self.run_once_window(window_start, window_end)
                    window_start = window_end + 1
                    consecutive_errors = 0
                await asyncio.sleep(self.poll_interval)
            except Exception:
                logger.exception("Poller encountered an error")
                consecutive_errors += 1
                backoff = min(300, (2 ** min(consecutive_errors, 6)))
                await asyncio.sleep(backoff)
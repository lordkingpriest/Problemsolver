"""
BinanceClient - lightweight async client for signed Binance REST endpoints used by the poller.

Responsibilities:
- server time sync (/api/v3/time)
- sign requests (HMAC SHA256)
- poll deposit history (/sapi/v1/capital/deposit/hisrec)
- safe timestamp skew handling

This client never logs secrets. API key/secret are injected from Settings at runtime.
"""
import time
import typing as t
import asyncio
import httpx

from app.core.config import settings
from app.utils.binance_signing import sign_binance_query
import logging

logger = logging.getLogger("problemsolver.poller.binance")

BINANCE_BASE = "https://api.binance.com"


class BinanceClient:
    def __init__(self, api_key: str, api_secret: str, http_client: httpx.AsyncClient | None = None):
        if not api_key or not api_secret:
            raise ValueError("BINANCE_API_KEY and BINANCE_API_SECRET must be provided at runtime")
        self.api_key = api_key
        self.api_secret = api_secret
        self.http = http_client or httpx.AsyncClient(timeout=30.0)
        # time offset = server_time_ms - local_time_ms
        self._time_offset_ms: int | None = None

    async def close(self):
        try:
            await self.http.aclose()
        except Exception:
            pass

    async def sync_time(self) -> int:
        """Fetch server time and compute offset to local time (ms). Return offset."""
        url = f"{BINANCE_BASE}/api/v3/time"
        r = await self.http.get(url)
        r.raise_for_status()
        data = r.json()
        server_time = int(data["serverTime"])
        local_time = int(time.time() * 1000)
        self._time_offset_ms = server_time - local_time
        logger.debug("Synced Binance server time: server=%s local=%s offset_ms=%s", server_time, local_time, self._time_offset_ms)
        return self._time_offset_ms

    def _now_ms(self) -> int:
        """Return current ms adjusted by server time offset if available."""
        local = int(time.time() * 1000)
        return local + (self._time_offset_ms or 0)

    async def _signed_get(self, path: str, params: dict | None = None) -> dict:
        """
        Generic signed GET helper. Adds timestamp and signature to params, sets API key header.
        """
        params = dict(params or {})
        params["timestamp"] = str(self._now_ms())
        # Build query string in same order as Binance (sorted by key) to be deterministic
        qs = "&".join(f"{k}={params[k]}" for k in sorted(params.keys()))
        signature = sign_binance_query(qs, self.api_secret)
        qs_signed = qs + "&signature=" + signature
        url = f"{BINANCE_BASE}{path}?{qs_signed}"
        headers = {"X-MBX-APIKEY": self.api_key}
        r = await self.http.get(url, headers=headers)
        r.raise_for_status()
        return r.json()

    async def get_deposit_history(self, start_time_ms: int | None = None, end_time_ms: int | None = None, limit: int = 100) -> list[dict]:
        """
        Call /sapi/v1/capital/deposit/hisrec with paginated range.
        - Binance supports startTime and endTime; results ordered by insertTime descending (newest first).
        - We will request in ascending time windows by using startTime and endTime and then reverse results as needed.
        """
        params: dict[str, t.Any] = {"limit": str(limit)}
        if start_time_ms is not None:
            params["startTime"] = str(start_time_ms)
        if end_time_ms is not None:
            params["endTime"] = str(end_time_ms)
        path = "/sapi/v1/capital/deposit/hisrec"
        try:
            data = await self._signed_get(path, params=params)
            # Binance returns a list
            if isinstance(data, list):
                return data
            # if unexpected, wrap into list
            return list(data)
        except httpx.HTTPStatusError as e:
            # Let caller handle retries/backoff
            logger.warning("Binance deposit history request failed: %s", e)
            raise
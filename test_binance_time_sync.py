import pytest
import asyncio
from app.poller.binance_client import BinanceClient
import httpx
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_sync_time_sets_offset():
    async_client = AsyncMock()
    # Simulate Binance /api/v3/time returning serverTime
    async_client.get.return_value.json.return_value = {"serverTime": 1670000000000}
    async_client.get.return_value.raise_for_status = lambda: None
    client = BinanceClient(api_key="k", api_secret="s", http_client=async_client)
    offset = await client.sync_time()
    assert isinstance(offset, int)
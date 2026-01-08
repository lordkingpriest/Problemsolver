import asyncio
import pytest
from app.poller.processor import ingest_deposit
from app.db.session import AsyncSessionLocal
from app.db.models import DepositRaw

@pytest.mark.asyncio
async def test_ingest_deposit_idempotent():
    deposit = {
        "txId": "tx-test-123",
        "coin": "USDT",
        "network": "ERC20",
        "amount": "10.0",
        "status": 1,
        "address": "0xdeadbeef",
        "addressTag": None,
        "insertTime": 1670000000000,
        "completeTime": 1670000001000,
        "confirmTimes": 12
    }
    async with AsyncSessionLocal() as session:
        async with session.begin():
            rec1, inserted1 = await ingest_deposit(session, deposit)
            assert inserted1 is True
            # Second attempt should detect existing and return inserted=False
            rec2, inserted2 = await ingest_deposit(session, deposit)
            assert inserted2 is False
            assert rec1.tx_id == rec2.tx_id
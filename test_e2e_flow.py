import asyncio
import uuid
from decimal import Decimal
import pytest
import respx
from httpx import Response
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.db.models import Merchant, Invoice, DepositRaw, Payment, LedgerEntry, WebhookQueue
from app.poller.service import PollerService
from app.poller.binance_client import BinanceClient
from app.poller.amount_diff import adjusted_amount_for_invoice

# Mark as asyncio test
pytestmark = pytest.mark.asyncio

async def run_migrations():
    # Run Alembic programmatically before tests
    from alembic import command
    from alembic.config import Config
    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")

@pytest.fixture(scope="module", autouse=True)
def event_loop():
    loop = asyncio.get_event_loop()
    yield loop

@pytest.fixture(scope="module")
async def prepare_db():
    # Ensure migrations applied
    await run_migrations()
    yield
    # teardown not required (CI will use ephemeral DB)

@pytest.fixture
async def merchant_and_invoice():
    # Create a merchant and invoice in DB directly to control IDs
    async with AsyncSessionLocal() as session:
        async with session.begin():
            merchant = Merchant(name="Test Merchant")
            session.add(merchant)
            await session.flush()
            # create invoice with deterministic UUID
            invoice_id = uuid.uuid4()
            base_amount = Decimal("10.00")
            adjusted = adjusted_amount_for_invoice(base_amount, invoice_id, "ERC20", k=3)
            invoice = Invoice(
                id=invoice_id,
                merchant_id=merchant.id,
                publish_amount=adjusted,
                currency="USDT",
                network="ERC20",
                address="0xtestaddress",
                address_tag=None,
                status="pending"
            )
            session.add(invoice)
            await session.flush()
            inv = invoice
            merch = merchant
        # return IDs
        return merch, inv

@pytest.fixture
def mocked_binance(monkeypatch):
    """
    Provide a monkeypatch for BinanceClient.get_deposit_history to return a deposit matching the invoice.
    We don't rely on network; we return a list of deposits.
    """
    async def _mock_get_deposit_history(self, start_time_ms=None, end_time_ms=None, limit=100):
        # Will be replaced per-test by injecting expected deposit
        return []
    monkeypatch.setattr(BinanceClient, "get_deposit_history", _mock_get_deposit_history)
    yield

async def test_end_to_end_credit(prepare_db, merchant_and_invoice, monkeypatch):
    merchant, invoice = merchant_and_invoice
    # Build a deposit that matches the invoice
    deposit = {
        "txId": "tx-e2e-1",
        "amount": str(invoice.publish_amount),
        "coin": "USDT",
        "network": invoice.network,
        "status": 1,
        "address": invoice.address,
        "addressTag": None,
        "insertTime": int(datetime.now(timezone.utc).timestamp() * 1000),
        "completeTime": int(datetime.now(timezone.utc).timestamp() * 1000),
        "confirmTimes": 12
    }

    # Monkeypatch BinanceClient.get_deposit_history to return that deposit
    async def mocked_get(self, start_time_ms=None, end_time_ms=None, limit=100):
        return [deposit]
    monkeypatch.setattr(BinanceClient, "get_deposit_history", mocked_get)

    # Create a BinanceClient and PollerService but don't let it call network
    client = BinanceClient(api_key="dummy", api_secret="dummy")
    poller = PollerService(client=client, poll_interval=1)

    # Run one window using timestamps that include deposit.insertTime
    start_ms = deposit["insertTime"] - 1000
    end_ms = deposit["insertTime"] + 1000

    # Run the window
    result = await poller.run_once_window(start_ms, end_ms)

    # Assert processing occurred: deposit_raw record, payment, ledger entry, invoice status updated, webhook queued
    async with AsyncSessionLocal() as session:
        # deposit_raw exists and processed True
        dr = (await session.execute(
            DepositRaw.__table__.select().where(DepositRaw.tx_id == deposit["txId"])
        )).first()
        assert dr is not None

        # reload invoice
        inv = (await session.execute(Invoice.__table__.select().where(Invoice.id == invoice.id))).first()
        assert inv is not None
        # Invoice should be paid
        invoice_row = (await session.execute(Invoice.__table__.select().where(Invoice.id == invoice.id))).first()
        # Query via ORM for clarity
        inv_obj = (await session.get(Invoice, invoice.id))
        assert inv_obj.status == "paid"

        # Payment exists
        payment_row = (await session.execute(Payment.__table__.select().where(Payment.tx_id == deposit["txId"]))).first()
        assert payment_row is not None

        # Ledger entry exists
        ledger_row = (await session.execute(LedgerEntry.__table__.select().where(LedgerEntry.merchant_id == merchant.id))).first()
        assert ledger_row is not None

        # Webhook queue entry
        queue_row = (await session.execute(WebhookQueue.__table__.select().where(WebhookQueue.merchant_id == merchant.id))).first()
        assert queue_row is not None
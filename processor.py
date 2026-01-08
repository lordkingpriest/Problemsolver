"""
Processor with amount-differentiation fallback and Prometheus metrics integration.

Behavior changes:
- If no exact amount match among candidates, compute adjusted_amount for each candidate invoice
  using amount_diff.adjusted_amount_for_invoice(...) and compare the deposit amount to adjusted_amount.
- If exactly one invoice matches adjusted_amount -> credit as usual.
- If multiple invoices share the same adjusted_amount (collision) -> increment collisions metric,
  write audit/system event, mark involved invoices as 'pending_manual_resolution' and leave deposit unprocessed.
Metrics added:
- problemsolver_deposits_processed_total
- problemsolver_deposits_errors_total
- problemsolver_collisions_total
"""
from decimal import Decimal, getcontext
import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import AsyncSessionLocal
from app.db.models import DepositRaw, Invoice, WebhookQueue, Payment, LedgerEntry, AuditLog, SystemEvent
from app.poller.config import required_confirmations_for
from app.poller import amount_diff
from prometheus_client import Counter

logger = logging.getLogger("problemsolver.poller.processor")

# Metrics
MET_DEPOSITS_PROCESSED = Counter("problemsolver_deposits_processed_total", "Total deposits processed (credited)")
MET_DEPOSITS_ERRORS = Counter("problemsolver_deposits_errors_total", "Total deposit processing errors")
MET_COLLISIONS = Counter("problemsolver_collisions_total", "Total collisions detected during amount-diff matching")

# Config defaults
AMOUNT_DIFF_K = int(getattr(__import__("app.core.config", fromlist=["settings"]).settings, "AMOUNT_DIFF_K", 3))
MAX_COLLISION_ESCALATE = int(getattr(__import__("app.core.config", fromlist=["settings"]).settings, "AMOUNT_DIFF_MAX_RETRIES", 5))


async def ingest_deposit(session: AsyncSession, deposit: dict) -> tuple[DepositRaw, bool]:
    """
    Idempotent insert of deposit_raw; return (record, inserted_bool)
    """
    txid = deposit.get("txId")
    if not txid:
        raise ValueError("deposit missing txId")
    record = DepositRaw(
        tx_id=txid,
        coin=deposit.get("coin"),
        network=deposit.get("network"),
        amount=Decimal(str(deposit.get("amount"))),
        status=int(deposit.get("status") or 0),
        address=deposit.get("address"),
        address_tag=deposit.get("addressTag"),
        insert_time_ms=int(deposit.get("insertTime") or 0),
        complete_time_ms=int(deposit.get("completeTime") or 0) if deposit.get("completeTime") else None,
        raw=deposit,
    )
    try:
        session.add(record)
        await session.flush()
        inserted = True
        logger.debug("Inserted deposit_raw tx=%s", txid)
    except Exception:
        # Unique constraint likely; fetch existing row
        await session.rollback()
        existing = (await session.execute(select(DepositRaw).where(DepositRaw.tx_id == txid))).scalar_one_or_none()
        if existing:
            return existing, False
        else:
            logger.exception("Unexpected error inserting deposit_raw tx=%s", txid)
            raise
    return record, inserted


async def try_match_and_credit(session: AsyncSession, deposit_raw: DepositRaw) -> bool:
    """
    Attempt to match deposit to invoice.
    1) Exact amount match first.
    2) Amount-diff fallback among candidates.
    Collision handling: mark invoices 'pending_manual_resolution' and emit audit/system_event.
    """
    try:
        # Only USDT handled
        if (deposit_raw.coin or "").upper() != "USDT":
            logger.info("Ignoring non-USDT deposit tx=%s", deposit_raw.tx_id)
            return False

        raw = deposit_raw.raw or {}
        confirmations = int(raw.get("confirmTimes") or 0)
        required = required_confirmations_for(deposit_raw.network)
        if deposit_raw.status != 1 or confirmations < required:
            logger.info("Deposit not ready tx=%s status=%s confirmations=%s required=%s", deposit_raw.tx_id, deposit_raw.status, confirmations, required)
            return False

        # Find candidate invoices by address/network and pending status
        stmt = select(Invoice).where(
            Invoice.address == deposit_raw.address,
            Invoice.network == deposit_raw.network,
            Invoice.status == "pending"
        ).limit(50)
        if deposit_raw.address_tag:
            stmt = stmt.where(Invoice.address_tag == deposit_raw.address_tag)

        res = await session.execute(stmt)
        candidates = res.scalars().all()
        if not candidates:
            logger.info("No invoice candidates for tx=%s", deposit_raw.tx_id)
            return False

        getcontext().prec = 50
        amount = deposit_raw.amount

        # First pass: exact amount match
        for candidate in candidates:
            # Lock invoice
            invoice_row = (await session.execute(select(Invoice).where(Invoice.id == candidate.id).with_for_update())).scalar_one()
            if invoice_row.status != "pending":
                continue
            inv_amount = Decimal(str(invoice_row.publish_amount))
            if inv_amount == amount:
                # perform atomic credit
                await _credit_invoice(session, invoice_row, deposit_raw, amount, confirmations)
                MET_DEPOSITS_PROCESSED.inc()
                return True

        # Amount-differentiation fallback
        matches = []
        for candidate in candidates:
            adj = amount_diff.adjusted_amount_for_invoice(Decimal(str(candidate.publish_amount)), candidate.id, candidate.network, AMOUNT_DIFF_K)
            if adj == amount:
                matches.append(candidate)

        if len(matches) == 1:
            # single deterministic match -> credit
            invoice_row = (await session.execute(select(Invoice).where(Invoice.id == matches[0].id).with_for_update())).scalar_one()
            if invoice_row.status != "pending":
                logger.info("Matched invoice no longer pending for tx=%s", deposit_raw.tx_id)
                return False
            await _credit_invoice(session, invoice_row, deposit_raw, amount, confirmations, used_amount_diff=True)
            MET_DEPOSITS_PROCESSED.inc()
            return True
        elif len(matches) > 1:
            # Collision detected
            MET_COLLISIONS.inc()
            logger.warning("Amount-diff collision for tx=%s matches=%s", deposit_raw.tx_id, [str(m.id) for m in matches])
            # Mark invoices pending_manual_resolution and write audit/system_event
            for inv in matches:
                inv_pending = (await session.execute(select(Invoice).where(Invoice.id == inv.id).with_for_update())).scalar_one()
                inv_pending.status = "pending_manual_resolution"
            # Create audit log and system event
            audit = AuditLog(actor="poller", action="collision_detected", details={"tx": deposit_raw.tx_id, "matches": [str(m.id) for m in matches]})
            session.add(audit)
            se = SystemEvent(source="poller", event_type="collision", payload={"tx": deposit_raw.tx_id, "matches": [str(m.id) for m in matches]})
            session.add(se)
            # Leave deposit_raw.processed = false for manual handling
            return False
        else:
            # no matches found
            logger.info("No amount-diff match for tx=%s", deposit_raw.tx_id)
            return False
    except Exception:
        MET_DEPOSITS_ERRORS.inc()
        logger.exception("Error during try_match_and_credit for tx=%s", deposit_raw.tx_id)
        raise


async def _credit_invoice(session: AsyncSession, invoice_row: Invoice, deposit_raw: DepositRaw, amount: Decimal, confirmations: int, used_amount_diff: bool = False):
    """
    Perform the atomic writes: Payment, LedgerEntry, invoice status update, deposit_raw.processed, webhook queue.
    Assumes caller has acquired SELECT FOR UPDATE on invoice_row and is within a transaction.
    """
    payment = Payment(
        invoice_id=invoice_row.id,
        deposit_raw_id=deposit_raw.id,
        tx_id=deposit_raw.tx_id,
        amount=amount,
        network=deposit_raw.network,
        address=deposit_raw.address,
        address_tag=deposit_raw.address_tag,
        status="settled",
        metadata={"used_amount_diff": used_amount_diff}
    )
    session.add(payment)
    await session.flush()
    ledger = LedgerEntry(
        merchant_id=invoice_row.merchant_id,
        change_amount=amount,
        currency="USDT",
        entry_type="credit_invoice",
        reference_id=payment.id,
        metadata={"invoice_id": str(invoice_row.id), "tx_id": deposit_raw.tx_id, "confirmations": confirmations}
    )
    session.add(ledger)
    # transition invoice and mark deposit processed
    invoice_row.status = "paid"
    deposit_raw.processed = True
    # enqueue webhook
    payload = {
        "invoiceId": str(invoice_row.id),
        "merchantId": str(invoice_row.merchant_id),
        "status": "paid",
        "amount": str(amount),
        "network": deposit_raw.network,
        "txHash": deposit_raw.tx_id,
        "confirmations": confirmations,
        "confirmedAt": deposit_raw.complete_time_ms,
        "metadata": {"used_amount_diff": used_amount_diff}
    }
    queue = WebhookQueue(merchant_id=invoice_row.merchant_id, payload=payload, headers={})
    session.add(queue)
    await session.flush()
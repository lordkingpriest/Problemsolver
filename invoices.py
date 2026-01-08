from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, condecimal
from decimal import Decimal
import uuid
from typing import Optional
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.db.models import Invoice, AuditLog, SystemEvent
from app.poller.amount_diff import adjusted_amount_for_invoice
import logging

logger = logging.getLogger("problemsolver.api.invoices")
router = APIRouter()

# Config
MAX_INVOICE_CREATION_ATTEMPTS = int(getattr(settings, "INVOICE_CREATION_MAX_ATTEMPTS", 5))
AMOUNT_DIFF_K = int(getattr(settings, "AMOUNT_DIFF_K", 3))


# NOTE: Replace this dependency with real API key / merchant auth in production
async def get_current_merchant():
    """
    Placeholder merchant retrieval. In production, authenticate via API key and return merchant_id.
    For now, tests will pass merchant_id in the payload.
    """
    return None


class InvoiceCreateReq(BaseModel):
    merchant_id: uuid.UUID
    base_amount: condecimal(gt=0)  # positive decimal
    currency: Optional[str] = "USDT"
    network: Optional[str] = None
    address: Optional[str] = None
    address_tag: Optional[str] = None
    expiry_seconds: Optional[int] = None
    metadata: Optional[dict] = None


class InvoiceResp(BaseModel):
    invoice_id: uuid.UUID
    publish_amount: Decimal
    currency: str
    network: Optional[str]
    address: Optional[str]
    address_tag: Optional[str]
    status: str


@router.post("/api/invoices", response_model=InvoiceResp, status_code=status.HTTP_201_CREATED)
async def create_invoice(req: InvoiceCreateReq):
    """
    Create invoice with deterministic amount-differentiation applied.
    Algorithm:
      - pick base_uuid_int = random 128-bit int
      - for attempt in [0..MAX_ATTEMPTS-1]:
          candidate_uuid_int = (base_uuid_int + attempt) % (2**128)
          candidate_uuid = uuid.UUID(int=candidate_uuid_int)
          adjusted_amount = adjusted_amount_for_invoice(base_amount, candidate_uuid, network, k)
          try to insert invoice with id=candidate_uuid and publish_amount=adjusted_amount
          if success -> return
      - if all attempts exhaust -> create invoice with status 'pending_manual_resolution' and emit AuditLog/SystemEvent and return 202 or error
    """
    base_amount = Decimal(str(req.base_amount))
    network = req.network
    address = req.address
    merchant_id = req.merchant_id

    base_uuid_int = uuid.uuid4().int
    two128 = 1 << 128

    async with AsyncSessionLocal() as session:
        for attempt in range(MAX_INVOICE_CREATION_ATTEMPTS):
            # Candidate invoice UUID deterministically derived
            cand_int = (base_uuid_int + attempt) % two128
            cand_uuid = uuid.UUID(int=cand_int)
            adjusted_amount = adjusted_amount_for_invoice(base_amount, cand_uuid, network, AMOUNT_DIFF_K)
            # Create invoice row with deterministic id
            invoice = Invoice(
                id=cand_uuid,
                merchant_id=merchant_id,
                publish_amount=adjusted_amount,
                currency=req.currency or "USDT",
                network=network,
                address=address,
                address_tag=req.address_tag,
                status="pending",
                publish_metadata=req.metadata or {},
            )
            try:
                async with session.begin():
                    session.add(invoice)
                    # attempt to flush (this will raise IntegrityError if partial unique constraint violated)
                    await session.flush()
                # success
                logger.info("Created invoice %s merchant=%s amount=%s", invoice.id, merchant_id, adjusted_amount)
                return InvoiceResp(
                    invoice_id=invoice.id,
                    publish_amount=adjusted_amount,
                    currency=invoice.currency,
                    network=invoice.network,
                    address=invoice.address,
                    address_tag=invoice.address_tag,
                    status=invoice.status
                )
            except IntegrityError as ie:
                # Could be unique constraint violation on (merchant_id, publish_amount, address)
                await session.rollback()
                logger.warning("Invoice creation collision on attempt=%s invoice_id=%s err=%s", attempt, cand_uuid, ie)
                continue
            except Exception:
                await session.rollback()
                logger.exception("Invoice creation unexpected error attempt=%s", attempt)
                raise HTTPException(status_code=500, detail="invoice_creation_failed")

        # Exhausted attempts -> create an invoice placeholder or escalate
        # Create an invoice record flagged for manual resolution (no publish_amount set or special status)
        try:
            async with session.begin():
                failure_invoice = Invoice(
                    merchant_id=merchant_id,
                    publish_amount=base_amount,
                    currency=req.currency or "USDT",
                    network=network,
                    address=address,
                    address_tag=req.address_tag,
                    status="pending_manual_resolution",
                    publish_metadata={"note": "amount-diff-collision", "attempts": MAX_INVOICE_CREATION_ATTEMPTS},
                )
                session.add(failure_invoice)
                audit = AuditLog(actor="invoice_service", action="invoice_creation_collision_exhausted", details={"merchant_id": str(merchant_id), "base_amount": str(base_amount)})
                session.add(audit)
                se = SystemEvent(source="invoice_service", event_type="collision_exhausted", payload={"merchant_id": str(merchant_id), "base_amount": str(base_amount)})
                session.add(se)
                await session.flush()
            raise HTTPException(status_code=409, detail="invoice_creation_collision")
        except Exception:
            await session.rollback()
            logger.exception("Failed to create manual-resolution invoice")
            raise HTTPException(status_code=500, detail="invoice_creation_failed")
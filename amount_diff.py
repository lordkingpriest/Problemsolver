"""
Amount-differentiation helper.

Strategy:
- Reserve k least-significant digits to encode a deterministic invoiceIndex.
- invoiceIndex := int(invoice_uuid.hex, 16) % (10**k)
- delta := invoiceIndex * 10^-k
- adjusted_amount := base_amount + delta
- Round adjusted_amount to network precision (network decimal places) to avoid impossible precision.

Network precisions (from spec):
- ERC20 (USDT token on Ethereum): 6 decimals
- TRC20 (TRON): 6 decimals
- BEP20 (BSC): 18 decimals

This module is deterministic and has no side-effects. Use Decimal for monetary arithmetic.
"""
from decimal import Decimal, getcontext, ROUND_DOWN
import uuid
from typing import Tuple

# network -> decimals mapping
NETWORK_PRECISIONS = {
    "ERC20": 6,
    "ETH": 6,
    "TRC20": 6,
    "TRON": 6,
    "BEP20": 18,
    "BSC": 18,
}

DEFAULT_PRECISION = 6  # conservative default if unknown

def network_precision(network: str | None) -> int:
    if not network:
        return DEFAULT_PRECISION
    return NETWORK_PRECISIONS.get(network.upper(), DEFAULT_PRECISION)

def invoice_index_from_uuid(invoice_id: uuid.UUID, k: int) -> int:
    """
    Deterministically derive invoiceIndex from invoice UUID.
    Returns integer in [0, 10^k - 1].
    """
    if k <= 0:
        return 0
    hex_val = invoice_id.hex  # 32 hex chars
    num = int(hex_val, 16)
    modulus = 10 ** k
    return num % modulus

def compute_delta(invoice_id: uuid.UUID, k: int) -> Decimal:
    """
    Compute delta Decimal for given invoice_id and k reserved digits.
    Example: k=3 => delta in increments of 0.001
    """
    idx = invoice_index_from_uuid(invoice_id, k)
    # Use Decimal arithmetic
    getcontext().prec = 50
    return Decimal(idx) * (Decimal(10) ** (-k))

def adjusted_amount_for_invoice(base_amount: Decimal, invoice_id: uuid.UUID, network: str | None, k: int) -> Decimal:
    """
    Return adjusted amount as base + delta, rounded (quantized) to the network precision.
    """
    prec = network_precision(network)
    # Ensure high precision for addition
    getcontext().prec = max(50, prec + k + 10)
    delta = compute_delta(invoice_id, k)
    raw = (Decimal(base_amount) + delta)
    # Quantize to network precision (ROUND_DOWN to be deterministic and safe)
    quant = Decimal(1).scaleb(-prec)  # Decimal('0.000001') for prec=6
    adjusted = raw.quantize(quant, rounding=ROUND_DOWN)
    return adjusted

def decompose_adjusted_amount(adjusted_amount: Decimal, base_amount: Decimal, k: int) -> Tuple[Decimal, Decimal]:
    """
    For debugging: return (delta, fractional) where delta = adjusted - base.
    """
    getcontext().prec = 50
    delta = Decimal(adjusted_amount) - Decimal(base_amount)
    return delta, delta  # same value (placeholder)
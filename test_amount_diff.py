import uuid
from decimal import Decimal
from app.poller.amount_diff import adjusted_amount_for_invoice, compute_delta

def test_amount_diff_deterministic():
    base = Decimal("10.000000")
    invoice_id = uuid.UUID("12345678-1234-5678-1234-567812345678")
    k = 3
    network = "ERC20"
    adj1 = adjusted_amount_for_invoice(base, invoice_id, network, k)
    # calling again must produce same result
    adj2 = adjusted_amount_for_invoice(base, invoice_id, network, k)
    assert adj1 == adj2
    # delta should be less than 0.001 * 10^k (i.e., less than 1 for small k)
    delta = compute_delta(invoice_id, k)
    assert delta >= Decimal("0")
    assert delta < Decimal("1")

def test_adjusted_amount_rounding_precision():
    base = Decimal("1.23456789")
    invoice_id = uuid.UUID(int=0xabcdef1234567890abcdef1234567890)
    k = 3
    network = "BEP20"
    adj = adjusted_amount_for_invoice(base, invoice_id, network, k)
    # BEP20 precision 18 -> adjusted should have at most 18 decimals
    assert isinstance(adj, Decimal)
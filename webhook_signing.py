import hmac
import hashlib
from typing import Union


def sign_webhook(payload: Union[bytes, str], timestamp: str, secret: str) -> str:
    """
    Sign webhook payloads with WEBHOOK_SECRET.
    Signature header format: sha256=<hex>
    Data to sign: <timestamp>.<payload>
    """
    if isinstance(payload, str):
        payload_bytes = payload.encode("utf-8")
    else:
        payload_bytes = payload
    message = timestamp.encode("utf-8") + b"." + payload_bytes
    mac = hmac.new(secret.encode("utf-8"), message, hashlib.sha256)
    return "sha256=" + mac.hexdigest()


def verify_webhook_signature(payload: Union[bytes, str], timestamp: str, secret: str, signature: str, tolerance_seconds: int = 300) -> bool:
    """
    Verify the signature and (optionally) timestamp age.
    - signature expected to be 'sha256=<hex>'
    - timestamp is an ISO or unix string; timestamp age check is left to the caller (returns boolean).
    """
    expected = sign_webhook(payload, timestamp, secret)
    return hmac.compare_digest(expected, signature)
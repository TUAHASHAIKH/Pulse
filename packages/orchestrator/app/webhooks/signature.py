"""
Pulse Orchestrator — GitHub Webhook Signature Verification

Verifies that incoming webhook payloads actually came from GitHub,
not from a random attacker hitting our endpoint.

How it works:
  1. When you register a webhook on GitHub, you set a "secret" string.
  2. GitHub sends every webhook with an X-Hub-Signature-256 header
     containing HMAC-SHA256(secret, raw_body).
  3. We compute the same HMAC on our side and compare.
  4. If they match → payload is authentic. If not → reject with 401.

We use hmac.compare_digest() for timing-safe comparison,
preventing timing attacks that could leak the secret.
"""

import hashlib
import hmac


def verify_github_signature(
    payload_body: bytes,
    signature_header: str,
    secret: str,
) -> bool:
    """
    Verify a GitHub webhook signature.

    Args:
        payload_body: The raw request body bytes (NOT parsed JSON —
                      we must hash the exact bytes GitHub sent).
        signature_header: The X-Hub-Signature-256 header value,
                          e.g. "sha256=abc123..."
        secret: The webhook secret configured in GitHub and in our .env.

    Returns:
        True if the signature is valid, False otherwise.
    """
    if not signature_header:
        return False

    # GitHub sends "sha256=<hex_digest>"
    if not signature_header.startswith("sha256="):
        return False

    expected_signature = signature_header[7:]  # strip "sha256=" prefix

    # Compute HMAC-SHA256 of the raw body using our secret
    computed_hmac = hmac.new(
        key=secret.encode("utf-8"),
        msg=payload_body,
        digestmod=hashlib.sha256,
    ).hexdigest()

    # Timing-safe comparison
    return hmac.compare_digest(computed_hmac, expected_signature)

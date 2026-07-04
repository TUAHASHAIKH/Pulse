"""
Unit tests for GitHub webhook signature verification.

These test the cryptographic verification logic independently
of the running server — fast, reliable, no network needed.
"""

import hashlib
import hmac
import pytest

# Add the app directory to the path
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.webhooks.signature import verify_github_signature


class TestVerifyGithubSignature:
    """Tests for the HMAC-SHA256 signature verification."""

    SECRET = "my-webhook-secret"
    PAYLOAD = b'{"action": "opened", "pull_request": {"number": 42}}'

    def _make_signature(self, payload: bytes, secret: str) -> str:
        """Helper: compute a valid GitHub-style signature."""
        digest = hmac.new(
            key=secret.encode("utf-8"),
            msg=payload,
            digestmod=hashlib.sha256,
        ).hexdigest()
        return f"sha256={digest}"

    def test_valid_signature(self):
        """A correctly signed payload should return True."""
        sig = self._make_signature(self.PAYLOAD, self.SECRET)
        assert verify_github_signature(self.PAYLOAD, sig, self.SECRET) is True

    def test_invalid_signature(self):
        """A wrong signature should return False."""
        assert verify_github_signature(
            self.PAYLOAD, "sha256=definitely_wrong", self.SECRET
        ) is False

    def test_empty_signature_header(self):
        """An empty signature header should return False."""
        assert verify_github_signature(self.PAYLOAD, "", self.SECRET) is False

    def test_missing_sha256_prefix(self):
        """A signature without the 'sha256=' prefix should return False."""
        digest = hmac.new(
            key=self.SECRET.encode("utf-8"),
            msg=self.PAYLOAD,
            digestmod=hashlib.sha256,
        ).hexdigest()
        # Missing "sha256=" prefix
        assert verify_github_signature(self.PAYLOAD, digest, self.SECRET) is False

    def test_wrong_secret(self):
        """A signature made with a different secret should return False."""
        sig = self._make_signature(self.PAYLOAD, "wrong-secret")
        assert verify_github_signature(self.PAYLOAD, sig, self.SECRET) is False

    def test_modified_payload(self):
        """If the payload is tampered with, the signature should fail."""
        sig = self._make_signature(self.PAYLOAD, self.SECRET)
        tampered = b'{"action": "opened", "pull_request": {"number": 99}}'
        assert verify_github_signature(tampered, sig, self.SECRET) is False

    def test_different_payloads_different_signatures(self):
        """Two different payloads should produce different valid signatures."""
        payload_a = b'{"pr": 1}'
        payload_b = b'{"pr": 2}'
        sig_a = self._make_signature(payload_a, self.SECRET)
        sig_b = self._make_signature(payload_b, self.SECRET)
        assert sig_a != sig_b
        assert verify_github_signature(payload_a, sig_a, self.SECRET) is True
        assert verify_github_signature(payload_b, sig_b, self.SECRET) is True
        # Cross-check: wrong payload with wrong signature should fail
        assert verify_github_signature(payload_a, sig_b, self.SECRET) is False

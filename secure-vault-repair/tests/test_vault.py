"""
Tests for the Secure Vault Pipeline
=====================================
Validates the correctness of the vault output by checking:
- Structural integrity of output files
- Cryptographic correctness of sealed messages
- Statistical accuracy of vault metrics
- Per-message authentication tag verification
"""

import json
import base64
import hashlib
import os
import pytest

RUNTIME_DIR = "/app/runtime"
VAULT_OUTPUT_PATH = os.path.join(RUNTIME_DIR, "vault_output.json")
VAULT_STATS_PATH = os.path.join(RUNTIME_DIR, "vault_stats.json")


@pytest.fixture(scope="module")
def vault_output():
    """Load vault output JSON."""
    with open(VAULT_OUTPUT_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


@pytest.fixture(scope="module")
def vault_stats():
    """Load vault stats JSON."""
    with open(VAULT_STATS_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def _get_message_by_id(vault_output, msg_id):
    """Helper to find a sealed message by ID."""
    for msg in vault_output["sealed_messages"]:
        if msg["id"] == msg_id:
            return msg
    return None


def test_output_files_exist():
    """Both vault_output.json and vault_stats.json must exist."""
    assert os.path.isfile(VAULT_OUTPUT_PATH), f"Missing: {VAULT_OUTPUT_PATH}"
    assert os.path.isfile(VAULT_STATS_PATH), f"Missing: {VAULT_STATS_PATH}"


def test_vault_id_matches(vault_output):
    """Vault ID in output must match the configured value."""
    assert vault_output["vault_id"] == "vault-2024-alpha"
    assert vault_output["total_sealed"] == 5
    assert len(vault_output["sealed_messages"]) == 5


def test_message_ids_preserved(vault_output):
    """All message IDs from config must appear in output with correct structure."""
    expected_ids = {"msg-001", "msg-002", "msg-003", "msg-004", "msg-005"}
    actual_ids = {msg["id"] for msg in vault_output["sealed_messages"]}
    assert actual_ids == expected_ids
    # Each message must have all required fields
    for msg in vault_output["sealed_messages"]:
        assert "ciphertext_b64" in msg
        assert "hmac_tag_hex" in msg
        assert "nonce_hex" in msg
        assert "padded_length" in msg


def test_key_fingerprint_value(vault_output):
    """Key fingerprint must be exactly '772c8de1' (8 hex chars of SHA-256 of encryption key)."""
    kfp = vault_output["key_fingerprint"]
    assert len(kfp) == 8, f"Key fingerprint length {len(kfp)}, expected 8"
    assert all(c in '0123456789abcdef' for c in kfp), "Key fingerprint must be lowercase hex"
    assert kfp == "772c8de1", f"Key fingerprint '{kfp}' does not match expected '772c8de1'"


def test_all_ciphertext_b64_decodable(vault_output):
    """All ciphertext_b64 values must be valid standard Base64 with correct padding."""
    for msg in vault_output["sealed_messages"]:
        b64_str = msg["ciphertext_b64"]
        # Must use standard Base64 alphabet (not URL-safe)
        assert '_' not in b64_str and '-' not in b64_str, (
            f"{msg['id']}: uses URL-safe alphabet instead of standard Base64"
        )
        # Must have proper = padding (length must be multiple of 4)
        assert len(b64_str) % 4 == 0, (
            f"{msg['id']}: Base64 length {len(b64_str)} not multiple of 4 (missing padding)"
        )
        # Must be valid standard Base64
        try:
            decoded = base64.b64decode(b64_str, validate=True)
        except Exception as e:
            pytest.fail(f"{msg['id']}: not valid Base64: {e}")
        # Decoded length must match padded_length
        assert len(decoded) == msg["padded_length"], (
            f"{msg['id']}: decoded length {len(decoded)} != padded_length {msg['padded_length']}"
        )


def test_padded_lengths_correct(vault_output):
    """All padded_length values must be 48 (correct PKCS#7 for these message sizes)."""
    # msg-001: 37 bytes -> pad to 48 (11 bytes padding)
    # msg-002: 37 bytes -> pad to 48 (11 bytes padding)
    # msg-003: 35 bytes -> pad to 48 (13 bytes padding)
    # msg-004: 43 bytes -> pad to 48 (5 bytes padding)
    # msg-005: 39 bytes -> pad to 48 (9 bytes padding)
    for msg in vault_output["sealed_messages"]:
        pad_len = msg["padded_length"]
        assert pad_len == 48, f"{msg['id']}: padded_length {pad_len} != expected 48"
        assert pad_len % 16 == 0, f"{msg['id']}: padded_length not multiple of 16"


def test_total_byte_counts(vault_stats):
    """Total plaintext bytes must be 191, ciphertext and padded must both be 240, ratio = 1.256545."""
    assert vault_stats["total_plaintext_bytes"] == 191
    assert vault_stats["total_ciphertext_bytes"] == 240
    assert vault_stats["total_padded_bytes"] == 240
    assert vault_stats["total_ciphertext_bytes"] == vault_stats["total_padded_bytes"]
    # Expansion ratio must be exactly 240/191
    ratio = vault_stats["avg_expansion_ratio"]
    assert abs(ratio - 1.256545) < 0.000001, f"Expansion ratio {ratio} != 1.256545"


def test_hmac_verified_flag(vault_stats):
    """HMAC verified flag must be True and key_derivation_rounds must be 10000."""
    assert vault_stats["hmac_verified"] is True
    assert vault_stats["key_derivation_rounds"] == 10000


def test_hmac_tag_msg001(vault_output):
    """HMAC tag for msg-001 must start with the expected prefix (verifies KDF + cipher + HMAC correctness)."""
    msg = _get_message_by_id(vault_output, "msg-001")
    assert msg is not None, "msg-001 not found in output"
    tag = msg["hmac_tag_hex"]
    assert len(tag) == 64, f"HMAC tag length {len(tag)} != 64"
    assert tag.startswith("27abc6c3f3e9d9ed"), (
        f"msg-001 HMAC tag prefix '{tag[:16]}' != expected '27abc6c3f3e9d9ed'"
    )


def test_hmac_tag_msg002(vault_output):
    """HMAC tag for msg-002 must start with the expected prefix."""
    msg = _get_message_by_id(vault_output, "msg-002")
    assert msg is not None, "msg-002 not found in output"
    tag = msg["hmac_tag_hex"]
    assert len(tag) == 64
    assert tag.startswith("4bc9e1becd70255c"), (
        f"msg-002 HMAC tag prefix '{tag[:16]}' != expected '4bc9e1becd70255c'"
    )


def test_hmac_tag_msg003(vault_output):
    """HMAC tag for msg-003 must start with the expected prefix."""
    msg = _get_message_by_id(vault_output, "msg-003")
    assert msg is not None, "msg-003 not found in output"
    tag = msg["hmac_tag_hex"]
    assert len(tag) == 64
    assert tag.startswith("1d0c5e82955ffa75"), (
        f"msg-003 HMAC tag prefix '{tag[:16]}' != expected '1d0c5e82955ffa75'"
    )


def test_hmac_tag_msg004(vault_output):
    """HMAC tag for msg-004 must start with the expected prefix."""
    msg4 = _get_message_by_id(vault_output, "msg-004")
    assert msg4 is not None, "msg-004 not found"
    assert msg4["hmac_tag_hex"].startswith("3f30e7a855a42aa3"), (
        f"msg-004 HMAC prefix '{msg4['hmac_tag_hex'][:16]}' != '3f30e7a855a42aa3'"
    )


def test_hmac_tag_msg005(vault_output):
    """HMAC tag for msg-005 must start with the expected prefix."""
    msg5 = _get_message_by_id(vault_output, "msg-005")
    assert msg5 is not None, "msg-005 not found"
    assert msg5["hmac_tag_hex"].startswith("05505551cadd6e38"), (
        f"msg-005 HMAC prefix '{msg5['hmac_tag_hex'][:16]}' != '05505551cadd6e38'"
    )


def test_integrity_checksum(vault_stats):
    """Integrity checksum must match the expected value."""
    assert vault_stats["integrity_checksum"] == "c36368ef2691420a"


def test_nonce_uniqueness(vault_output):
    """All 5 messages must have different nonces with the correct prefix and format."""
    nonces = [msg["nonce_hex"] for msg in vault_output["sealed_messages"]]
    assert len(set(nonces)) == 5, f"Nonce collision detected"
    # All nonces must start with the configured prefix
    for nonce in nonces:
        assert nonce.startswith("4e6f6e636530303031"), (
            f"Nonce {nonce} missing expected prefix '4e6f6e636530303031'"
        )
    # Each nonce must be 32 hex chars (16 bytes)
    for nonce in nonces:
        assert len(nonce) == 32, f"Nonce length {len(nonce)} != 32 hex chars"

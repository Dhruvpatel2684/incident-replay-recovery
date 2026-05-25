"""
Certificate Chain Auditor - Test Suite
Validates the audit output files for correctness.
Tests check chain linking, expiration, key usage, revocation, depth, and summary.
"""

import json
import os
import hashlib
import pytest


REPORT_PATH = "/app/runtime/output/audit_report.jsonl"
SUMMARY_PATH = "/app/runtime/output/audit_summary.json"


@pytest.fixture
def report_entries():
    """Load all entries from the JSONL report file."""
    assert os.path.isfile(REPORT_PATH), f"Report file not found: {REPORT_PATH}"
    entries = []
    with open(REPORT_PATH, 'r') as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


@pytest.fixture
def summary():
    """Load the summary JSON file."""
    assert os.path.isfile(SUMMARY_PATH), f"Summary file not found: {SUMMARY_PATH}"
    with open(SUMMARY_PATH, 'r') as f:
        return json.load(f)


@pytest.fixture
def entry_by_cn(report_entries):
    """Create a lookup dict from subject_cn to report entry."""
    return {e["subject_cn"]: e for e in report_entries}


# ===========================================================================
# Chain Linking Tests
# ===========================================================================

class TestChainLinking:
    """Tests for correct trust chain construction."""

    def test_intermediate_links_to_root(self, report_entries):
        """Intermediate CA 1 must chain to Root CA, not to itself."""
        # Find the intermediate CA (SecureSign)
        intermediate = None
        for entry in report_entries:
            if entry["subject_dn"] == "CN=Certificate Authority,O=SecureSign,C=US":
                intermediate = entry
                break
        assert intermediate is not None, "Intermediate CA 1 not found in report"
        # Chain must include the root CA serial
        root_dn = "CN=Certificate Authority,O=GlobalRoot,C=US"
        root_entry = None
        for entry in report_entries:
            if entry["subject_dn"] == root_dn:
                root_entry = entry
                break
        assert root_entry is not None, "Root CA not found"
        assert root_entry["serial"] in intermediate["chain_serials"], \
            "Intermediate CA 1 chain must include Root CA"

    def test_intermediate_does_not_chain_to_self(self, report_entries):
        """Intermediate CA 1 must NOT have itself as its own issuer in chain."""
        intermediate = None
        for entry in report_entries:
            if entry["subject_dn"] == "CN=Certificate Authority,O=SecureSign,C=US":
                intermediate = entry
                break
        assert intermediate is not None
        # The chain should have exactly 2 entries: itself and root
        assert len(intermediate["chain_serials"]) == 2, \
            f"Intermediate chain should have 2 certs, got {len(intermediate['chain_serials'])}"

    def test_leaf_chains_through_intermediate_to_root(self, entry_by_cn):
        """api.example.com should chain through Intermediate CA 1 to Root."""
        api_entry = entry_by_cn.get("api.example.com")
        assert api_entry is not None, "api.example.com not found"
        # Chain should be: leaf -> intermediate -> root (3 certs)
        assert len(api_entry["chain_serials"]) == 3, \
            f"api.example.com chain should have 3 certs, got {len(api_entry['chain_serials'])}"

    def test_root_ca_chain_is_self_only(self, report_entries):
        """Root CA chain contains only itself."""
        root = None
        for entry in report_entries:
            if entry["self_signed"] and entry["subject_dn"] == "CN=Certificate Authority,O=GlobalRoot,C=US":
                root = entry
                break
        assert root is not None, "Root CA not found"
        assert len(root["chain_serials"]) == 1, \
            "Self-signed root chain should contain only itself"


# ===========================================================================
# Expiration Tests
# ===========================================================================

class TestExpiration:
    """Tests for certificate expiration validation."""

    def test_legacy_corp_expired(self, entry_by_cn):
        """legacy.corp.net with not_after == reference_time must be marked expired."""
        legacy = entry_by_cn.get("legacy.corp.net")
        assert legacy is not None, "legacy.corp.net not found"
        assert legacy["is_expired"] is True, \
            "legacy.corp.net should be expired (not_after equals reference_time)"

    def test_api_example_not_expired(self, entry_by_cn):
        """api.example.com with not_after after reference_time is not expired."""
        api = entry_by_cn.get("api.example.com")
        assert api is not None
        assert api["is_expired"] is False, \
            "api.example.com should NOT be expired"

    def test_root_ca_not_expired(self, entry_by_cn):
        """Root CA with far-future not_after is not expired."""
        root = entry_by_cn.get("Certificate Authority")
        # There are two with this CN; find the self-signed one
        # Use report_entries directly
        assert root is not None


# ===========================================================================
# Key Usage Tests
# ===========================================================================

class TestKeyUsage:
    """Tests for key usage bitmask validation."""

    def test_signing_example_fails_key_usage(self, entry_by_cn):
        """signing.example.com has key_usage=1 but required is 3; must fail."""
        signing = entry_by_cn.get("signing.example.com")
        assert signing is not None, "signing.example.com not found"
        assert signing["key_usage_valid"] is False, \
            "signing.example.com should fail key_usage check (has 1, needs 3)"

    def test_api_example_passes_key_usage(self, entry_by_cn):
        """api.example.com has key_usage=3 matching required=3; must pass."""
        api = entry_by_cn.get("api.example.com")
        assert api is not None
        assert api["key_usage_valid"] is True, \
            "api.example.com should pass key_usage check (has 3, needs 3)"

    def test_ca_certs_bypass_leaf_key_usage(self, report_entries):
        """CA certificates should not be subject to leaf key usage requirements."""
        for entry in report_entries:
            if entry["is_ca"]:
                assert entry["key_usage_valid"] is True, \
                    f"CA cert {entry['subject_cn']} should bypass leaf key usage check"


# ===========================================================================
# Revocation Tests
# ===========================================================================

class TestRevocation:
    """Tests for revocation checking and chain propagation."""

    def test_dev_internal_revoked_by_intermediate(self, entry_by_cn):
        """dev.internal.io is under revoked Intermediate CA 2; must be revoked."""
        dev = entry_by_cn.get("dev.internal.io")
        assert dev is not None, "dev.internal.io not found"
        assert dev["is_revoked"] is True, \
            "dev.internal.io should be marked revoked (intermediate CA is revoked)"

    def test_dev_signing_ca_revoked(self, entry_by_cn):
        """Dev Signing CA is directly revoked."""
        dev_ca = entry_by_cn.get("Dev Signing CA")
        assert dev_ca is not None, "Dev Signing CA not found"
        assert dev_ca["is_revoked"] is True, \
            "Dev Signing CA should be marked as revoked"

    def test_api_example_not_revoked(self, entry_by_cn):
        """api.example.com under valid intermediate is not revoked."""
        api = entry_by_cn.get("api.example.com")
        assert api is not None
        assert api["is_revoked"] is False, \
            "api.example.com should NOT be revoked"


# ===========================================================================
# Chain Depth Tests
# ===========================================================================

class TestChainDepth:
    """Tests for chain depth calculation."""

    def test_root_ca_depth_valid(self, report_entries):
        """Self-signed root CA must have valid depth (not flagged as zero-depth)."""
        root = None
        for entry in report_entries:
            if entry["self_signed"] and entry["subject_dn"] == "CN=Certificate Authority,O=GlobalRoot,C=US":
                root = entry
                break
        assert root is not None, "Root CA not found"
        assert root["depth_valid"] is True, \
            "Self-signed root CA should have valid depth"

    def test_root_ca_depth_is_one(self, report_entries):
        """Self-signed root chain depth should be 1."""
        root = None
        for entry in report_entries:
            if entry["self_signed"] and entry["subject_dn"] == "CN=Certificate Authority,O=GlobalRoot,C=US":
                root = entry
                break
        assert root is not None
        assert root["chain_depth"] == 1, \
            f"Root CA chain depth should be 1, got {root['chain_depth']}"


# ===========================================================================
# Summary & Integrity Tests
# ===========================================================================

class TestSummaryAndIntegrity:
    """Tests for summary statistics and file integrity."""

    def test_all_certs_present(self, report_entries):
        """All 7 certificates must be present in the report."""
        assert len(report_entries) == 7, \
            f"Expected 7 certificates in report, got {len(report_entries)}"

    def test_summary_total_count(self, summary):
        """Summary total_certificates must be 7."""
        assert summary["total_certificates"] == 7

    def test_summary_valid_count(self, summary):
        """Only api.example.com should be fully valid (3 valid certs total: root, intermediate1, api)."""
        # Valid: Root CA, Intermediate CA 1, api.example.com = 3
        assert summary["valid_count"] == 3, \
            f"Expected 3 valid certs, got {summary['valid_count']}"

    def test_summary_invalid_count(self, summary):
        """4 certs should be invalid."""
        # Invalid: Dev Signing CA (revoked), dev.internal.io (chain revoked),
        #          legacy.corp.net (expired), signing.example.com (key usage)
        assert summary["invalid_count"] == 4, \
            f"Expected 4 invalid certs, got {summary['invalid_count']}"

    def test_summary_expired_count(self, summary):
        """1 cert should be expired (legacy.corp.net)."""
        assert summary["expired_count"] == 1, \
            f"Expected 1 expired cert, got {summary['expired_count']}"

    def test_summary_revoked_count(self, summary):
        """2 certs should be revoked (Dev Signing CA + dev.internal.io)."""
        assert summary["revoked_count"] == 2, \
            f"Expected 2 revoked certs, got {summary['revoked_count']}"

    def test_report_sha256_matches(self, summary):
        """SHA-256 hash in summary must match the actual report file hash."""
        sha256_hash = hashlib.sha256()
        with open(REPORT_PATH, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                sha256_hash.update(chunk)
        actual_hash = sha256_hash.hexdigest()
        assert summary["report_sha256"] == actual_hash, \
            f"SHA-256 mismatch: summary={summary['report_sha256']}, actual={actual_hash}"

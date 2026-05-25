"""
DNS Zone Resolver — behavioral verification tests.
"""

import hashlib
import json
import os

import pytest

OUTPUT_DIR = "/app/runtime/output"
RESULTS_PATH = os.path.join(OUTPUT_DIR, "resolution_results.jsonl")
SUMMARY_PATH = os.path.join(OUTPUT_DIR, "resolution_summary.json")


def load_results():
    assert os.path.exists(RESULTS_PATH), \
        f"results file missing: {RESULTS_PATH} — resolver must be executed to produce output"
    records = []
    with open(RESULTS_PATH) as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    return records


def load_summary():
    assert os.path.exists(SUMMARY_PATH), \
        f"summary file missing: {SUMMARY_PATH} — resolver must be executed to produce output"
    with open(SUMMARY_PATH) as f:
        return json.load(f)


def get_result(results, name, qtype):
    for r in results:
        if r["name"] == name and r["type"] == qtype:
            return r
    return None


# --- Zone Loading ---

class TestZoneLoading:
    def test_example_com_zone_loaded(self):
        """The example.com zone must be loaded regardless of serial wrap."""
        summary = load_summary()
        assert "example.com" in summary["zones_loaded"], \
            "example.com zone not loaded — serial comparison may be broken"

    def test_internal_dev_zone_loaded(self):
        """The internal.dev zone must be loaded."""
        summary = load_summary()
        assert "internal.dev" in summary["zones_loaded"], \
            "internal.dev zone not loaded"

    def test_serial_in_metadata(self):
        """Loaded zones must report their SOA serial numbers."""
        summary = load_summary()
        for zone_name, meta in summary["zones_loaded"].items():
            assert "serial" in meta, f"zone {zone_name} missing serial in metadata"


# --- Wildcard Precedence ---

class TestWildcardPrecedence:
    def test_exact_match_over_wildcard(self):
        """www.example.com has an exact A record — must not return wildcard."""
        results = load_results()
        r = get_result(results, "www.example.com", "A")
        assert r is not None and r["status"] == "NOERROR", \
            "www.example.com should resolve"
        assert r["answer"] == "93.184.216.34", \
            f"www.example.com should be exact 93.184.216.34, got {r['answer']}"

    def test_wildcard_for_unknown(self):
        """unknown.example.com has no exact record — should match wildcard."""
        results = load_results()
        r = get_result(results, "unknown.example.com", "A")
        assert r is not None and r["status"] == "NOERROR", \
            "unknown.example.com should resolve via wildcard"
        assert r["answer"] == "93.184.216.100", \
            f"unknown.example.com should be wildcard 93.184.216.100, got {r['answer']}"

    def test_app_internal_exact(self):
        """app.internal.dev has an exact record — must not return wildcard."""
        results = load_results()
        r = get_result(results, "app.internal.dev", "A")
        assert r is not None and r["status"] == "NOERROR"
        assert r["answer"] == "10.0.0.50", \
            f"app.internal.dev should be exact 10.0.0.50, got {r['answer']}"

    def test_wildcard_internal(self):
        """random.internal.dev has no exact record — should match wildcard."""
        results = load_results()
        r = get_result(results, "random.internal.dev", "A")
        assert r is not None and r["status"] == "NOERROR"
        assert r["answer"] == "10.0.0.100", \
            f"random.internal.dev should be wildcard 10.0.0.100, got {r['answer']}"


# --- CNAME Chain Resolution ---

class TestCNAMEChains:
    def test_cname_chain_at_max_depth(self):
        """hop1.example.com is a 5-hop chain — must resolve to final A record."""
        results = load_results()
        r = get_result(results, "hop1.example.com", "A")
        assert r is not None, "hop1.example.com result missing"
        assert r["status"] == "NOERROR", \
            f"hop1.example.com should resolve, got {r['status']}"
        assert r["answer"] == "93.184.216.200", \
            f"hop1 chain should resolve to 93.184.216.200, got {r['answer']}"

    def test_cname_short_chain(self):
        """alias.example.com is a 2-hop chain — should resolve normally."""
        results = load_results()
        r = get_result(results, "alias.example.com", "A")
        assert r is not None and r["status"] == "NOERROR"
        assert r["answer"] == "93.184.216.75", \
            f"alias chain should resolve to 93.184.216.75, got {r['answer']}"

    def test_cname_chain_in_answer(self):
        """Chain queries should include the resolution path."""
        results = load_results()
        r = get_result(results, "hop1.example.com", "A")
        assert r is not None
        assert len(r.get("chain", [])) >= 4, \
            f"hop1 chain should show resolution path, got {r.get('chain', [])}"

    def test_no_cname_loops(self):
        """No query should produce a SERVFAIL from infinite CNAME loops."""
        results = load_results()
        for r in results:
            if r["status"] == "SERVFAIL":
                assert "loop" not in r.get("error", "").lower(), \
                    f"CNAME loop detected for {r['name']}"


# --- MX Through CNAME ---

class TestMXResolution:
    def test_mx_through_cname(self):
        """mail.example.com MX should resolve through CNAME to mx-pool."""
        results = load_results()
        r = get_result(results, "mail.example.com", "MX")
        assert r is not None, "mail.example.com MX result missing"
        assert r["status"] == "NOERROR", \
            f"mail.example.com MX should resolve, got {r['status']}"
        assert "mx-pool" in str(r.get("answer", "")), \
            f"mail MX should resolve to mx-pool, got {r.get('answer')}"


# --- Cache & TTL ---

class TestCacheTTL:
    def test_ttl_values_present(self):
        """Each resolved result must include a TTL value."""
        results = load_results()
        for r in results:
            assert "ttl" in r, f"result for {r['name']} missing ttl field"

    def test_cached_record_has_correct_ttl(self):
        """cached.example.com has explicit TTL 60 in zone file."""
        results = load_results()
        r = get_result(results, "cached.example.com", "A")
        assert r is not None and r["status"] == "NOERROR"
        assert r["ttl"] == 60, \
            f"cached.example.com TTL should be 60, got {r.get('ttl')}"


# --- Output Integrity ---

class TestOutputIntegrity:
    def test_sha256_matches_file(self):
        """SHA-256 in summary must match the results file content."""
        summary = load_summary()
        stored = summary["results_sha256"]
        with open(RESULTS_PATH) as f:
            content = f.read()
        lines = [l for l in content.split("\n") if l.strip()]
        computed = hashlib.sha256("\n".join(lines).encode()).hexdigest()
        assert stored == computed, "integrity hash does not match results file"

    def test_record_count_matches_queries(self):
        """Output must have one result per input query."""
        results = load_results()
        summary = load_summary()
        assert summary["total_queries"] == len(results), \
            "query count mismatch between summary and results"
        assert len(results) == 10, f"expected 10 results, got {len(results)}"

    def test_all_results_have_status(self):
        """Every result must have a valid status code."""
        results = load_results()
        valid = {"NOERROR", "NXDOMAIN", "SERVFAIL"}
        for r in results:
            assert r["status"] in valid, \
                f"{r['name']}: invalid status {r['status']}"

    def test_resolved_count_correct(self):
        """Summary resolved_count must match actual NOERROR results."""
        results = load_results()
        summary = load_summary()
        actual = sum(1 for r in results if r["status"] == "NOERROR")
        assert summary["resolved_count"] == actual, \
            f"resolved_count mismatch: summary={summary['resolved_count']} actual={actual}"

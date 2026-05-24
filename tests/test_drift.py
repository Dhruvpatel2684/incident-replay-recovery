"""
Behavioral validation for the configuration drift reconciler.
Verifies drift detection accuracy, compliance scoring, and report integrity.
"""

import hashlib
import json
import os

# Harbor container paths
RUNTIME_DIR = "/app/runtime"
OUTPUT_DIR = os.path.join(RUNTIME_DIR, "output")
DRIFT_REPORT = os.path.join(OUTPUT_DIR, "drift_report.jsonl")
COMPLIANCE_SUMMARY = os.path.join(OUTPUT_DIR, "compliance_summary.json")


def load_drift_report():
    assert os.path.exists(DRIFT_REPORT), f"drift report missing: {DRIFT_REPORT}"
    records = []
    with open(DRIFT_REPORT) as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    return records


def load_compliance():
    assert os.path.exists(COMPLIANCE_SUMMARY), f"compliance summary missing: {COMPLIANCE_SUMMARY}"
    with open(COMPLIANCE_SUMMARY) as f:
        return json.load(f)


# --- Drift Detection Tests ---

def test_nested_drift_granularity():
    """Drift in nested config fields must report the specific sub-key, not the parent dict."""
    records = load_drift_report()
    node_map = {r["node_id"]: r for r in records}

    web01 = node_map["web-prod-01"]
    drift_fields = [d["field"] for d in web01["drifts"]]

    # Should detect tls.cert_path specifically, not just "tls" or "config.tls"
    assert any("cert_path" in f for f in drift_fields), \
        f"web-prod-01 should report tls.cert_path drift, got: {drift_fields}"
    # Should NOT have the parent "tls" as a monolithic mismatch
    assert "tls" not in drift_fields and "config.tls" not in drift_fields, \
        f"web-prod-01 should not report parent 'tls' as whole-object drift, got: {drift_fields}"


def test_recursive_descent_depth():
    """Drift detection must recurse into all nested dict levels."""
    records = load_drift_report()
    node_map = {r["node_id"]: r for r in records}

    db01 = node_map["db-prod-01"]
    drift_fields = [d["field"] for d in db01["drifts"]]

    # Should detect replication.max_wal_senders specifically
    assert any("max_wal_senders" in f for f in drift_fields), \
        f"db-prod-01 should report replication.max_wal_senders drift, got: {drift_fields}"


def test_type_coercion_no_false_positives():
    """Numeric fields with string/int type differences must not be reported as drift."""
    records = load_drift_report()
    node_map = {r["node_id"]: r for r in records}

    # web-prod-01: manifest has listen_port="8080", live has 8080 (int)
    # These are semantically equivalent — should NOT appear as drift
    web01 = node_map["web-prod-01"]
    drift_fields = [d["field"] for d in web01["drifts"]]

    coerced_fields = ["listen_port", "max_connections", "timeout_seconds"]
    for field in coerced_fields:
        matching = [f for f in drift_fields if field in f and "config." + field != f]
        # Field should not appear as drift if values are numerically equal
        assert not any(field == f or field == f.split(".")[-1] for f in drift_fields
                      if f.endswith(field) and field in ["listen_port", "max_connections", "timeout_seconds"]), \
            f"web-prod-01: {field} should be coerced (string/int equivalent), got drifts: {drift_fields}"


def test_order_insensitive_no_false_drift():
    """Reordered lists in ignore_order_fields must not be flagged as drift."""
    records = load_drift_report()
    node_map = {r["node_id"]: r for r in records}

    # web-prod-01: dns_servers and tags are reordered but same content
    web01 = node_map["web-prod-01"]
    drift_fields = [d["field"] for d in web01["drifts"]]

    # dns_servers should NOT appear as drift (same elements, different order)
    assert not any("dns_servers" in f for f in drift_fields), \
        f"web-prod-01: dns_servers should be order-insensitive, got drifts: {drift_fields}"

    # tags should NOT appear as drift (same elements, different order)
    assert not any("tags" in f for f in drift_fields), \
        f"web-prod-01: tags should be order-insensitive, got drifts: {drift_fields}"


def test_real_drift_detected():
    """Actual configuration differences must be correctly identified."""
    records = load_drift_report()
    node_map = {r["node_id"]: r for r in records}

    # web-prod-02 has real drift: workers mismatch (8 vs 4), tls.min_version, logging changes
    web02 = node_map["web-prod-02"]
    assert web02["drift_count"] >= 3, \
        f"web-prod-02 should have at least 3 real drifts, got {web02['drift_count']}"

    # db-prod-02 has wal_level and replication drift
    db02 = node_map["db-prod-02"]
    drift_fields = [d["field"] for d in db02["drifts"]]
    assert any("wal_level" in f for f in drift_fields), \
        f"db-prod-02 should have wal_level drift, got: {drift_fields}"


def test_field_paths_no_prefix():
    """Drift field paths must use bare config paths without artificial prefixes."""
    records = load_drift_report()

    for record in records:
        for drift in record["drifts"]:
            field = drift["field"]
            assert not field.startswith("config."), \
                f"node {record['node_id']}: field '{field}' has 'config.' prefix — paths should be relative to config root"


# --- Compliance Tests ---

def test_decommissioned_excluded():
    """Nodes with status 'decommissioned' must not appear in compliance scoring."""
    data = load_compliance()
    node_ids = [s["node_id"] for s in data["compliance"]["node_scores"]]

    assert "legacy-app-01" not in node_ids, \
        "decommissioned node 'legacy-app-01' should be excluded from compliance"


def test_compliance_precision():
    """Compliance percentages must use float division, not integer truncation."""
    data = load_compliance()

    for score in data["compliance"]["node_scores"]:
        if score["total_fields"] > 0:
            expected = round((score["compliant_fields"] / score["total_fields"]) * 100, 2)
            assert score["compliance_pct"] == expected, \
                f"{score['node_id']}: compliance {score['compliance_pct']}% != expected {expected}%"


def test_compliance_node_count():
    """Only active nodes should be counted in compliance (no decommissioned)."""
    data = load_compliance()
    # 8 total nodes, 1 decommissioned → 7 in compliance
    assert data["compliance"]["total_nodes"] == 7, \
        f"expected 7 active nodes in compliance, got {data['compliance']['total_nodes']}"


# --- Report Integrity Tests ---

def test_report_sha256_integrity():
    """The compliance summary sha256 must match the actual drift report content."""
    data = load_compliance()
    report_sha = data["report_sha256"]

    with open(DRIFT_REPORT) as f:
        lines = [line.rstrip("\n") for line in f if line.strip()]

    computed = hashlib.sha256("\n".join(lines).encode()).hexdigest()
    assert report_sha == computed, \
        f"sha256 mismatch: summary says {report_sha}, computed {computed}"


def test_report_record_count():
    """The compliance summary record_count must match actual drift report lines."""
    data = load_compliance()
    with open(DRIFT_REPORT) as f:
        actual_count = sum(1 for line in f if line.strip())

    assert data["record_count"] == actual_count, \
        f"record_count mismatch: summary says {data['record_count']}, actual {actual_count}"


def test_remediation_action_count():
    """Total remediation actions in summary must match actual actions in drift report."""
    data = load_compliance()
    records = load_drift_report()

    actual_actions = sum(len(r.get("remediation", [])) for r in records)
    assert data["total_remediation_actions"] == actual_actions, \
        f"remediation count mismatch: summary says {data['total_remediation_actions']}, actual {actual_actions}"

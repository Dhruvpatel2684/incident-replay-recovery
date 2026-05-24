"""
Configuration Drift Reconciler — behavioral verification.
"""

import hashlib
import json
import os

import pytest

OUTPUT_DIR = "/app/runtime/output"
REPORT_PATH = os.path.join(OUTPUT_DIR, "drift_report.jsonl")
COMPLIANCE_PATH = os.path.join(OUTPUT_DIR, "compliance_summary.json")


def load_report():
    records = []
    with open(REPORT_PATH) as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    return records


def load_compliance():
    with open(COMPLIANCE_PATH) as f:
        return json.load(f)


def get_node(report, node_id):
    for r in report:
        if r["node_id"] == node_id:
            return r
    return None


# --- Nested type coercion ---

class TestTypeCoercion:
    def test_save_interval_not_false_positive(self):
        """Semantically equal numeric values in nested configs must not drift."""
        report = load_report()
        cache = get_node(report, "cache-prod-01")
        fields = [d["field"] for d in cache["drifts"]]
        assert not any("save_interval" in f for f in fields), \
            f"cache-prod-01 has unexpected drift entries: {fields}"

    def test_cache_drift_count(self):
        """cache-prod-01 should have exactly 1 real drift (aof_enabled)."""
        report = load_report()
        cache = get_node(report, "cache-prod-01")
        assert cache["drift_count"] == 1, \
            f"cache-prod-01 drift count incorrect: {cache['drift_count']}"

    def test_real_nested_drift_still_detected(self):
        """Actual different values in nested coerced fields must be caught."""
        report = load_report()
        worker = get_node(report, "worker-prod-01")
        fields = [d["field"] for d in worker["drifts"]]
        assert any("max_tasks_per_child" in f for f in fields), \
            f"worker-prod-01 missing expected drift: {fields}"

    def test_monitor_storage_drift(self):
        """monitor-prod-01 storage.max_disk_gb real diff must be detected."""
        report = load_report()
        monitor = get_node(report, "monitor-prod-01")
        fields = [d["field"] for d in monitor["drifts"]]
        assert any("max_disk_gb" in f for f in fields), \
            f"monitor-prod-01 missing storage drift: {fields}"


# --- Order-insensitive comparison ---

class TestOrderInsensitive:
    def test_dns_servers_no_false_drift(self):
        """Equivalent dns_servers with whitespace variance must not drift."""
        report = load_report()
        web01 = get_node(report, "web-prod-01")
        fields = [d["field"] for d in web01["drifts"]]
        assert not any("dns_servers" in f for f in fields), \
            f"web-prod-01 has false dns_servers drift: {fields}"

    def test_web01_drift_count(self):
        """web-prod-01 should have exactly 1 real drift (tls.cert_path)."""
        report = load_report()
        web01 = get_node(report, "web-prod-01")
        assert web01["drift_count"] == 1, \
            f"web-prod-01 drift count incorrect: {web01['drift_count']}"

    def test_tags_no_false_drift(self):
        """Tags in different order must not produce drift."""
        report = load_report()
        cache = get_node(report, "cache-prod-01")
        fields = [d["field"] for d in cache["drifts"]]
        assert not any("tags" in f for f in fields), \
            f"cache-prod-01 has false tags drift: {fields}"

    def test_ntp_no_false_drift(self):
        """NTP servers reordered must not produce drift."""
        report = load_report()
        db01 = get_node(report, "db-prod-01")
        fields = [d["field"] for d in db01["drifts"]]
        assert not any("ntp_servers" in f for f in fields), \
            f"db-prod-01 has false ntp_servers drift: {fields}"


# --- Node status and remediation ---

class TestNodeStatus:
    def test_db02_status_is_active(self):
        """db-prod-02 is declared active and should appear as active."""
        report = load_report()
        db02 = get_node(report, "db-prod-02")
        assert db02["status"] == "active", \
            f"db-prod-02 status incorrect: {db02['status']}"

    def test_active_nodes_get_remediation(self):
        """All active nodes with drift must have remediation plans."""
        report = load_report()
        for r in report:
            if r["status"] == "active" and r["drift_count"] > 0:
                assert len(r.get("remediation", [])) > 0, \
                    f"{r['node_id']} is active with drift but has no remediation"

    def test_decommissioned_excluded_compliance(self):
        """Decommissioned nodes must not appear in compliance."""
        data = load_compliance()
        ids = [s["node_id"] for s in data["compliance"]["node_scores"]]
        assert "legacy-app-01" not in ids, \
            "decommissioned node in compliance scores"


# --- Compliance accuracy ---

class TestCompliance:
    def test_overall_is_precise_float(self):
        """Overall compliance must be a precise float, not truncated integer."""
        data = load_compliance()
        overall = data["compliance"]["overall_compliance_pct"]
        assert isinstance(overall, float), \
            f"overall compliance should be float, got {type(overall).__name__}"
        assert overall != int(overall), \
            f"overall compliance {overall} appears truncated"

    def test_per_node_scores_valid(self):
        """Per-node compliance must be in valid range."""
        data = load_compliance()
        for s in data["compliance"]["node_scores"]:
            assert 0 <= s["compliance_pct"] <= 100

    def test_node_count_excludes_decommissioned(self):
        """Total nodes in compliance should exclude decommissioned."""
        data = load_compliance()
        assert data["compliance"]["total_nodes"] == 7, \
            f"expected 7 nodes, got {data['compliance']['total_nodes']}"


# --- Report integrity ---

class TestIntegrity:
    def test_sha256_matches_file(self):
        """SHA-256 in compliance must match the drift report file content."""
        data = load_compliance()
        stored = data["report_sha256"]
        with open(REPORT_PATH) as f:
            content = f.read()
        lines = [l for l in content.split("\n") if l.strip()]
        computed = hashlib.sha256("\n".join(lines).encode()).hexdigest()
        assert stored == computed, "integrity hash does not match report"

    def test_record_count(self):
        """Record count must match actual lines."""
        data = load_compliance()
        report = load_report()
        assert data["record_count"] == len(report), "record count mismatch"

    def test_total_remediation_count(self):
        """Remediation action count must match actual actions in report."""
        data = load_compliance()
        report = load_report()
        actual = sum(len(r.get("remediation", [])) for r in report)
        assert data["total_remediation_actions"] == actual, \
            "remediation count mismatch"

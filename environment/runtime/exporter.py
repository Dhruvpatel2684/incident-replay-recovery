"""
Exports drift reports and compliance summaries to output files.
"""

import hashlib
import json
import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger("drift.exporter")


def export_report(drift_results, remediation_plans, compliance_summary, config):
    """Write drift report and compliance summary to output directory."""
    output_path = config.get("output", "output_path", fallback="/app/runtime/output")
    snapshot_filename = config.get("output", "snapshot_filename", fallback="drift_report.jsonl")
    compliance_filename = config.get("output", "compliance_filename", fallback="compliance_summary.json")

    os.makedirs(output_path, exist_ok=True)

    # Write drift report as JSONL
    report_path = os.path.join(output_path, snapshot_filename)
    lines = []
    for node_result in drift_results:
        plan = next((p for p in remediation_plans if p["node_id"] == node_result["node_id"]), None)
        record = {
            "node_id": node_result["node_id"],
            "status": node_result.get("status", "unknown"),
            "region": node_result.get("region", "unknown"),
            "drift_count": node_result["drift_count"],
            "drifts": node_result["drifts"],
            "remediation": plan["actions"] if plan else []
        }
        lines.append(json.dumps(record, sort_keys=True, separators=(",", ":")))

    with open(report_path, "w") as f:
        f.write("\n".join(lines) + "\n")

    # Compute integrity hash
    content_hash = hashlib.sha256("\n".join(lines).encode()).hexdigest()

    # Write compliance summary
    summary_path = os.path.join(output_path, compliance_filename)
    summary = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        "report_sha256": content_hash,
        "record_count": len(lines),
        "nodes_with_drift": sum(1 for r in drift_results if r["drift_count"] > 0),
        "total_drift_entries": sum(r["drift_count"] for r in drift_results),
        "total_remediation_actions": sum(p["action_count"] for p in remediation_plans),
        "compliance": compliance_summary
    }

    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2, sort_keys=True)

    logger.info(f"drift report: {report_path} ({len(lines)} records)")
    logger.info(f"compliance summary: {summary_path}")
    logger.info(f"report integrity: {content_hash}")

    return report_path, summary_path

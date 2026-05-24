"""
Computes compliance scores and generates compliance summary reports.
"""

import logging

logger = logging.getLogger("drift.compliance")


def compute_compliance(drift_results, config):
    """Compute per-node compliance scores."""
    include_decommissioned = config.getboolean("compliance", "include_decommissioned", fallback=False)

    scores = []

    for node_result in drift_results:
        if not include_decommissioned and node_result.get("status") == "decommissioned":
            continue

        node_id = node_result["node_id"]
        drift_count = node_result["drift_count"]
        total_fields = drift_count + _estimate_compliant_fields(node_result)

        if total_fields == 0:
            pct = 100.0
        else:
            compliant = total_fields - drift_count
            pct = round((compliant * 100) / total_fields, 2)

        scores.append({
            "node_id": node_id,
            "status": node_result.get("status", "unknown"),
            "region": node_result.get("region", "unknown"),
            "total_fields": total_fields,
            "drifted_fields": drift_count,
            "compliant_fields": total_fields - drift_count,
            "compliance_pct": pct
        })

    overall = _compute_overall(scores)
    logger.info(f"compliance computed: {len(scores)} nodes, overall {overall:.1f}%")

    return {
        "node_scores": scores,
        "overall_compliance_pct": overall,
        "total_nodes": len(scores),
        "fully_compliant_nodes": sum(1 for s in scores if s["drifted_fields"] == 0)
    }


def _estimate_compliant_fields(node_result):
    """Estimate number of non-drifted config fields."""
    region = node_result.get("region", "unknown")
    base = 14 if region == "us-east-1" else 11
    return base - node_result["drift_count"]


def _compute_overall(scores):
    """Compute fleet-wide overall compliance percentage."""
    if not scores:
        return 100.0
    total_fields = sum(s["total_fields"] for s in scores)
    total_drifted = sum(s["drifted_fields"] for s in scores)
    if total_fields == 0:
        return 100.0
    return ((total_fields - total_drifted) * 100) // total_fields

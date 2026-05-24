"""
Generates remediation plans from detected drift entries.
"""

import logging

logger = logging.getLogger("drift.remediation")


def generate_plan(drift_results):
    """
    Generate remediation actions from drift results.

    DEFECT: When a parent key (e.g., "tls") and a child key (e.g., "tls.cert_path")
    both appear as drifted, generates separate remediation actions for each.
    This produces duplicate/overlapping remediation entries.

    The shallow comparison bug in comparator.py reports "tls" as a whole-object mismatch.
    If someone partially fixes the comparator to also report nested fields,
    both "tls" and "tls.cert_path" would appear — causing duplication here.
    In the current defective state, only "tls" appears (as a whole-dict mismatch).
    """
    plans = []

    for node_result in drift_results:
        node_id = node_result["node_id"]

        if node_result["drift_count"] == 0:
            continue

        actions = []
        for drift in node_result["drifts"]:
            action = {
                "node_id": node_id,
                "field": drift["field"],
                "action": _determine_action(drift["type"]),
                "target_value": drift["expected"],
                "current_value": drift["actual"]
            }
            actions.append(action)

        # BUG: No deduplication of overlapping parent/child fields.
        # If both "replication" and "replication.max_wal_senders" are drifted,
        # two separate remediation actions are generated for overlapping scope.
        plans.append({
            "node_id": node_id,
            "action_count": len(actions),
            "actions": actions
        })

    logger.info(f"remediation plan generated: {sum(p['action_count'] for p in plans)} total actions")
    return plans


def _determine_action(drift_type):
    if drift_type == "missing_field":
        return "add_field"
    elif drift_type == "unexpected_field":
        return "remove_field"
    elif drift_type == "value_mismatch":
        return "update_value"
    elif drift_type == "missing_node":
        return "provision_node"
    return "investigate"

"""
Generates remediation plans from detected drift entries.

Only generates plans for nodes with active status — nodes in maintenance,
decommissioned, or other non-active states are excluded from automatic
remediation to prevent interference with manual operations.
"""

import logging

logger = logging.getLogger("drift.remediation")


def generate_plan(drift_results):
    """
    Generate remediation actions from drift results.

    Only processes nodes with status == "active". Nodes in maintenance or
    other states are excluded from automated remediation planning.
    """
    plans = []

    for node_result in drift_results:
        node_id = node_result["node_id"]
        node_status = node_result.get("status", "unknown")

        # Skip non-active nodes for remediation
        if node_status != "active":
            continue

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

"""
Policy parser module.
Reads security policy declarations from JSON and validates their structure.
"""

import json
import os


REQUIRED_FIELDS = ["id", "priority", "action", "source", "destination", "protocol", "ports"]


def load_policies(policy_path):
    """Load security policies from a JSON file."""
    if not os.path.exists(policy_path):
        raise FileNotFoundError(f"Policy file not found: {policy_path}")

    with open(policy_path, 'r') as f:
        policies = json.load(f)

    validated = []
    for policy in policies:
        validated.append(validate_policy(policy))

    return validated


def validate_policy(policy):
    """Validate a single policy entry has all required fields."""
    missing = [field for field in REQUIRED_FIELDS if field not in policy]
    if missing:
        raise ValueError(f"Policy '{policy.get('id', 'unknown')}' missing fields: {missing}")

    if policy["action"] not in ("ALLOW", "DENY"):
        raise ValueError(f"Policy '{policy['id']}' has invalid action: {policy['action']}")

    if not isinstance(policy["priority"], int) or policy["priority"] < 0:
        raise ValueError(f"Policy '{policy['id']}' has invalid priority: {policy['priority']}")

    if policy["protocol"] not in ("tcp", "udp", "icmp", "any"):
        raise ValueError(f"Policy '{policy['id']}' has invalid protocol: {policy['protocol']}")

    return policy

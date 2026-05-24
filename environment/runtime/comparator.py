"""
Compares manifest declarations against live node state to detect configuration drift.

Implements recursive descent comparison with type coercion and order-insensitive
list handling based on reconciler.ini configuration.
"""

import configparser
import json
import logging
import os

logger = logging.getLogger("drift.comparator")

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config", "reconciler.ini")


def load_config():
    config = configparser.ConfigParser()
    config.read(CONFIG_PATH)
    return config


def get_ignore_order_fields(config):
    raw = config.get("drift", "ignore_order_fields", fallback="")
    return [f.strip() for f in raw.split(",") if f.strip()]


def get_type_coerce_fields(config):
    raw = config.get("drift", "type_coerce_fields", fallback="")
    return [f.strip() for f in raw.split(",") if f.strip()]


def _compare_values(manifest_val, live_val, field_name, coerce_enabled, ignore_order_fields):
    """
    Compare two values with type coercion and order-insensitive list support.
    """
    if coerce_enabled:
        try:
            return str(manifest_val).strip() == str(live_val).strip()
        except (TypeError, ValueError):
            pass

    if field_name in ignore_order_fields:
        if isinstance(manifest_val, list) and isinstance(live_val, list):
            if len(manifest_val) != len(live_val):
                return False
            return json.dumps(sorted(manifest_val)) == json.dumps(sorted(live_val))

    return manifest_val == live_val


def compare_configs(manifest_config, live_config, coerce_fields, ignore_order_fields, path_prefix=""):
    """
    Recursively compare manifest config dict against live config dict.
    """
    drifts = []
    all_keys = set(list(manifest_config.keys()) + list(live_config.keys()))

    for key in sorted(all_keys):
        full_path = f"{path_prefix}.{key}" if path_prefix else key
        manifest_val = manifest_config.get(key)
        live_val = live_config.get(key)

        if key not in manifest_config:
            drifts.append({"field": full_path, "type": "unexpected_field", "expected": None, "actual": live_val})
            continue
        if key not in live_config:
            drifts.append({"field": full_path, "type": "missing_field", "expected": manifest_val, "actual": None})
            continue

        if isinstance(manifest_val, dict) and isinstance(live_val, dict):
            parent_coerce = key in coerce_fields
            child_drifts = _compare_nested(manifest_val, live_val, coerce_fields, ignore_order_fields, full_path, parent_coerce)
            drifts.extend(child_drifts)
            continue

        coerce_enabled = key in coerce_fields
        if not _compare_values(manifest_val, live_val, key, coerce_enabled, ignore_order_fields):
            drifts.append({"field": full_path, "type": "value_mismatch", "expected": manifest_val, "actual": live_val})

    return drifts


def _compare_nested(manifest_dict, live_dict, coerce_fields, ignore_order_fields, path_prefix, parent_coerce):
    """
    Compare nested dictionary structures.
    """
    drifts = []
    all_keys = set(list(manifest_dict.keys()) + list(live_dict.keys()))

    for key in sorted(all_keys):
        full_path = f"{path_prefix}.{key}"
        manifest_val = manifest_dict.get(key)
        live_val = live_dict.get(key)

        if key not in manifest_dict:
            drifts.append({"field": full_path, "type": "unexpected_field", "expected": None, "actual": live_val})
            continue
        if key not in live_dict:
            drifts.append({"field": full_path, "type": "missing_field", "expected": manifest_val, "actual": None})
            continue

        if isinstance(manifest_val, dict) and isinstance(live_val, dict):
            nested_drifts = _compare_nested(manifest_val, live_val, coerce_fields, ignore_order_fields, full_path, parent_coerce)
            drifts.extend(nested_drifts)
            continue

        coerce_enabled = parent_coerce
        if not _compare_values(manifest_val, live_val, key, coerce_enabled, ignore_order_fields):
            drifts.append({"field": full_path, "type": "value_mismatch", "expected": manifest_val, "actual": live_val})

    return drifts


def detect_drift(manifest_nodes, live_nodes, config):
    """Run drift detection across all nodes."""
    coerce_fields = get_type_coerce_fields(config)
    ignore_order_fields = get_ignore_order_fields(config)

    live_map = {n["node_id"]: n for n in live_nodes}
    results = []

    for manifest_node in manifest_nodes:
        node_id = manifest_node["node_id"]
        live_node = live_map.get(node_id)

        if not live_node:
            results.append({"node_id": node_id, "status": manifest_node.get("status", "unknown"), "region": manifest_node.get("region", "unknown"), "drift_count": 1, "drifts": [{"field": "_node", "type": "missing_node", "expected": "present", "actual": None}]})
            continue

        manifest_config = manifest_node.get("config", {})
        live_config = live_node.get("config", {})
        drifts = compare_configs(manifest_config, live_config, coerce_fields, ignore_order_fields, path_prefix="config")

        results.append({
            "node_id": node_id,
            "status": live_node.get("status", "unknown"),
            "region": manifest_node.get("region", "unknown"),
            "drift_count": len(drifts),
            "drifts": drifts
        })

    logger.info(f"drift detection complete: {len(results)} nodes analyzed")
    return results

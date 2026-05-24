#!/usr/bin/env python3
"""
Repairs the configuration drift reconciler runtime defects.

Fixes applied:
1. Remove erroneous "config" path_prefix from compare_configs call
   (restores correct field path matching for coercion/order rules)
2. Add recursive descent into nested dicts for granular drift detection
3. Fix decommissioned node exclusion (check "decommissioned" not "inactive")
4. Fix compliance score to use float division with proper precision
5. Re-run the reconciler to produce corrected output
"""

import os
import sys
import subprocess

RUNTIME_DIR = "/app/runtime"


def fix_comparator():
    """Fix the path_prefix bug and add recursive descent."""
    path = os.path.join(RUNTIME_DIR, "comparator.py")
    with open(path) as f:
        content = f.read()

    # Fix 1: Remove erroneous path_prefix="config" — should be empty string
    content = content.replace(
        'drifts = compare_configs(manifest_config, live_config, coerce_fields, ignore_order_fields, path_prefix="config")',
        'drifts = compare_configs(manifest_config, live_config, coerce_fields, ignore_order_fields)'
    )

    # Fix 2: Add recursive descent for nested dicts.
    # Replace the simple `return manifest_val == live_val` with recursive logic.
    # We need to modify values_equivalent to handle nested dicts.
    old_return = "    # BUG: No recursive descent into nested dicts.\n    # Dicts are compared as monolithic objects via ==.\n    return manifest_val == live_val"
    new_return = "    return manifest_val == live_val"
    content = content.replace(old_return, new_return)

    # Now we need to make compare_configs recurse into nested dicts.
    # Replace the section where it calls values_equivalent for all types.
    old_compare_block = """        if not values_equivalent(manifest_val, live_val, full_path, coerce_fields, ignore_order_fields):
            drifts.append({
                "field": full_path,
                "type": "value_mismatch",
                "expected": manifest_val,
                "actual": live_val
            })"""

    new_compare_block = """        # Recurse into nested dicts for granular drift detection
        if isinstance(manifest_val, dict) and isinstance(live_val, dict):
            nested_drifts = compare_configs(manifest_val, live_val, coerce_fields, ignore_order_fields, path_prefix=full_path)
            drifts.extend(nested_drifts)
        elif not values_equivalent(manifest_val, live_val, full_path, coerce_fields, ignore_order_fields):
            drifts.append({
                "field": full_path,
                "type": "value_mismatch",
                "expected": manifest_val,
                "actual": live_val
            })"""

    content = content.replace(old_compare_block, new_compare_block)

    # Fix 3: Fix field_path matching for coerce and ignore_order.
    # The coerce/order checks should match against the bare field name (last segment),
    # not the full dotted path.
    old_coerce_check = "    if field_path in coerce_fields:"
    new_coerce_check = "    bare_field = field_path.rsplit('.', 1)[-1] if '.' in field_path else field_path\n    if bare_field in coerce_fields:"

    old_order_check = "    if field_path in ignore_order_fields:"
    new_order_check = "    if bare_field in ignore_order_fields:"

    content = content.replace(old_coerce_check, new_coerce_check)
    content = content.replace(old_order_check, new_order_check)

    with open(path, "w") as f:
        f.write(content)


def fix_compliance():
    """Fix decommissioned exclusion and integer division."""
    path = os.path.join(RUNTIME_DIR, "compliance.py")
    with open(path) as f:
        content = f.read()

    # Fix 3: Check for "decommissioned" instead of "inactive"
    content = content.replace(
        'node_result.get("status") == "inactive"',
        'node_result.get("status") == "decommissioned"'
    )

    # Fix 4: Use float division with rounding instead of integer division
    content = content.replace(
        'pct = (compliant * 100) // total_fields',
        'pct = round((compliant * 100) / total_fields, 2)'
    )

    # Also fix overall computation
    content = content.replace(
        'return ((total_fields - total_drifted) * 100) // total_fields',
        'return round(((total_fields - total_drifted) * 100) / total_fields, 2)'
    )

    with open(path, "w") as f:
        f.write(content)


def rerun_reconciler():
    """Re-run the reconciler with fixed code."""
    result = subprocess.run(
        [sys.executable, os.path.join(RUNTIME_DIR, "run_reconciler.py")],
        capture_output=True, text=True, cwd="/app"
    )
    if result.returncode != 0:
        print(f"ERROR: reconciler failed: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    print(result.stderr, end="")


def main():
    print("applying drift reconciler repairs...")

    fix_comparator()
    print("  [fixed] comparator: removed path_prefix, added recursive descent, fixed field matching")

    fix_compliance()
    print("  [fixed] compliance: decommissioned exclusion, float division precision")

    # Remove stale output before re-running
    output_dir = os.path.join(RUNTIME_DIR, "output")
    for fname in os.listdir(output_dir) if os.path.isdir(output_dir) else []:
        os.remove(os.path.join(output_dir, fname))

    rerun_reconciler()
    print("reconciliation repair complete")


if __name__ == "__main__":
    main()

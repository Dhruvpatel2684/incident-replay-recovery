#!/usr/bin/env python3
"""
Repairs configuration drift reconciler runtime defects.
"""

import os
import sys
import subprocess

RUNTIME_DIR = "/app/runtime"


def fix_comparator():
    """Fix coercion propagation, order comparison, and status attribution."""
    path = os.path.join(RUNTIME_DIR, "comparator.py")
    with open(path) as f:
        content = f.read()

    # Fix 1: In _compare_nested, coercion must check leaf key against coerce_fields
    content = content.replace(
        "coerce_enabled = parent_coerce",
        "coerce_enabled = parent_coerce or (key in coerce_fields)"
    )

    # Fix 2: Order-insensitive comparison should strip whitespace and compare directly
    content = content.replace(
        "return json.dumps(sorted(manifest_val)) == json.dumps(sorted(live_val))",
        "return sorted(str(x).strip() for x in manifest_val) == sorted(str(x).strip() for x in live_val)"
    )

    # Fix 3: Status should come from manifest_node, not live_node
    content = content.replace(
        '"status": live_node.get("status", "unknown"),',
        '"status": manifest_node.get("status", "unknown"),'
    )

    with open(path, "w") as f:
        f.write(content)


def fix_compliance():
    """Fix integer division in overall compliance."""
    path = os.path.join(RUNTIME_DIR, "compliance.py")
    with open(path) as f:
        content = f.read()

    content = content.replace(
        "return ((total_fields - total_drifted) * 100) // total_fields",
        "return round(((total_fields - total_drifted) * 100) / total_fields, 2)"
    )

    with open(path, "w") as f:
        f.write(content)


def fix_exporter():
    """Fix drift totals to exclude decommissioned nodes."""
    path = os.path.join(RUNTIME_DIR, "exporter.py")
    with open(path) as f:
        content = f.read()

    # Fix 5: total_drift_entries and nodes_with_drift should exclude decommissioned
    content = content.replace(
        '"nodes_with_drift": sum(1 for r in drift_results if r["drift_count"] > 0),',
        '"nodes_with_drift": sum(1 for r in drift_results if r["drift_count"] > 0 and r.get("status") != "decommissioned"),'
    )
    content = content.replace(
        '"total_drift_entries": sum(r["drift_count"] for r in drift_results),',
        '"total_drift_entries": sum(r["drift_count"] for r in drift_results if r.get("status") != "decommissioned"),'
    )

    with open(path, "w") as f:
        f.write(content)


def rerun():
    """Re-run reconciler with fixed code."""
    result = subprocess.run(
        [sys.executable, os.path.join(RUNTIME_DIR, "run_reconciler.py")],
        capture_output=True, text=True, cwd="/app"
    )
    if result.returncode != 0:
        print(f"ERROR: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    print(result.stderr, end="")


def main():
    print("applying reconciler repairs...")
    fix_comparator()
    print("  [fixed] comparator: coercion propagation, order comparison, status source")
    fix_compliance()
    print("  [fixed] compliance: float division for overall score")
    fix_exporter()
    print("  [fixed] exporter: drift totals exclude decommissioned nodes")

    # Clear stale output
    output_dir = os.path.join(RUNTIME_DIR, "output")
    for f in os.listdir(output_dir) if os.path.isdir(output_dir) else []:
        fpath = os.path.join(output_dir, f)
        if os.path.isfile(fpath):
            os.remove(fpath)

    rerun()
    print("repair complete")


if __name__ == "__main__":
    main()

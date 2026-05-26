"""
Output writer module for the build orchestrator.

Writes the execution plan to a JSON file.
"""

import json
import os


def write_plan(plan, output_dir="/app/runtime/output"):
    """
    Write the build plan to the output directory.

    Args:
        plan: dict containing the complete execution plan
        output_dir: directory to write the output file
    """
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "build_plan.json")

    with open(output_path, "w") as f:
        json.dump(plan, f, indent=2)

    return output_path

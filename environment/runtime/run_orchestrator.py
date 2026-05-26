"""
Build Orchestrator - Entry Point

Reads build targets, analyzes the dependency graph, and produces
an execution plan with parallelism and scheduling information.
"""

import json
import os
import sys

# Ensure the runtime package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from runtime.graph_analyzer import GraphAnalyzer
from runtime.plan_builder import PlanBuilder
from runtime.output_writer import write_plan


def main():
    """Run the build orchestrator pipeline."""
    # Load build targets
    targets_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "build_targets.json")
    with open(targets_path, "r") as f:
        targets = json.load(f)

    print(f"[orchestrator] Loaded {len(targets)} build targets")

    # Analyze the dependency graph
    analyzer = GraphAnalyzer(targets)
    print("[orchestrator] Graph analysis complete")

    # Build the execution plan
    builder = PlanBuilder(analyzer)
    plan = builder.build_plan()
    print(f"[orchestrator] Plan built: {plan['analysis']['total_stages']} stages, "
          f"makespan {plan['analysis']['makespan_ms']}ms")

    # Write output
    output_path = write_plan(plan)
    print(f"[orchestrator] Plan written to {output_path}")

    return plan


if __name__ == "__main__":
    main()

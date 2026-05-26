"""
Build plan construction module.

Uses the GraphAnalyzer results to construct a complete execution plan
with scheduling information, parallelism details, and timing estimates.
"""

import hashlib
import json


class PlanBuilder:
    """Constructs an execution plan from graph analysis results."""

    def __init__(self, analyzer):
        """
        Initialize the plan builder.

        Args:
            analyzer: A GraphAnalyzer instance with completed analysis
        """
        self.analyzer = analyzer

    def build_plan(self):
        """
        Build the complete execution plan.

        Returns:
            dict with the full execution plan
        """
        priorities = self.analyzer.compute_all_priorities()
        parallel_set = self.analyzer.find_parallel_set()
        critical_path = self.analyzer.find_critical_path()
        independent_pairs = self.analyzer.get_independent_pairs()
        stages = self.analyzer.compute_execution_stages()

        # Build target details
        target_details = []
        for tid in sorted(self.analyzer.target_ids):
            t = self.analyzer.targets[tid]
            target_details.append({
                "id": tid,
                "name": t["name"],
                "estimated_duration_ms": t["estimated_duration_ms"],
                "dependencies": t["dependencies"],
                "priority": priorities[tid],
                "in_parallel_set": tid in parallel_set,
                "on_critical_path": tid in critical_path
            })

        # Compute makespan (total time with parallelism)
        makespan_ms = 0
        for stage in stages:
            stage_duration = max(
                self.analyzer.targets[tid]["estimated_duration_ms"]
                for tid in stage
            )
            makespan_ms += stage_duration

        # Compute serial time (no parallelism)
        serial_time_ms = sum(
            t["estimated_duration_ms"] for t in self.analyzer.targets.values()
        )

        # Build the plan
        plan = {
            "plan_version": "1.0",
            "total_targets": len(self.analyzer.target_ids),
            "targets": target_details,
            "analysis": {
                "independent_pair_count": len(independent_pairs),
                "critical_path": critical_path,
                "critical_path_length_ms": sum(
                    self.analyzer.targets[tid]["estimated_duration_ms"]
                    for tid in critical_path
                ),
                "parallel_set": sorted(parallel_set),
                "parallel_set_size": len(parallel_set),
                "execution_stages": stages,
                "total_stages": len(stages),
                "makespan_ms": makespan_ms,
                "serial_time_ms": serial_time_ms,
                "speedup_factor": round(serial_time_ms / makespan_ms, 2) if makespan_ms > 0 else 1.0
            },
            "priorities": priorities
        }

        # Compute fingerprint for integrity verification
        plan["fingerprint"] = self._compute_fingerprint(plan)

        return plan

    def _compute_fingerprint(self, plan):
        """
        Compute a SHA-256 fingerprint of the plan content.

        This covers the analysis results to detect any changes.
        """
        # Create a deterministic representation of key plan data
        fingerprint_data = {
            "independent_pair_count": plan["analysis"]["independent_pair_count"],
            "critical_path": plan["analysis"]["critical_path"],
            "parallel_set": plan["analysis"]["parallel_set"],
            "priorities": plan["priorities"],
            "total_stages": plan["analysis"]["total_stages"],
            "makespan_ms": plan["analysis"]["makespan_ms"]
        }
        raw = json.dumps(fingerprint_data, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()

"""
Main entry point for the flow control simulation system.
"""
import json
import os
import glob

from runtime.protocols.flow_sim import FlowSimulation


DATA_DIR = "/app/runtime/data"
OUTPUT_DIR = "/app/runtime/output"


def main():
    """Run all simulation scenarios."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    trace_files = sorted(glob.glob(os.path.join(DATA_DIR, "trace_scenario_*.json")))
    results = []

    for path in trace_files:
        with open(path, "r") as f:
            trace = json.load(f)
        sim = FlowSimulation(trace)
        summary = sim.run()
        summary["scenario_id"] = trace["scenario_id"]
        results.append(summary)

    total_sent = sum(r["segments_sent"] for r in results)
    total_blocked = sum(r["segments_blocked"] for r in results)
    total_retx = sum(r["retransmissions"] for r in results)

    aggregate = {
        "scenarios_run": len(results),
        "total_segments_sent": total_sent,
        "total_segments_blocked": total_blocked,
        "total_retransmissions": total_retx,
        "efficiency": round(total_sent / max(1, total_sent + total_blocked), 4),
    }

    with open(os.path.join(OUTPUT_DIR, "scenario_results.json"), "w") as f:
        json.dump(results, f, indent=2)

    with open(os.path.join(OUTPUT_DIR, "flow_summary.json"), "w") as f:
        json.dump(aggregate, f, indent=2)


if __name__ == "__main__":
    main()

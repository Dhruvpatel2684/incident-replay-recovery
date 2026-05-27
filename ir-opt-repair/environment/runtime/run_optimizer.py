"""
Main entry point for the IR optimizer.

Runs the optimization sequence:
1. Load IR program from specification
2. Run constant folding pass
3. Compute dominance information
4. Run dead code elimination
5. Compute register pressure
6. Generate optimization report
"""
import json
import os
import glob

from runtime.ir.builder import load_program
from runtime.passes.constant_fold import run_constant_fold
from runtime.passes.dce import run_dce
from runtime.analysis.dominance import compute_dominators, compute_idom
from runtime.codegen.register_alloc import compute_register_pressure


DATA_DIR = "/app/runtime/data"
OUTPUT_DIR = "/app/runtime/output"


def optimize_program(program_path):
    """Run full optimization on a single program."""
    program = load_program(program_path)
    total_instructions = len(program.get_all_instructions())

    # Pass 1: Constant folding
    folded = run_constant_fold(program)

    # Analysis: Compute dominance
    dom_sets = compute_dominators(program)
    idom = compute_idom(program, dom_sets)

    # Pass 2: Dead code elimination
    eliminated = run_dce(program)

    # Analysis: Register pressure
    reg_pressure = compute_register_pressure(program)

    live_count = program.count_live_instructions()

    return {
        "total_instructions": total_instructions,
        "live_instructions": live_count,
        "eliminated_instructions": eliminated,
        "folded_instructions": folded,
        "register_pressure": reg_pressure,
        "dominance_tree_size": len(idom),
        "block_count": len(program.blocks),
    }


def main():
    """Run optimizer on all programs in data directory."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    program_files = sorted(glob.glob(os.path.join(DATA_DIR, "program_*.json")))
    results = []

    for pf in program_files:
        result = optimize_program(pf)
        result["source_file"] = os.path.basename(pf)
        results.append(result)

    total_original = sum(r["total_instructions"] for r in results)
    total_live = sum(r["live_instructions"] for r in results)
    total_eliminated = sum(r["eliminated_instructions"] for r in results)
    total_folded = sum(r["folded_instructions"] for r in results)
    max_pressure = max(r["register_pressure"]["max_pressure"] for r in results)
    total_spills = sum(r["register_pressure"]["spill_points"] for r in results)

    summary = {
        "programs_optimized": len(results),
        "total_original_instructions": total_original,
        "total_live_instructions": total_live,
        "total_eliminated": total_eliminated,
        "total_folded": total_folded,
        "reduction_ratio": round(1.0 - total_live / max(1, total_original), 4),
        "max_register_pressure": max_pressure,
        "total_spill_points": total_spills,
    }

    with open(os.path.join(OUTPUT_DIR, "opt_results.json"), "w") as f:
        json.dump(results, f, indent=2)

    with open(os.path.join(OUTPUT_DIR, "opt_summary.json"), "w") as f:
        json.dump(summary, f, indent=2)


if __name__ == "__main__":
    main()

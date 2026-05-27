# IR Optimizer Repair — Debugging Task

## Overview

A compiler intermediate representation (IR) optimizer processes programs through multiple optimization passes including constant folding, dead code elimination, and register allocation analysis. The system operates on SSA-form programs with basic blocks connected by control flow edges.

## System Environment

- **Language**: Python 3.11
- **Runtime**: `/app/runtime/` (source, config, data, output)
- **Global system-wide tooling**: `uv` and `pytest` are available
- **Entry point**: `python3 -m runtime.run_optimizer`

## Architecture

The optimizer is organized into multiple packages:

- `/app/runtime/ir/` — IR representation (programs, blocks, instructions)
- `/app/runtime/passes/` — Optimization passes (constant folding, DCE)
- `/app/runtime/analysis/` — Program analysis (liveness, dominance)
- `/app/runtime/codegen/` — Code generation analysis (register allocation)

## Observed Symptoms

The optimizer produces incorrect results:

- Far too many instructions are eliminated as "dead code" (reduction ratio ~67% when it should be ~21%)
- Register pressure is unrealistically low (max 2) because most instructions were incorrectly removed
- No spill points are detected even when many registers should be simultaneously live
- Programs with cross-block register uses have those values incorrectly eliminated

## Expected Behavior

When operating correctly:

- Total live instructions across 3 programs: 45 (out of 57 original)
- Eliminated instructions: 12 (only truly dead local values)
- Max register pressure: 8 (program_gamma has a long live chain)
- Spill points detected: >= 2 (pressure reaches physical register limit)
- Reduction ratio: approximately 0.21

## Output Schema

### `/app/runtime/output/opt_summary.json`

| Field | Type | Description |
|-------|------|-------------|
| `programs_optimized` | integer | Number of programs processed |
| `total_original_instructions` | integer | Total instructions before optimization |
| `total_live_instructions` | integer | Instructions remaining after optimization |
| `total_eliminated` | integer | Instructions marked dead |
| `total_folded` | integer | Instructions constant-folded |
| `reduction_ratio` | float | Fraction of instructions eliminated |
| `max_register_pressure` | integer | Highest simultaneous live registers |
| `total_spill_points` | integer | Points where spill is needed |

### `/app/runtime/output/opt_results.json`

Array of per-program results with instruction counts and register pressure details.

## Key Files

| File | Purpose |
|------|---------|
| `/app/runtime/run_optimizer.py` | Entry point, runs all passes |
| `/app/runtime/ir/program.py` | IR program and basic block representation |
| `/app/runtime/ir/instructions.py` | IR instruction model |
| `/app/runtime/ir/builder.py` | Loads programs from JSON |
| `/app/runtime/passes/constant_fold.py` | Constant folding pass |
| `/app/runtime/passes/dce.py` | Dead code elimination pass |
| `/app/runtime/analysis/liveness.py` | Register liveness analysis |
| `/app/runtime/analysis/dominance.py` | Dominator tree computation |
| `/app/runtime/codegen/register_alloc.py` | Register pressure analysis |
| `/app/runtime/data/program_alpha.json` | Test program with loop |
| `/app/runtime/data/program_beta.json` | Test program with diamond CFG |
| `/app/runtime/data/program_gamma.json` | Test program with long chain |

## Your Task

Identify and fix the defects causing over-elimination and incorrect metrics. The bugs span multiple analysis and optimization modules and interact through shared program state.

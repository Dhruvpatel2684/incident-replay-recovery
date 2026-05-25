# SSA Register Allocation Repair — Debugging Task

## Overview

A compiler backend register allocation system processes intermediate representation (IR) from multiple compilation units, resolves SSA phi-nodes, schedules instructions by dominance order, analyzes register pressure, and assigns physical registers. The system currently produces incorrect allocation maps and scheduling output due to several interacting defects.

## System Environment

- **Language**: Python 3.11
- **Runtime**: `/app/runtime/` (source, config, data, output)
- **Global system-wide tooling**: `uv` and `pytest` are available
- **Configuration**: `/app/runtime/config/allocator.ini`
- **Data**: `/app/runtime/data/` (three compilation unit JSON files)
- **Output**: `/app/runtime/output/` (allocation_map.json, schedule.json)

## Processing Stages

1. **IR Loading** — Reads instruction streams from three compilation unit files (`unit_alpha.json`, `unit_beta.json`, `unit_gamma.json`). Each unit contains basic blocks with typed instructions.

2. **Phi Resolution** — Resolves SSA phi-node instructions into parallel copies. Phi nodes appear at merge points and select values based on predecessor control flow. Uses settings from the `allocator.constraints` configuration section for coalescing decisions.

3. **Scheduling** — Orders all instructions into a deterministic execution sequence. The correct ordering is: primary sort by `block_id`, secondary by `unit_id` (to separate same-named blocks from different units), then by `position` within the block.

4. **Pressure Analysis** — Computes register pressure per register class across all blocks. At each program point, the pressure reflects only that block's local contribution (each block's pressure value replaces, not accumulates with, previous blocks).

5. **Register Allocation** — Assigns physical registers from per-class pools. When pressure for a class exceeds the spill threshold (defined in the constraints section), allocations spill to stack. Register classes must be recognized via the configuration to receive physical register assignments.

## Problem

The system runs without crashing but produces incorrect outputs:
- Some register classes that should receive physical register assignments are instead being spilled to stack unconditionally
- The spill threshold appears miscalibrated, causing excessive spilling
- The instruction schedule is non-deterministic across runs
- Register pressure values seem inflated beyond what the IR should produce

## Expected Correct Output

When operating correctly, the system should:
- Recognize all four register classes (`gpr`, `fpr`, `vec`, `simd`) and allocate physical registers for each
- Use a spill threshold of 4 (from the constraints section) to determine when pressure warrants spilling
- Produce a deterministic instruction schedule ordered by (block_id, unit_id, position)
- Compute pressure per class that reflects each block's contribution independently (not accumulated across blocks)

## Output Schema

### `/app/runtime/output/allocation_map.json`

| Field | Type | Description |
|-------|------|-------------|
| `allocations` | object | Map of virtual register name to allocation entry |
| `allocations.<vreg>.type` | string | Either "register" or "spill" |
| `allocations.<vreg>.location` | string | Physical register name (e.g., "gpr0") or stack slot (e.g., "stack_0") |
| `allocations.<vreg>.register_class` | string | The class this register belongs to (gpr, fpr, vec, simd) |
| `phi_resolutions` | array | List of resolved phi-node entries |
| `phi_resolutions[].dest` | string | Destination virtual register |
| `phi_resolutions[].sources` | array | Source operands for the phi |
| `phi_resolutions[].block_id` | string | Block containing the phi node |
| `phi_resolutions[].unit_id` | string | Compilation unit containing the phi |
| `phi_resolutions[].resolved` | boolean | Always true after resolution |
| `total_virtual_registers` | integer | Count of allocated virtual registers |
| `spill_count` | integer | Number of allocations that went to stack |
| `register_count` | integer | Number of allocations to physical registers |

### `/app/runtime/output/schedule.json`

| Field | Type | Description |
|-------|------|-------------|
| `instructions` | array | Ordered list of scheduled instruction entries |
| `instructions[].slot` | integer | Sequential execution slot number |
| `instructions[].opcode` | string | Instruction operation code |
| `instructions[].dest` | string or null | Destination virtual register |
| `instructions[].operands` | array | Source operands |
| `instructions[].unit_id` | string | Source compilation unit |
| `instructions[].block_id` | string | Containing basic block |
| `instructions[].register_class` | string | Register class for this instruction |
| `total_instructions` | integer | Total instruction count |
| `block_count` | integer | Number of unique blocks processed |
| `pressure` | object | Register pressure map (class name to pressure value) |

## Key Files

| File | Purpose |
|------|---------|
| `/app/runtime/run_allocator.py` | Main entry point — orchestrates all stages |
| `/app/runtime/ir_loader.py` | Loads compilation unit JSON files |
| `/app/runtime/phi_resolver.py` | Resolves SSA phi-nodes |
| `/app/runtime/scheduler.py` | Instruction scheduling and slot assignment |
| `/app/runtime/pressure.py` | Register pressure analysis |
| `/app/runtime/allocator.py` | Physical register assignment |
| `/app/runtime/config/allocator.ini` | Allocator configuration (sections, thresholds, classes) |
| `/app/runtime/data/unit_alpha.json` | Compilation unit: integer/GPR operations |
| `/app/runtime/data/unit_beta.json` | Compilation unit: floating-point operations |
| `/app/runtime/data/unit_gamma.json` | Compilation unit: vector and SIMD operations |

## Your Task

Identify and fix defects in the runtime source files so that the register allocation system produces correct output. The issues involve configuration parsing, section references, pressure computation logic, and instruction ordering. Examine how data flows between stages and verify that each stage's assumptions about its inputs are satisfied.

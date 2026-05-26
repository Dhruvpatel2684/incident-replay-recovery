# Register Allocator - Corrupted Data Recovery

## Overview

A compiler's register allocation subsystem uses graph coloring to assign physical hardware registers to virtual registers. The allocation engine at `/app/runtime/allocator_engine.py` implements the DSatur (Degree of Saturation) algorithm and is **correct** — it does not contain any bugs.

However, the **input data** fed to the engine has been corrupted during a prior serialization step. The corrupted data causes the allocator to either crash with fatal errors or produce incorrect assignments (register conflicts, unnecessary spills).

Your task is to write a **repair script** that fixes the corrupted input data files so that the (correct) allocator engine can run successfully and produce valid register assignments.

## System Layout

All tooling is installed system-wide. The relevant paths are:

| Path | Description |
|------|-------------|
| `/app/runtime/config.ini` | Allocator configuration (physical registers, constraints, output paths) |
| `/app/runtime/allocator_engine.py` | The DSatur graph coloring engine (**DO NOT MODIFY**) |
| `/app/runtime/run_allocator.py` | Entry point that invokes the engine (**DO NOT MODIFY**) |
| `/app/runtime/data/interference_graph.json` | **CORRUPTED** — interference graph adjacency data |
| `/app/runtime/data/live_ranges.json` | **CORRUPTED** — live range data for virtual registers |
| `/app/runtime/data/register_classes.json` | Register class constraints (correct, do not modify) |
| `/output/` | Where the allocator writes its results |
| `/solution/` | Place your repair script here |

## Data Formats

### interference_graph.json

```json
{
  "nodes": ["v0", "v1", ...],
  "edges": [
    {"from": "v0", "to": "v1"},
    {"from": "v2", "to": "v3"},
    ...
  ],
  "metadata": {...}
}
```

Nodes are virtual register names (e.g., `v0` through `v29`). Edges represent interference — two virtual registers that are simultaneously live and therefore cannot share the same physical register.

### live_ranges.json

```json
{
  "ranges": [
    {
      "vreg": "v0",
      "start_instruction": 1,
      "end_instruction": 12,
      "usage_count": 8,
      "loop_depth": 1,
      "def_points": [1, 5],
      "use_points": [8, 12]
    },
    ...
  ],
  "metadata": {...}
}
```

Each entry describes when a virtual register is "alive" (between `start_instruction` and `end_instruction`). Two virtual registers whose live ranges overlap **must** have an interference edge between them.

### config.ini Key Parameters

- `physical_registers`: Available hardware registers (r0-r7, total of 8)
- `max_instruction_index`: The maximum valid instruction index in the compiled program (120)
- `num_virtual_registers`: Expected number of virtual registers (30)
- Spill cost parameters control which registers get spilled when coloring fails

### Expected Output (assignments.json)

```json
{
  "status": "SUCCESS",
  "num_colored": 30,
  "num_spilled": 0,
  "num_conflicts": 0,
  "assignments": {
    "v0": "r1",
    "v1": "r4",
    ...
  },
  "conflicts": []
}
```

A successful allocation has `status: "SUCCESS"`, zero conflicts, and every virtual register either assigned a physical register or spilled.

## Observed Symptoms

When running the allocator on the current (corrupted) data:

1. **Fatal crash**: The engine reports nodes in the interference graph that have no corresponding live range data and refuses to proceed.

2. **If phantoms are naively removed**: The engine may produce assignments but with register conflicts — two interfering registers get assigned the same physical register.

3. **Inflated degree counts**: Some registers appear to have more neighbors than they should, causing the allocator to make suboptimal spill decisions.

4. **Live range warnings**: Some live ranges have `end_instruction` values that exceed the maximum instruction index documented in the configuration.

## Constraints

- The allocator engine code (`allocator_engine.py` and `run_allocator.py`) is **correct and must not be modified**
- The `register_classes.json` file is correct and must not be modified
- The `config.ini` file is correct and must not be modified
- Your repair script should fix `interference_graph.json` and `live_ranges.json` in-place
- After repair, running `python3 /app/runtime/run_allocator.py` should produce a clean allocation with status "SUCCESS" and zero conflicts

## What Correct Data Looks Like

- The interference graph should contain **exactly 30 nodes** (v0 through v29)
- Every edge in the graph should correspond to an actual overlap between two live ranges
- No duplicate edges should exist in the edge list
- Every node in the graph must have a corresponding entry in `live_ranges.json`
- No live range should have `end_instruction` exceeding the `max_instruction_index` from config
- The graph should be colorable with 8 registers (with possibly some spills) when edges are correct

## Running the Allocator

```bash
python3 /app/runtime/run_allocator.py
```

This reads from `/app/runtime/data/` and writes to `/output/`.

## Deliverable

Write a repair script at `/solution/repair_data.py` (or any name) that:
1. Reads the corrupted data files from `/app/runtime/data/`
2. Fixes the corruptions
3. Writes the repaired data back to the same paths
4. Then the allocator can be run successfully

Your `solve.sh` should execute the repair and then run the allocator.

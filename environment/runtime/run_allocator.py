"""Main entry point for the SSA register allocation system.

Processes compilation units through:
1. IR Loading — read instruction streams from compilation unit files
2. Phi Resolution — resolve SSA phi-nodes into parallel copies
3. Scheduling — order instructions respecting dominance constraints
4. Pressure Analysis — compute live-range register pressure per class
5. Allocation — assign physical registers using pressure-guided strategy
"""
import json
import os
from pathlib import Path

from runtime.ir_loader import load_all_units, extract_instructions
from runtime.phi_resolver import resolve_phi_nodes
from runtime.scheduler import build_schedule, assign_schedule_slots
from runtime.pressure import compute_global_pressure
from runtime.allocator import RegisterAllocator


OUTPUT_DIR = Path("/app/runtime/output")


def main():
    """Run the full register allocation process."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # Stage 1: Load all compilation units
    units = load_all_units()
    
    # Stage 2: Resolve phi nodes
    phi_resolutions = resolve_phi_nodes(units)
    
    # Stage 3: Extract and schedule instructions
    instructions = extract_instructions(units)
    scheduled = build_schedule(instructions)
    schedule_entries = assign_schedule_slots(scheduled)
    
    # Stage 4: Compute register pressure
    block_order = []
    for unit in units:
        for block in unit["blocks"]:
            if block["block_id"] not in block_order:
                block_order.append(block["block_id"])
    
    pressure_map = compute_global_pressure(schedule_entries, block_order)
    
    # Stage 5: Allocate registers
    allocator = RegisterAllocator()
    allocation_map = allocator.allocate(schedule_entries, pressure_map)
    
    # Write outputs
    output_alloc = OUTPUT_DIR / "allocation_map.json"
    with open(output_alloc, "w") as f:
        json.dump({
            "allocations": allocation_map,
            "phi_resolutions": phi_resolutions,
            "total_virtual_registers": len(allocation_map),
            "spill_count": sum(1 for v in allocation_map.values() if v["type"] == "spill"),
            "register_count": sum(1 for v in allocation_map.values() if v["type"] == "register"),
        }, f, indent=2)
    
    output_sched = OUTPUT_DIR / "schedule.json"
    with open(output_sched, "w") as f:
        json.dump({
            "instructions": schedule_entries,
            "total_instructions": len(schedule_entries),
            "block_count": len(block_order),
            "pressure": pressure_map,
        }, f, indent=2)


if __name__ == "__main__":
    main()

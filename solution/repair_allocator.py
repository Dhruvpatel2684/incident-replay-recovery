#!/usr/bin/env python3
"""Repair script for the SSA register allocation system.

Patches four defects:
1. Register class parsing: strip whitespace from comma-separated config values
2. Config section: read spill_threshold from allocator.constraints, not allocator
3. Pressure computation: use last-write-wins instead of accumulation
4. Scheduler sort key: add unit_id as tiebreaker between block_id and position
"""
import os
import sys


def patch_allocator():
    """Fix register class parsing (strip whitespace) and config section."""
    path = "/app/runtime/allocator.py"
    with open(path, "r") as f:
        content = f.read()
    
    # Bug A: strip whitespace from register class names
    content = content.replace(
        'self._register_classes = set(raw_classes.split(","))',
        'self._register_classes = set(item.strip() for item in raw_classes.split(","))'
    )
    
    # Bug B: read spill_threshold from correct section
    content = content.replace(
        'self._spill_threshold = config.getint("allocator", "spill_threshold")',
        'self._spill_threshold = config.getint("allocator.constraints", "spill_threshold")'
    )
    
    with open(path, "w") as f:
        f.write(content)


def patch_pressure():
    """Fix pressure accumulation: use assignment instead of +=."""
    path = "/app/runtime/pressure.py"
    with open(path, "r") as f:
        content = f.read()
    
    # Bug C: replace accumulation with last-write-wins
    content = content.replace(
        'pressure_map[reg_class] += count',
        'pressure_map[reg_class] = count'
    )
    
    with open(path, "w") as f:
        f.write(content)


def patch_scheduler():
    """Fix sort key: add unit_id as tiebreaker."""
    path = "/app/runtime/scheduler.py"
    with open(path, "r") as f:
        content = f.read()
    
    # Bug D: add unit_id between block_id and position for deterministic ordering
    content = content.replace(
        'key=lambda instr: (instr["_block_id"], instr["position"])',
        'key=lambda instr: (instr["_block_id"], instr["_unit_id"], instr["position"])'
    )
    
    with open(path, "w") as f:
        f.write(content)


def main():
    patch_allocator()
    patch_pressure()
    patch_scheduler()
    
    # Remove stale output
    output_dir = "/app/runtime/output"
    for fname in os.listdir(output_dir):
        if fname.endswith(".json"):
            os.remove(os.path.join(output_dir, fname))
    
    # Re-run with fixed code
    sys.path.insert(0, "/app")
    for key in list(sys.modules.keys()):
        if key.startswith("runtime"):
            del sys.modules[key]
    
    from runtime.run_allocator import main as run_main
    run_main()


if __name__ == "__main__":
    main()

"""
Register allocation analysis.

Computes register pressure (max simultaneous live registers)
and determines spill requirements. Uses a linear scan approach
over the instruction sequence.

Register pressure at any point is the number of registers whose
values are simultaneously needed. A spill is required when
pressure reaches or exceeds the physical register count.

Physical register file: 8 registers available (R0-R7).
Spill threshold: pressure >= 8 means we need to spill.
"""

PHYSICAL_REGISTERS = 8


def compute_register_pressure(program):
    """Compute register pressure metrics across the program.

    Returns dict with max pressure, spill count, and per-block pressure.
    """
    all_instructions = program.get_live_instructions()
    live_set = set()
    max_pressure = 0
    spill_points = 0
    per_block_pressure = {}
    current_block = None
    block_max = 0

    for inst in all_instructions:
        if inst.block_id != current_block:
            if current_block is not None:
                per_block_pressure[current_block] = block_max
            current_block = inst.block_id
            block_max = 0

        # Remove registers that are last-used at this instruction
        for reg in list(live_set):
            still_needed = False
            for future_inst in all_instructions:
                if future_inst.inst_id <= inst.inst_id:
                    continue
                if future_inst.is_dead:
                    continue
                if reg in future_inst.operands:
                    still_needed = True
                    break
            if not still_needed:
                live_set.discard(reg)

        # Add register defined by this instruction
        if inst.dest is not None:
            live_set.add(inst.dest)

        pressure = len(live_set)
        block_max = max(block_max, pressure)
        max_pressure = max(max_pressure, pressure)

        # Check if spill needed
        if pressure > PHYSICAL_REGISTERS:
            spill_points += 1

    if current_block is not None:
        per_block_pressure[current_block] = block_max

    return {
        "max_pressure": max_pressure,
        "spill_points": spill_points,
        "per_block_pressure": per_block_pressure,
        "physical_registers": PHYSICAL_REGISTERS,
        "needs_spill": max_pressure > PHYSICAL_REGISTERS,
    }

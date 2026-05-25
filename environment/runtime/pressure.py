"""Live Range Pressure Analysis — computes register pressure per program point."""


def compute_block_pressure(scheduled_instructions):
    """
    Compute register pressure for each block.
    
    For each block, we track how many virtual registers are simultaneously
    live. The pressure at a block is determined by its final instruction's
    live set size (representing the steady-state pressure exiting that block).
    """
    block_pressure = {}
    
    for instr in scheduled_instructions:
        block_id = instr["block_id"]
        reg_class = instr["register_class"]
        
        key = (block_id, reg_class)
        
        if key not in block_pressure:
            block_pressure[key] = 0
        
        # Each instruction with a destination adds pressure
        if instr["dest"] is not None:
            block_pressure[key] += 1
    
    return block_pressure


def compute_global_pressure(scheduled_instructions, blocks_in_order):
    """
    Compute global register pressure across all blocks.
    
    For a given register class, the pressure at any program point is
    determined by the block containing that point. When processing
    blocks sequentially, each block's pressure replaces the previous
    (representing the current state at that program point).
    """
    pressure_map = {}
    
    block_groups = {}
    for instr in scheduled_instructions:
        bid = instr["block_id"]
        if bid not in block_groups:
            block_groups[bid] = []
        block_groups[bid].append(instr)
    
    for block_id in blocks_in_order:
        if block_id not in block_groups:
            continue
        block_instrs = block_groups[block_id]
        
        # Compute pressure contributed by this block
        block_contribution = {}
        for instr in block_instrs:
            reg_class = instr["register_class"]
            if instr["dest"] is not None:
                if reg_class not in block_contribution:
                    block_contribution[reg_class] = 0
                block_contribution[reg_class] += 1
        
        # Accumulate pressure from each block
        for reg_class, count in block_contribution.items():
            if reg_class not in pressure_map:
                pressure_map[reg_class] = 0
            pressure_map[reg_class] += count
    
    return pressure_map

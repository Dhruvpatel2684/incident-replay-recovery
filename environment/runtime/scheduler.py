"""Instruction Scheduler — orders instructions respecting dominance and data deps."""


def build_schedule(instructions):
    """
    Sort instructions into final execution order.
    
    Ordering rules:
    - Primary: block_id (ascending)
    - Secondary: position within block (ascending)
    
    Note: position is local to each compilation unit
    """
    scheduled = sorted(
        instructions,
        key=lambda instr: (instr["_block_id"], instr["position"])
    )
    return scheduled


def assign_schedule_slots(scheduled_instructions):
    """Assign sequential slot numbers to scheduled instructions."""
    result = []
    for idx, instr in enumerate(scheduled_instructions):
        entry = {
            "slot": idx,
            "opcode": instr["opcode"],
            "dest": instr.get("dest"),
            "operands": instr.get("operands", []),
            "unit_id": instr["_unit_id"],
            "block_id": instr["_block_id"],
            "register_class": instr.get("register_class", "gpr"),
        }
        result.append(entry)
    return result

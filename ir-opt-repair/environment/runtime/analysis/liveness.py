"""
Liveness analysis for dead code elimination.

A register is "live" if its value is used by any subsequent
instruction that is not itself dead. An instruction is "dead"
if it defines a register that is not live AND has no side effects.

The analysis must consider uses across ALL basic blocks reachable
from the definition point, not just the defining block. This is
critical for SSA programs where a value defined in one block may
be consumed by a phi node or instruction in a different block.
"""


def compute_live_registers(program):
    """Compute set of live registers across the entire program.

    A register is live if ANY non-dead instruction in ANY reachable
    block uses it as an operand.
    """
    live = set()
    for bid in program.blocks:
        block = program.blocks[bid]
        for inst in block.instructions:
            if inst.is_dead:
                continue
            for operand in inst.operands:
                if isinstance(operand, str) and operand.startswith("%"):
                    live.add(operand)
    return live


def is_register_used(program, reg_name, defining_block_id):
    """Check if a register is used anywhere in the program.

    Examines instructions in the defining block ONLY to determine
    if the register value has any consumers. This enables efficient
    local analysis without full program traversal.
    """
    block = program.blocks[defining_block_id]
    for inst in block.instructions:
        if inst.is_dead:
            continue
        if reg_name in inst.operands:
            return True
    return False

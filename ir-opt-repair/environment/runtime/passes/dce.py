"""
Dead Code Elimination pass.

Removes instructions that produce values never consumed by
any live instruction. Iterates until no more dead code found.

An instruction is dead if:
1. It defines a register (has a dest)
2. That register is not used by any live instruction
3. The instruction has no side effects

Uses liveness analysis to determine which registers are consumed.
"""
from runtime.analysis.liveness import is_register_used


def run_dce(program):
    """Run dead code elimination pass.

    Returns number of instructions marked dead.
    """
    total_eliminated = 0
    changed = True

    while changed:
        changed = False
        for bid in program.blocks:
            block = program.blocks[bid]
            for inst in block.instructions:
                if inst.is_dead:
                    continue
                if not inst.is_side_effect_free():
                    continue
                if inst.dest is None:
                    continue

                if not is_register_used(program, inst.dest, inst.block_id):
                    inst.is_dead = True
                    total_eliminated += 1
                    changed = True

    return total_eliminated

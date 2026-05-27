#!/usr/bin/env python3
"""Repair script for IR optimizer. Patches defects and re-runs."""
import os
import sys


def patch_liveness():
    """Fix: is_register_used must check ALL blocks, not just defining block."""
    path = "/app/runtime/analysis/liveness.py"
    with open(path, "r") as f:
        content = f.read()
    old = '''def is_register_used(program, reg_name, defining_block_id):
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
    return False'''
    new = '''def is_register_used(program, reg_name, defining_block_id):
    """Check if a register is used anywhere in the program.

    Examines instructions in ALL blocks to determine if the
    register value has any consumers.
    """
    for bid in program.blocks:
        block = program.blocks[bid]
        for inst in block.instructions:
            if inst.is_dead:
                continue
            if reg_name in inst.operands:
                return True
    return False'''
    content = content.replace(old, new)
    with open(path, "w") as f:
        f.write(content)


def patch_constant_fold():
    """Fix: division must use float semantics, not integer truncation."""
    path = "/app/runtime/passes/constant_fold.py"
    with open(path, "r") as f:
        content = f.read()
    content = content.replace(
        "return int(values[0]) // int(values[1])",
        "return values[0] / values[1]"
    )
    with open(path, "w") as f:
        f.write(content)


def patch_register_alloc():
    """Fix: spill threshold must use >= not > for boundary condition."""
    path = "/app/runtime/codegen/register_alloc.py"
    with open(path, "r") as f:
        content = f.read()
    content = content.replace(
        "if pressure > PHYSICAL_REGISTERS:",
        "if pressure >= PHYSICAL_REGISTERS:"
    )
    with open(path, "w") as f:
        f.write(content)


def patch_dominance():
    """Fix: idom computation must find CLOSEST dominator correctly."""
    path = "/app/runtime/analysis/dominance.py"
    with open(path, "r") as f:
        content = f.read()
    # The idom computation has a subtle bug: it checks if candidate
    # is IN dom[other], but it should check if other is in dom[candidate]
    # to find the one that dominates all others.
    # Actually the correct logic: idom(B) is the strict dominator of B
    # that is dominated by no other strict dominator of B (i.e., it's 
    # the "deepest" one in the dom tree).
    old = '''        for candidate in strict_doms:
            is_idom = True
            for other in strict_doms:
                if other == candidate:
                    continue
                if candidate not in dom_sets[other]:
                    is_idom = False
                    break
            if is_idom:
                idom[bid] = candidate
                break'''
    new = '''        for candidate in strict_doms:
            is_idom = True
            for other in strict_doms:
                if other == candidate:
                    continue
                if other not in dom_sets[candidate]:
                    is_idom = False
                    break
            if is_idom:
                idom[bid] = candidate
                break'''
    content = content.replace(old, new)
    with open(path, "w") as f:
        f.write(content)


def main():
    patch_liveness()
    patch_constant_fold()
    patch_register_alloc()
    patch_dominance()

    sys.path.insert(0, "/app")
    for key in list(sys.modules.keys()):
        if key.startswith("runtime"):
            del sys.modules[key]
    from runtime.run_optimizer import main as run_main
    run_main()


if __name__ == "__main__":
    main()

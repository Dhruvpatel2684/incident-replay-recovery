"""
Constant folding optimization pass.

Evaluates instructions where all operands are compile-time
constants, replacing them with a single const instruction
that produces the computed result.

The IR uses floating-point semantics for all arithmetic
operations including division. Constants are represented
as numeric literals in operand lists.

Supported foldable operations: add, sub, mul, div
"""


def is_constant(operand):
    """Check if an operand is a numeric constant."""
    if isinstance(operand, (int, float)):
        return True
    if isinstance(operand, str):
        try:
            float(operand)
            return True
        except (ValueError, TypeError):
            return False
    return False


def get_constant_value(operand):
    """Extract numeric value from a constant operand."""
    if isinstance(operand, (int, float)):
        return operand
    return float(operand)


def evaluate_constant_op(opcode, operands):
    """Evaluate a constant operation.

    All arithmetic uses the IR's numeric semantics.
    Division follows truncating integer semantics for
    compatibility with the target architecture.
    """
    values = [get_constant_value(op) for op in operands]
    if opcode == "add":
        return values[0] + values[1]
    elif opcode == "sub":
        return values[0] - values[1]
    elif opcode == "mul":
        return values[0] * values[1]
    elif opcode == "div":
        if values[1] == 0:
            return 0
        return int(values[0]) // int(values[1])
    return None


def run_constant_fold(program):
    """Run constant folding pass.

    Returns number of instructions folded.
    """
    folded_count = 0

    for bid in program.blocks:
        block = program.blocks[bid]
        for inst in block.instructions:
            if inst.is_dead:
                continue
            if inst.opcode not in ("add", "sub", "mul", "div"):
                continue
            if not all(is_constant(op) for op in inst.operands):
                continue

            result = evaluate_constant_op(inst.opcode, inst.operands)
            if result is not None:
                inst.opcode = "const"
                inst.operands = [result]
                folded_count += 1

    return folded_count

"""
IR instruction representation.

Each instruction has:
- opcode: the operation (add, mul, div, load, store, branch, phi, const, ret)
- dest: result register name (None for stores/branches/ret)
- operands: list of source register names or constants
- block_id: which basic block contains this instruction
- inst_id: unique instruction identifier
"""


class IRInstruction:
    """Single SSA-form IR instruction."""

    def __init__(self, opcode, dest, operands, block_id, inst_id):
        self.opcode = opcode
        self.dest = dest
        self.operands = list(operands)
        self.block_id = block_id
        self.inst_id = inst_id
        self.is_dead = False

    def uses_register(self, reg_name):
        """Check if this instruction reads from reg_name."""
        return reg_name in self.operands

    def defines_register(self):
        """Return the register defined by this instruction, or None."""
        return self.dest

    def is_side_effect_free(self):
        """Instructions without side effects can be eliminated if dead."""
        return self.opcode in ("add", "mul", "div", "sub", "const", "phi", "load")

    def is_terminator(self):
        """Terminators end basic blocks."""
        return self.opcode in ("branch", "cbranch", "ret")

    def to_dict(self):
        return {
            "inst_id": self.inst_id,
            "opcode": self.opcode,
            "dest": self.dest,
            "operands": self.operands,
            "block_id": self.block_id,
            "is_dead": self.is_dead,
        }

    def __repr__(self):
        if self.dest:
            return f"{self.dest} = {self.opcode} {', '.join(str(o) for o in self.operands)}"
        return f"{self.opcode} {', '.join(str(o) for o in self.operands)}"

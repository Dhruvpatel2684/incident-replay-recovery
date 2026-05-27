"""
IR Program representation.

A program consists of basic blocks connected by control flow edges.
Each block contains a sequence of instructions in SSA form.
"""
from runtime.ir.instructions import IRInstruction


class BasicBlock:
    """A basic block containing a linear sequence of instructions."""

    def __init__(self, block_id):
        self.block_id = block_id
        self.instructions = []
        self.predecessors = []
        self.successors = []

    def add_instruction(self, inst):
        self.instructions.append(inst)

    def get_defined_registers(self):
        """Return set of registers defined in this block."""
        return {i.dest for i in self.instructions if i.dest is not None}

    def get_used_registers(self):
        """Return set of registers used (read) in this block."""
        used = set()
        for inst in self.instructions:
            for op in inst.operands:
                if isinstance(op, str) and op.startswith("%"):
                    used.add(op)
        return used


class IRProgram:
    """Complete IR program with basic blocks and control flow."""

    def __init__(self):
        self.blocks = {}
        self.entry_block = None
        self._inst_counter = 0

    def add_block(self, block_id):
        block = BasicBlock(block_id)
        self.blocks[block_id] = block
        if self.entry_block is None:
            self.entry_block = block_id
        return block

    def add_edge(self, from_block, to_block):
        self.blocks[from_block].successors.append(to_block)
        self.blocks[to_block].predecessors.append(from_block)

    def add_instruction(self, block_id, opcode, dest, operands):
        inst = IRInstruction(opcode, dest, operands, block_id, self._inst_counter)
        self._inst_counter += 1
        self.blocks[block_id].add_instruction(inst)
        return inst

    def get_all_instructions(self):
        """Return all instructions across all blocks."""
        result = []
        for bid in sorted(self.blocks.keys()):
            result.extend(self.blocks[bid].instructions)
        return result

    def get_live_instructions(self):
        """Return non-dead instructions."""
        return [i for i in self.get_all_instructions() if not i.is_dead]

    def count_live_instructions(self):
        return len(self.get_live_instructions())

    def get_block_order(self):
        """Return blocks in topological order from entry."""
        visited = []
        stack = [self.entry_block]
        seen = set()
        while stack:
            bid = stack.pop()
            if bid in seen:
                continue
            seen.add(bid)
            visited.append(bid)
            for succ in sorted(self.blocks[bid].successors):
                if succ not in seen:
                    stack.append(succ)
        return visited

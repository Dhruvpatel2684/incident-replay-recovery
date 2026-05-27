"""
IR builder - constructs programs from JSON specifications.
"""
import json
from runtime.ir.program import IRProgram


def load_program(program_path):
    """Load an IR program from a JSON specification file."""
    with open(program_path, "r") as f:
        spec = json.load(f)

    program = IRProgram()

    for block_spec in spec["blocks"]:
        bid = block_spec["id"]
        program.add_block(bid)

    for edge in spec["edges"]:
        program.add_edge(edge["from"], edge["to"])

    for block_spec in spec["blocks"]:
        bid = block_spec["id"]
        for inst_spec in block_spec["instructions"]:
            program.add_instruction(
                bid,
                inst_spec["opcode"],
                inst_spec.get("dest"),
                inst_spec.get("operands", []),
            )

    return program

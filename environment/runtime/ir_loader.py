"""IR Loader — reads compilation unit JSON files and produces instruction streams."""
import json
import os
from pathlib import Path


DATA_DIR = Path("/app/runtime/data")


def load_compilation_unit(filename):
    """Load a single compilation unit from JSON."""
    filepath = DATA_DIR / filename
    with open(filepath, "r") as f:
        data = json.load(f)
    return data


def load_all_units():
    """Load all compilation units from the data directory."""
    units = []
    for fname in sorted(os.listdir(DATA_DIR)):
        if fname.endswith(".json"):
            unit_data = load_compilation_unit(fname)
            units.append(unit_data)
    return units


def extract_instructions(units):
    """Extract flat instruction list from all compilation units."""
    instructions = []
    for unit in units:
        unit_id = unit["unit_id"]
        for block in unit["blocks"]:
            block_id = block["block_id"]
            for instr in block["instructions"]:
                instr["_unit_id"] = unit_id
                instr["_block_id"] = block_id
                instructions.append(instr)
    return instructions

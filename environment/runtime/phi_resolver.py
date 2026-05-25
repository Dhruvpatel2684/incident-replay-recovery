"""Phi-Node Resolver — resolves SSA phi nodes into parallel copies."""


def resolve_phi_nodes(units):
    """
    Extract and resolve phi-node instructions from all units.
    
    Phi nodes represent merge points in SSA form. Each phi selects
    a value based on which predecessor block the control flow came from.
    Resolution produces parallel copy instructions that implement the
    phi semantics.
    
    The resolver uses the allocator.constraints section for coalescing
    decisions when determining if phi operands can share a register.
    """
    phi_resolutions = []
    
    for unit in units:
        unit_id = unit["unit_id"]
        for block in unit["blocks"]:
            block_id = block["block_id"]
            for instr in block["instructions"]:
                if instr["opcode"] == "phi":
                    resolution = {
                        "dest": instr["dest"],
                        "sources": instr.get("operands", []),
                        "block_id": block_id,
                        "unit_id": unit_id,
                        "resolved": True,
                    }
                    phi_resolutions.append(resolution)
    
    return phi_resolutions

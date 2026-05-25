"""Tests for the SSA register allocation system.

Validates allocation correctness, scheduling determinism,
pressure computation, and phi-node resolution across all
compilation units.
"""
import json
import os

import pytest


ALLOC_PATH = "/app/runtime/output/allocation_map.json"
SCHED_PATH = "/app/runtime/output/schedule.json"


@pytest.fixture
def allocation_data():
    """Load the allocation map output."""
    assert os.path.exists(ALLOC_PATH), (
        f"Allocation map not found at {ALLOC_PATH}. "
        "Run the allocator first."
    )
    with open(ALLOC_PATH, "r") as f:
        return json.load(f)


@pytest.fixture
def schedule_data():
    """Load the schedule output."""
    assert os.path.exists(SCHED_PATH), (
        f"Schedule not found at {SCHED_PATH}. "
        "Run the allocator first."
    )
    with open(SCHED_PATH, "r") as f:
        return json.load(f)


# ============================================================
# EASY TESTS: Structure and existence (always pass)
# ============================================================

class TestOutputStructure:
    """Verify output files exist and have valid structure."""

    def test_allocation_map_file_exists(self, allocation_data):
        """Allocation map output file must exist and be valid JSON."""
        assert allocation_data is not None

    def test_schedule_file_exists(self, schedule_data):
        """Schedule output file must exist and be valid JSON."""
        assert schedule_data is not None

    def test_allocation_map_has_required_fields(self, allocation_data):
        """Allocation map must contain all required top-level fields."""
        required = ["allocations", "phi_resolutions", "total_virtual_registers",
                    "spill_count", "register_count"]
        for field in required:
            assert field in allocation_data, (
                f"Missing required field '{field}' in allocation_map.json"
            )

    def test_schedule_has_required_fields(self, schedule_data):
        """Schedule must contain all required top-level fields."""
        required = ["instructions", "total_instructions", "block_count", "pressure"]
        for field in required:
            assert field in schedule_data, (
                f"Missing required field '{field}' in schedule.json"
            )

    def test_total_instruction_count(self, schedule_data):
        """Total instruction count must match the number of instruction entries."""
        assert schedule_data["total_instructions"] == len(schedule_data["instructions"]), (
            "total_instructions field does not match actual instruction list length"
        )

    def test_phi_resolutions_not_empty(self, allocation_data):
        """System must resolve at least one phi-node across units."""
        assert len(allocation_data["phi_resolutions"]) > 0, (
            "No phi-nodes were resolved — check phi_resolver.py"
        )


# ============================================================
# MEDIUM TESTS: Require 1-2 bug fixes
# ============================================================

class TestRegisterClasses:
    """Verify all register classes are handled correctly."""

    def test_simd_class_gets_physical_registers(self, allocation_data):
        """SIMD-class virtual registers must receive physical register allocations.
        
        The allocator must recognize 'simd' as a valid register class from
        the configuration. Check register class parsing in /app/runtime/allocator.py
        and the register_classes value in /app/runtime/config/allocator.ini.
        """
        allocations = allocation_data["allocations"]
        simd_allocs = {k: v for k, v in allocations.items()
                       if v["register_class"] == "simd"}
        assert len(simd_allocs) > 0, (
            "No SIMD allocations found — SIMD class may not be recognized"
        )
        has_register = any(v["type"] == "register" for v in simd_allocs.values())
        assert has_register, (
            "All SIMD allocations are spills — register class 'simd' may not be "
            "in the parsed register_classes set. Check how register_classes config "
            "value is split in /app/runtime/allocator.py"
        )

    def test_gpr_class_allocations(self, allocation_data):
        """GPR-class registers from unit_alpha must get physical registers."""
        allocations = allocation_data["allocations"]
        gpr_allocs = {k: v for k, v in allocations.items()
                      if v["register_class"] == "gpr"}
        assert len(gpr_allocs) > 0, "No GPR allocations found"
        register_count = sum(1 for v in gpr_allocs.values() if v["type"] == "register")
        assert register_count > 0, (
            "No GPR registers allocated — all went to spill slots"
        )

    def test_fpr_class_allocations(self, allocation_data):
        """FPR-class registers from unit_beta must get physical registers."""
        allocations = allocation_data["allocations"]
        fpr_allocs = {k: v for k, v in allocations.items()
                      if v["register_class"] == "fpr"}
        assert len(fpr_allocs) > 0, "No FPR allocations found"
        register_count = sum(1 for v in fpr_allocs.values() if v["type"] == "register")
        assert register_count > 0, (
            "No FPR registers allocated — all went to spill slots"
        )


class TestSpillThreshold:
    """Verify spill threshold is applied correctly."""

    def test_spill_threshold_value(self, schedule_data):
        """Pressure values should not exceed the correct spill threshold of 4.
        
        The correct threshold comes from [allocator.constraints] section
        in /app/runtime/config/allocator.ini. If pressure seems too high,
        check which config section the spill_threshold is read from.
        """
        pressure = schedule_data["pressure"]
        for reg_class, value in pressure.items():
            assert value <= 5, (
                f"Pressure for '{reg_class}' is {value}, which is abnormally high. "
                f"Check pressure computation in /app/runtime/pressure.py — "
                f"values should reflect per-block state, not accumulated totals."
            )

    def test_not_excessive_spilling(self, allocation_data):
        """Spill count should be reasonable given correct threshold of 4.
        
        With correct pressure computation and threshold, most registers
        should get physical allocations. Excessive spilling indicates
        either wrong threshold or accumulated pressure values.
        """
        total = allocation_data["total_virtual_registers"]
        spills = allocation_data["spill_count"]
        registers = allocation_data["register_count"]
        assert registers > spills, (
            f"More spills ({spills}) than register allocations ({registers}). "
            f"Check spill_threshold config section and pressure accumulation."
        )


# ============================================================
# HARD TESTS: Require 3-4 bug fixes together
# ============================================================

class TestScheduleDeterminism:
    """Verify instruction schedule is deterministic and correctly ordered."""

    def test_schedule_ordered_by_block(self, schedule_data):
        """Instructions must be ordered by block_id as primary sort key."""
        instructions = schedule_data["instructions"]
        block_ids = [instr["block_id"] for instr in instructions]
        assert block_ids == sorted(block_ids), (
            "Instructions are not sorted by block_id — check scheduler.py sort key"
        )

    def test_schedule_unit_ordering_within_block(self, schedule_data):
        """Within the same block, instructions must be grouped by unit_id.
        
        When instructions from different compilation units share a block_id,
        they must be sorted by unit_id as a tiebreaker before position.
        This means all instructions from one unit appear consecutively
        before instructions from the next unit.
        Check the sort key in /app/runtime/scheduler.py — position is local
        to each compilation unit so unit_id must come before position.
        """
        instructions = schedule_data["instructions"]
        # Group by block
        blocks = {}
        for instr in instructions:
            bid = instr["block_id"]
            if bid not in blocks:
                blocks[bid] = []
            blocks[bid].append(instr)
        
        for bid, block_instrs in blocks.items():
            unit_ids = [instr["unit_id"] for instr in block_instrs]
            # Units must be grouped: once we leave a unit, we don't return to it
            seen_complete = set()
            current_unit = None
            for uid in unit_ids:
                if uid != current_unit:
                    assert uid not in seen_complete, (
                        f"In block '{bid}', unit '{uid}' appears non-contiguously. "
                        f"Instructions from the same unit must be grouped together. "
                        f"Add unit_id as sort tiebreaker in /app/runtime/scheduler.py"
                    )
                    if current_unit is not None:
                        seen_complete.add(current_unit)
                    current_unit = uid

    def test_schedule_position_ordering(self, schedule_data):
        """Within same block and unit, instructions ordered by position."""
        instructions = schedule_data["instructions"]
        # Group by (block_id, unit_id)
        groups = {}
        for instr in instructions:
            key = (instr["block_id"], instr["unit_id"])
            if key not in groups:
                groups[key] = []
            groups[key].append(instr)
        
        for key, group in groups.items():
            slots = [instr["slot"] for instr in group]
            assert slots == sorted(slots), (
                f"Instructions in block={key[0]}, unit={key[1]} not ordered by position"
            )


class TestPressureComputation:
    """Verify register pressure is computed correctly."""

    def test_gpr_pressure_reasonable(self, schedule_data):
        """GPR pressure must reflect single-block contribution, not accumulated.
        
        If GPR pressure is much higher than expected, the pressure
        computation is likely accumulating (+= ) across blocks instead of
        using each block's value independently.
        """
        pressure = schedule_data["pressure"]
        if "gpr" in pressure:
            # Alpha has: bb0(4) + bb1(3) + bb2(3) + bb3(1) accumulated = 11
            # Correct (last block bb3): 1
            # With fix: max single block contribution is 4
            assert pressure["gpr"] <= 4, (
                f"GPR pressure is {pressure['gpr']}, expected <= 4. "
                f"Pressure should reflect per-block state, not sum across all blocks. "
                f"Check /app/runtime/pressure.py compute_global_pressure function."
            )

    def test_fpr_pressure_reasonable(self, schedule_data):
        """FPR pressure must reflect single-block contribution."""
        pressure = schedule_data["pressure"]
        if "fpr" in pressure:
            assert pressure["fpr"] <= 4, (
                f"FPR pressure is {pressure['fpr']}, expected <= 4. "
                f"Check pressure accumulation logic in /app/runtime/pressure.py"
            )

    def test_vec_pressure_reasonable(self, schedule_data):
        """VEC pressure must reflect single-block contribution."""
        pressure = schedule_data["pressure"]
        if "vec" in pressure:
            assert pressure["vec"] <= 4, (
                f"VEC pressure is {pressure['vec']}, expected <= 4. "
                f"Check /app/runtime/pressure.py — should not accumulate across blocks"
            )

    def test_simd_pressure_reasonable(self, schedule_data):
        """SIMD pressure must be computed (requires class recognition first)."""
        pressure = schedule_data["pressure"]
        assert "simd" in pressure, (
            "SIMD class not present in pressure map — likely not recognized "
            "as a valid register class. Check allocator.ini register_classes parsing."
        )
        assert pressure["simd"] <= 4, (
            f"SIMD pressure is {pressure['simd']}, expected <= 4."
        )


class TestAllocationCorrectness:
    """Verify final allocation correctness combining all fixes."""

    def test_all_four_classes_have_register_allocs(self, allocation_data):
        """All four register classes must have at least one physical register allocation.
        
        This requires: correct class parsing (simd recognized), correct threshold
        (from allocator.constraints), and correct pressure (not accumulated).
        """
        allocations = allocation_data["allocations"]
        classes_with_registers = set()
        for vreg, alloc in allocations.items():
            if alloc["type"] == "register":
                classes_with_registers.add(alloc["register_class"])
        
        expected = {"gpr", "fpr", "vec", "simd"}
        missing = expected - classes_with_registers
        assert not missing, (
            f"Register classes without physical allocations: {missing}. "
            f"Requires correct class parsing, threshold, and pressure."
        )

    def test_simd_not_all_spilled(self, allocation_data):
        """SIMD allocations must not be entirely spilled to stack.
        
        With correct config parsing (stripping whitespace from comma-split),
        correct threshold (from allocator.constraints section), and correct
        pressure computation, SIMD instructions should receive physical registers.
        """
        allocations = allocation_data["allocations"]
        simd_regs = [v for v in allocations.values()
                     if v["register_class"] == "simd" and v["type"] == "register"]
        simd_spills = [v for v in allocations.values()
                       if v["register_class"] == "simd" and v["type"] == "spill"]
        assert len(simd_regs) >= len(simd_spills), (
            f"SIMD: {len(simd_regs)} registers vs {len(simd_spills)} spills. "
            f"Too many spills — check register class parsing and pressure."
        )

    def test_register_count_exceeds_minimum(self, allocation_data):
        """Total physical register allocations must exceed a minimum threshold."""
        assert allocation_data["register_count"] >= 20, (
            f"Only {allocation_data['register_count']} physical registers allocated, "
            f"expected at least 20. Multiple defects likely still present."
        )

"""
Verification tests for the register allocator output.

These tests check that the allocator engine, when run on properly repaired data,
produces correct register assignments with no conflicts, correct spill decisions,
and consistent graph properties.

Tests are organized by difficulty:
- Easy (4): Output files exist, basic structure
- Medium (4): No conflicts, no phantoms, edge counts, valid registers
- Hard (7): Specific assignments, exact spill count, full interference respect,
            live range consistency, coloring order properties, graph statistics
"""

import json
import os
import configparser
import pytest


# --- Helpers ---

def load_json(path):
    """Load a JSON file, return None if not found."""
    if not os.path.exists(path):
        return None
    with open(path, 'r') as f:
        return json.load(f)


def load_config():
    """Load the allocator configuration."""
    config = configparser.ConfigParser()
    config.read('/app/runtime/config.ini')
    return config


@pytest.fixture
def assignments():
    data = load_json('/output/assignments.json')
    assert data is not None, "assignments.json not found in /output/"
    return data


@pytest.fixture
def spill_report():
    data = load_json('/output/spill_report.json')
    assert data is not None, "spill_report.json not found in /output/"
    return data


@pytest.fixture
def diagnostics():
    data = load_json('/output/diagnostics.json')
    assert data is not None, "diagnostics.json not found in /output/"
    return data


@pytest.fixture
def interference_graph():
    data = load_json('/app/runtime/data/interference_graph.json')
    assert data is not None, "interference_graph.json not found"
    return data


@pytest.fixture
def live_ranges():
    data = load_json('/app/runtime/data/live_ranges.json')
    assert data is not None, "live_ranges.json not found"
    return data


@pytest.fixture
def config():
    return load_config()


# ============================================================
# EASY TESTS (4) - Basic output existence and structure
# ============================================================

class TestEasyOutputExistence:
    """Verify output files exist and have correct basic structure."""

    def test_assignments_file_exists(self):
        """assignments.json must exist in /output/"""
        assert os.path.exists('/output/assignments.json'), \
            "Output file /output/assignments.json does not exist"

    def test_spill_report_file_exists(self):
        """spill_report.json must exist in /output/"""
        assert os.path.exists('/output/spill_report.json'), \
            "Output file /output/spill_report.json does not exist"

    def test_assignments_has_required_keys(self, assignments):
        """assignments.json must have status, assignments, num_colored, num_spilled"""
        required_keys = ['status', 'assignments', 'num_colored', 'num_spilled', 'conflicts']
        for key in required_keys:
            assert key in assignments, f"Missing key '{key}' in assignments.json"

    def test_correct_number_of_virtual_registers(self, assignments, config):
        """Total colored + spilled must equal expected virtual register count."""
        expected = int(config.get('program', 'num_virtual_registers'))
        total = assignments['num_colored'] + assignments['num_spilled']
        assert total == expected, \
            f"Expected {expected} total registers, got {total} (colored={assignments['num_colored']}, spilled={assignments['num_spilled']})"


# ============================================================
# MEDIUM TESTS (4) - Correctness properties
# ============================================================

class TestMediumCorrectness:
    """Verify core correctness properties of the allocation."""

    def test_no_register_conflicts(self, assignments):
        """No two interfering registers should share the same physical register."""
        assert assignments['status'] == 'SUCCESS', \
            f"Allocator status is '{assignments['status']}', expected 'SUCCESS'"
        assert assignments['num_conflicts'] == 0, \
            f"Found {assignments['num_conflicts']} register conflicts"
        assert len(assignments['conflicts']) == 0, \
            f"Conflict details: {assignments['conflicts']}"

    def test_no_phantom_registers_in_output(self, assignments, live_ranges):
        """All registers in output must have corresponding live range data."""
        valid_vregs = set(entry['vreg'] for entry in live_ranges['ranges'])
        assigned_vregs = set(assignments['assignments'].keys())
        phantom_in_output = assigned_vregs - valid_vregs
        assert len(phantom_in_output) == 0, \
            f"Phantom registers found in output: {phantom_in_output}"

    def test_all_assignments_use_valid_physical_registers(self, assignments, config):
        """Every assignment must use a valid physical register from config."""
        valid_regs = set(config.get('registers', 'physical_registers').split(','))
        for vreg, preg in assignments['assignments'].items():
            assert preg in valid_regs, \
                f"{vreg} assigned to invalid register '{preg}'. Valid: {valid_regs}"

    def test_graph_node_count_matches_expected(self, interference_graph, config):
        """The repaired graph should have exactly the expected number of nodes."""
        expected = int(config.get('program', 'num_virtual_registers'))
        actual = len(interference_graph['nodes'])
        assert actual == expected, \
            f"Graph has {actual} nodes, expected {expected}. Phantom nodes may not have been removed."


# ============================================================
# HARD TESTS (7) - Deep correctness and consistency
# ============================================================

class TestHardDeepCorrectness:
    """Verify deep semantic correctness of the allocation."""

    def test_no_duplicate_edges_in_graph(self, interference_graph):
        """The repaired interference graph should have no duplicate edges."""
        edge_set = set()
        duplicates = []
        for edge in interference_graph['edges']:
            normalized = tuple(sorted([edge['from'], edge['to']]))
            if normalized in edge_set:
                duplicates.append(normalized)
            edge_set.add(normalized)
        assert len(duplicates) == 0, \
            f"Found {len(duplicates)} duplicate edges: {duplicates[:5]}..."

    def test_all_interferences_respected(self, assignments, interference_graph):
        """For every edge in the graph, the two endpoints must have different registers."""
        assign_map = assignments['assignments']
        violations = []
        for edge in interference_graph['edges']:
            u, v = edge['from'], edge['to']
            if u in assign_map and v in assign_map:
                if assign_map[u] == assign_map[v]:
                    violations.append((u, v, assign_map[u]))
        assert len(violations) == 0, \
            f"Found {len(violations)} interference violations: {violations[:5]}"

    def test_live_range_overlap_implies_different_registers(self, assignments, live_ranges):
        """
        Any two registers whose live ranges overlap must have different 
        physical register assignments (unless one is spilled).
        This tests the SEMANTIC correctness beyond just graph edges.
        """
        ranges = {r['vreg']: r for r in live_ranges['ranges']}
        assign_map = assignments['assignments']
        violations = []
        
        vregs = sorted(ranges.keys())
        for i in range(len(vregs)):
            for j in range(i + 1, len(vregs)):
                vi, vj = vregs[i], vregs[j]
                ri, rj = ranges[vi], ranges[vj]
                # Check overlap
                if (ri['start_instruction'] <= rj['end_instruction'] and
                    rj['start_instruction'] <= ri['end_instruction']):
                    # They overlap - must have different registers (if both assigned)
                    if vi in assign_map and vj in assign_map:
                        if assign_map[vi] == assign_map[vj]:
                            violations.append((vi, vj, assign_map[vi]))
        
        assert len(violations) == 0, \
            f"Found {len(violations)} live-range overlap violations: {violations[:5]}"

    def test_no_live_ranges_exceed_max_instruction(self, live_ranges, config):
        """No live range should have end_instruction exceeding max_instruction_index."""
        max_idx = int(config.get('program', 'max_instruction_index'))
        violations = []
        for entry in live_ranges['ranges']:
            if entry['end_instruction'] > max_idx:
                violations.append(
                    f"{entry['vreg']}: end={entry['end_instruction']} > max={max_idx}"
                )
        assert len(violations) == 0, \
            f"Live ranges exceed max instruction index: {violations}"

    def test_exact_spill_count(self, assignments):
        """
        With correct data and 8 physical registers, the DSatur algorithm
        on this specific graph should produce exactly 0 spills.
        """
        assert assignments['num_spilled'] == 0, \
            f"Expected 0 spills, got {assignments['num_spilled']}"

    def test_edge_count_matches_expected(self, interference_graph):
        """
        The repaired graph should have exactly 110 edges (the correct count
        after removing duplicates, adding missing edges, removing phantom edges).
        """
        actual_edges = len(interference_graph['edges'])
        assert actual_edges == 110, \
            f"Expected 110 edges in repaired graph, got {actual_edges}"

    def test_register_class_constraints_respected(self, assignments):
        """
        Registers with class constraints must be assigned within their allowed set.
        v2, v10, v17, v22 -> r0-r5 only
        v5, v15, v25 -> r2-r7 only
        """
        assign_map = assignments['assignments']
        
        constrained_r0_r5 = {'v2', 'v10', 'v17', 'v22'}
        allowed_r0_r5 = {'r0', 'r1', 'r2', 'r3', 'r4', 'r5'}
        
        constrained_r2_r7 = {'v5', 'v15', 'v25'}
        allowed_r2_r7 = {'r2', 'r3', 'r4', 'r5', 'r6', 'r7'}
        
        violations = []
        for vreg in constrained_r0_r5:
            if vreg in assign_map and assign_map[vreg] not in allowed_r0_r5:
                violations.append(f"{vreg} assigned {assign_map[vreg]}, must be in {allowed_r0_r5}")
        
        for vreg in constrained_r2_r7:
            if vreg in assign_map and assign_map[vreg] not in allowed_r2_r7:
                violations.append(f"{vreg} assigned {assign_map[vreg]}, must be in {allowed_r2_r7}")
        
        assert len(violations) == 0, \
            f"Register class violations: {violations}"

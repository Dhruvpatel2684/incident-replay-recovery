"""Tests for the Graph Reachability Analysis Engine.

Validates edge filtering, reachability computation, path scoring,
and level summaries across all network topologies.
"""
import json
import os

import pytest


REACH_PATH = "/app/runtime/output/reachability.json"
SCORE_PATH = "/app/runtime/output/scores.json"


@pytest.fixture
def reach_data():
    """Load reachability output."""
    assert os.path.exists(REACH_PATH), f"Output not found at {REACH_PATH}"
    with open(REACH_PATH, "r") as f:
        return json.load(f)


@pytest.fixture
def score_data():
    """Load scoring output."""
    assert os.path.exists(SCORE_PATH), f"Output not found at {SCORE_PATH}"
    with open(SCORE_PATH, "r") as f:
        return json.load(f)


# ============================================================
# Structure tests (always pass)
# ============================================================

class TestOutputStructure:
    """Verify output files have valid structure."""

    def test_reachability_file_exists(self, reach_data):
        """Reachability output must exist."""
        assert reach_data is not None

    def test_scores_file_exists(self, score_data):
        """Scores output must exist."""
        assert score_data is not None

    def test_reachability_has_fields(self, reach_data):
        """Reachability output must have required fields."""
        for field in ["total_nodes", "total_edges", "total_reachable_pairs",
                      "active_link_types", "reachability_map"]:
            assert field in reach_data, f"Missing: {field}"

    def test_scores_has_fields(self, score_data):
        """Scores output must have required fields."""
        for field in ["node_scores", "level_summaries", "total_scored_sources"]:
            assert field in score_data, f"Missing: {field}"

    def test_reachability_map_has_nodes(self, reach_data):
        """Reachability map must contain entries for multiple nodes."""
        assert len(reach_data["reachability_map"]) >= 10

    def test_all_sources_scored(self, score_data):
        """All source nodes must have score entries."""
        assert score_data["total_scored_sources"] >= 10


# ============================================================
# Edge filtering tests (require Bug A fix)
# ============================================================

class TestEdgeFiltering:
    """Verify all link types are processed."""

    def test_total_edge_count(self, reach_data):
        """Must process exactly 42 edges (all 4 link types active)."""
        assert reach_data["total_edges"] == 42, (
            f"Expected 42 edges, got {reach_data['total_edges']}"
        )

    def test_four_link_types_active(self, reach_data):
        """All four link types must be active."""
        expected = ["direct", "mesh", "relay", "tunnel"]
        assert sorted(reach_data["active_link_types"]) == expected, (
            f"Expected {expected}, got {sorted(reach_data['active_link_types'])}"
        )

    def test_total_reachable_pairs(self, reach_data):
        """Total reachable pairs must be 122."""
        assert reach_data["total_reachable_pairs"] == 122, (
            f"Expected 122, got {reach_data['total_reachable_pairs']}"
        )


# ============================================================
# Hop limit tests (require Bug B fix)
# ============================================================

class TestHopLimit:
    """Verify correct hop limit is applied."""

    def test_node_a_reachable_count(self, reach_data):
        """Node A must reach exactly 13 other nodes within 3 hops."""
        a_data = reach_data["reachability_map"]["A"]
        assert a_data["reachable_count"] == 13, (
            f"A reachable_count: expected 13, got {a_data['reachable_count']}"
        )

    def test_node_a_max_depth(self, reach_data):
        """Node A maximum reachability depth must be 3."""
        a_data = reach_data["reachability_map"]["A"]
        assert a_data["max_depth"] == 3, (
            f"A max_depth: expected 3, got {a_data['max_depth']}"
        )

    def test_node_e_reachable_count(self, reach_data):
        """Node E must reach exactly 10 nodes (mesh links create shortcuts)."""
        e_data = reach_data["reachability_map"]["E"]
        assert e_data["reachable_count"] == 10, (
            f"E reachable_count: expected 10, got {e_data['reachable_count']}"
        )

    def test_node_a_depth_1_nodes(self, reach_data):
        """Node A must have B, C, D, F, K at depth 1."""
        a_nodes = reach_data["reachability_map"]["A"]["nodes"]
        depth_1 = sorted(k for k, v in a_nodes.items() if v == 1)
        expected = ["B", "C", "D", "F", "K"]
        assert depth_1 == expected, (
            f"A depth-1 nodes: expected {expected}, got {depth_1}"
        )


# ============================================================
# Level score tests (require Bug C fix)
# ============================================================

class TestLevelScores:
    """Verify per-level scoring computation."""

    def test_level_1_score_from_a(self, score_data):
        """Level 1 score from A must be 335.0."""
        levels = score_data["level_summaries"].get("A", {})
        assert levels.get("1") == 335.0, (
            f"A level 1: expected 335.0, got {levels.get('1')}"
        )

    def test_level_2_score_from_a(self, score_data):
        """Level 2 score from A must be 226.5 (not accumulated)."""
        levels = score_data["level_summaries"].get("A", {})
        assert levels.get("2") == 226.5, (
            f"A level 2: expected 226.5, got {levels.get('2')}"
        )

    def test_level_3_score_from_a(self, score_data):
        """Level 3 score from A must be 27.3."""
        levels = score_data["level_summaries"].get("A", {})
        assert levels.get("3") == 27.3, (
            f"A level 3: expected 27.3, got {levels.get('3')}"
        )

    def test_sum_all_level_1(self, score_data):
        """Sum of all level-1 scores across sources must be 2675.0."""
        total = sum(
            ls.get("1", 0) for ls in score_data["level_summaries"].values()
        )
        assert round(total, 1) == 2675.0, (
            f"Sum level 1: expected 2675.0, got {round(total, 1)}"
        )


# ============================================================
# Node score tests (require multiple fixes)
# ============================================================

class TestNodeScores:
    """Verify individual node path scores."""

    def test_score_a_to_b(self, score_data):
        """Path score A->B must be 90.0."""
        assert score_data["node_scores"]["A"]["B"] == 90.0

    def test_score_a_to_k(self, score_data):
        """Path score A->K must be 70.0."""
        assert score_data["node_scores"]["A"]["K"] == 70.0

    def test_score_a_to_j(self, score_data):
        """Path score A->J must be 19.0 (via mesh shortcut at depth 2)."""
        assert score_data["node_scores"]["A"]["J"] == 19.0, (
            f"A->J: expected 19.0, got {score_data['node_scores']['A'].get('J')}"
        )

    def test_score_a_to_m(self, score_data):
        """Path score A->M must be 27.3 (depth 3 with normalization)."""
        assert score_data["node_scores"]["A"]["M"] == 27.3, (
            f"A->M: expected 27.3, got {score_data['node_scores']['A'].get('M')}"
        )


# ============================================================
# Sort determinism tests (require Bug D fix)
# ============================================================

class TestSortDeterminism:
    """Verify deterministic edge ordering."""

    def test_total_nodes(self, reach_data):
        """Graph must contain exactly 14 nodes."""
        assert reach_data["total_nodes"] == 14

    def test_node_j_reachable_from_a_at_depth_2(self, reach_data):
        """Node J must be reachable from A at depth 2 (mesh shortcut)."""
        a_nodes = reach_data["reachability_map"]["A"]["nodes"]
        assert a_nodes.get("J") == 2, (
            f"A->J depth: expected 2, got {a_nodes.get('J')}"
        )

    def test_scored_sources_count(self, score_data):
        """Must have scores for exactly 14 source nodes."""
        assert score_data["total_scored_sources"] == 14, (
            f"Expected 14 scored sources, got {score_data['total_scored_sources']}"
        )

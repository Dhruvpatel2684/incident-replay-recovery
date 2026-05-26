"""Tests for the Geospatial Event Correlation Engine.

Validates spatial indexing accuracy, temporal correlation scores,
cluster formation, and event stream ordering.
"""
import json
import os

import pytest


INDEX_PATH = "/app/runtime/output/spatial_index.json"
CORR_PATH = "/app/runtime/output/correlation.json"


@pytest.fixture
def index_data():
    """Load spatial index output."""
    assert os.path.exists(INDEX_PATH), (
        f"Spatial index output not found at {INDEX_PATH}"
    )
    with open(INDEX_PATH, "r") as f:
        return json.load(f)


@pytest.fixture
def correlation_data():
    """Load correlation output."""
    assert os.path.exists(CORR_PATH), (
        f"Correlation output not found at {CORR_PATH}"
    )
    with open(CORR_PATH, "r") as f:
        return json.load(f)


# ============================================================
# Structure tests (easy — always pass with buggy code)
# ============================================================

class TestOutputStructure:
    """Verify output files have valid structure."""

    def test_index_file_exists(self, index_data):
        """Spatial index output must exist."""
        assert index_data is not None

    def test_correlation_file_exists(self, correlation_data):
        """Correlation output must exist."""
        assert correlation_data is not None

    def test_index_has_required_fields(self, index_data):
        """Spatial index must have all required fields."""
        for field in ["total_events", "active_zones", "cell_count", "cell_assignments"]:
            assert field in index_data, f"Missing field: {field}"

    def test_correlation_has_required_fields(self, correlation_data):
        """Correlation output must have all required fields."""
        for field in ["window_scores", "clusters", "total_clusters", "total_correlated_events"]:
            assert field in correlation_data, f"Missing field: {field}"

    def test_clusters_have_required_fields(self, correlation_data):
        """Each cluster must contain required attributes."""
        required = ["anchor_zone", "anchor_timestamp", "cell", "event_count",
                    "raw_score", "adjusted_score"]
        for cluster in correlation_data["clusters"]:
            for field in required:
                assert field in cluster, f"Cluster missing field: {field}"

    def test_cell_assignments_are_pairs(self, index_data):
        """Cell assignments must be [x, y] coordinate pairs."""
        for key, cell in index_data["cell_assignments"].items():
            assert isinstance(cell, list) and len(cell) == 2, (
                f"Cell assignment for {key} is not a valid [x, y] pair"
            )


# ============================================================
# Zone coverage tests (require Bug A fix)
# ============================================================

class TestZoneCoverage:
    """Verify all configured zones contribute events."""

    def test_total_event_count(self, index_data):
        """Total ingested events must equal 58 (all four zones)."""
        assert index_data["total_events"] == 58, (
            f"Expected 58 total events, got {index_data['total_events']}"
        )

    def test_all_four_zones_active(self, index_data):
        """All four zones must appear in active_zones list."""
        expected = ["east", "north", "south", "west"]
        assert sorted(index_data["active_zones"]) == expected, (
            f"Expected zones {expected}, got {sorted(index_data['active_zones'])}"
        )

    def test_west_zone_events_present(self, index_data):
        """Events from west zone must appear in cell assignments."""
        west_keys = [k for k in index_data["cell_assignments"] if k.startswith("west_")]
        assert len(west_keys) == 14, (
            f"Expected 14 west zone events, found {len(west_keys)}"
        )


# ============================================================
# Spatial indexing tests (require Bug B fix)
# ============================================================

class TestSpatialIndexing:
    """Verify grid cell assignments for negative coordinates."""

    def test_cell_count(self, index_data):
        """Spatial grid must contain exactly 11 occupied cells."""
        assert index_data["cell_count"] == 11, (
            f"Expected 11 cells, got {index_data['cell_count']}"
        )

    def test_negative_coord_cell_north(self, index_data):
        """Event north_6 at (-3.2, 15.6) must map to cell [-1, 1]."""
        cell = index_data["cell_assignments"].get("north_6")
        assert cell == [-1, 1], (
            f"north_6 at (-3.2, 15.6): expected cell [-1, 1], got {cell}"
        )

    def test_negative_coord_cell_south(self, index_data):
        """Event south_2 at (-7.6, -12.4) must map to cell [-1, -2]."""
        cell = index_data["cell_assignments"].get("south_2")
        assert cell == [-1, -2], (
            f"south_2 at (-7.6, -12.4): expected cell [-1, -2], got {cell}"
        )

    def test_negative_coord_cell_west(self, index_data):
        """Event west_0 at (-18.3, 2.5) must map to cell [-2, 0]."""
        cell = index_data["cell_assignments"].get("west_0")
        assert cell == [-2, 0], (
            f"west_0 at (-18.3, 2.5): expected cell [-2, 0], got {cell}"
        )


# ============================================================
# Window score tests (require Bug C fix + interactions)
# ============================================================

class TestWindowScores:
    """Verify temporal correlation window scores."""

    def test_window_count(self, correlation_data):
        """Must produce exactly 7 scored windows."""
        assert len(correlation_data["window_scores"]) == 7, (
            f"Expected 7 windows, got {len(correlation_data['window_scores'])}"
        )

    def test_window_0_score(self, correlation_data):
        """First window score must equal 16.9."""
        score = correlation_data["window_scores"].get("0")
        assert score == 16.9, (
            f"Window 0 score: expected 16.9, got {score}"
        )

    def test_window_2_score(self, correlation_data):
        """Window 2 score must equal 33.1."""
        score = correlation_data["window_scores"].get("2")
        assert score == 33.1, (
            f"Window 2 score: expected 33.1, got {score}"
        )

    def test_total_window_score_sum(self, correlation_data):
        """Sum of all window scores must equal 193.5."""
        total = sum(correlation_data["window_scores"].values())
        assert round(total, 1) == 193.5, (
            f"Total window score sum: expected 193.5, got {round(total, 1)}"
        )


# ============================================================
# Cluster tests (require multiple bug fixes)
# ============================================================

class TestClusters:
    """Verify cluster formation and scoring."""

    def test_total_cluster_count(self, correlation_data):
        """Must produce exactly 13 clusters."""
        assert correlation_data["total_clusters"] == 13, (
            f"Expected 13 clusters, got {correlation_data['total_clusters']}"
        )

    def test_all_events_correlated(self, correlation_data):
        """All 58 events must be assigned to clusters."""
        assert correlation_data["total_correlated_events"] == 58, (
            f"Expected 58 correlated events, got {correlation_data['total_correlated_events']}"
        )

    def test_first_cluster_anchor(self, correlation_data):
        """First cluster must be anchored at north zone, timestamp 1000."""
        first = correlation_data["clusters"][0]
        assert first["anchor_zone"] == "north", (
            f"First cluster anchor_zone: expected 'north', got '{first['anchor_zone']}'"
        )
        assert first["anchor_timestamp"] == 1000, (
            f"First cluster anchor_timestamp: expected 1000, got {first['anchor_timestamp']}"
        )

    def test_first_cluster_size(self, correlation_data):
        """First cluster must contain exactly 9 events."""
        first = correlation_data["clusters"][0]
        assert first["event_count"] == 9, (
            f"First cluster event_count: expected 9, got {first['event_count']}"
        )

    def test_first_cluster_raw_score(self, correlation_data):
        """First cluster raw score must be 35.1."""
        first = correlation_data["clusters"][0]
        assert first["raw_score"] == 35.1, (
            f"First cluster raw_score: expected 35.1, got {first['raw_score']}"
        )

    def test_sum_raw_scores(self, correlation_data):
        """Sum of all cluster raw scores must be 233.5."""
        total = sum(c["raw_score"] for c in correlation_data["clusters"])
        assert round(total, 1) == 233.5, (
            f"Sum of raw scores: expected 233.5, got {round(total, 1)}"
        )


# ============================================================
# Event ordering tests (require Bug D fix)
# ============================================================

class TestEventOrdering:
    """Verify deterministic event merge ordering."""

    def test_timestamp_1100_order(self, correlation_data):
        """Events at timestamp 1100 must follow zone_id ordering.

        Multiple zones emit events at the same timestamp. The merge
        must produce deterministic ordering using zone_id as tiebreaker.
        """
        clusters = correlation_data["clusters"]
        # The cluster anchored at north@1100 depends on correct ordering
        north_1100 = [c for c in clusters
                      if c["anchor_zone"] == "north" and c["anchor_timestamp"] == 1100]
        assert len(north_1100) == 1, (
            f"Expected exactly 1 cluster anchored at north@1100, found {len(north_1100)}"
        )
        # With correct ordering, this cluster has 6 events
        assert north_1100[0]["event_count"] == 6, (
            f"Cluster north@1100 event_count: expected 6, got {north_1100[0]['event_count']}"
        )

    def test_ordering_affects_cluster_score(self, correlation_data):
        """Cluster at north@1100 adjusted score must be 1.71."""
        clusters = correlation_data["clusters"]
        north_1100 = [c for c in clusters
                      if c["anchor_zone"] == "north" and c["anchor_timestamp"] == 1100]
        assert len(north_1100) == 1
        assert north_1100[0]["adjusted_score"] == 1.71, (
            f"north@1100 adjusted_score: expected 1.71, got {north_1100[0]['adjusted_score']}"
        )

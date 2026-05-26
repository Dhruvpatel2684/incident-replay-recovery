"""
Test suite for cache eviction system.

Validates correctness of the eviction analysis by checking
computed output files against expected behavioral invariants.
"""
import json
import os

OUTPUT_DIR = "/app/runtime/output"
RANKING_PATH = os.path.join(OUTPUT_DIR, "eviction_ranking.json")
SUMMARY_PATH = os.path.join(OUTPUT_DIR, "eviction_summary.json")


def load_ranking():
    """Load eviction ranking from output."""
    with open(RANKING_PATH, "r") as f:
        return json.load(f)


def load_summary():
    """Load eviction summary from output."""
    with open(SUMMARY_PATH, "r") as f:
        return json.load(f)


# === BASIC TESTS ===


def test_output_files_created():
    """Verify output files exist after system execution."""
    assert os.path.isfile(RANKING_PATH), (
        f"Expected output file not found: {RANKING_PATH}"
    )
    assert os.path.isfile(SUMMARY_PATH), (
        f"Expected output file not found: {SUMMARY_PATH}"
    )


def test_ranking_entry_schema():
    """Verify each ranking entry contains all required fields."""
    ranking = load_ranking()
    assert isinstance(ranking, list), "Ranking must be a JSON array"
    assert len(ranking) > 0, "Ranking must contain at least one entry"
    required = {"entry_id", "tier_id", "key", "access_time",
                "access_count", "size_bytes", "eviction_score",
                "staleness_sec", "eviction_rank"}
    for entry in ranking:
        missing = required - set(entry.keys())
        assert not missing, f"Entry missing fields: {missing}"


def test_summary_schema():
    """Verify summary contains required structure."""
    summary = load_summary()
    assert "eviction_stats" in summary
    assert "total_candidates" in summary
    assert "total_entries_loaded" in summary
    stats = summary["eviction_stats"]
    assert "total_processed" in stats
    assert "windows_processed" in stats
    assert "hit_rate" in stats
    assert "peak_eviction_score" in stats
    assert "eviction_params" in stats
    assert "active_tiers" in stats


def test_eviction_ranks_sequential():
    """Verify eviction_rank values form a zero-indexed sequence."""
    ranking = load_ranking()
    ranks = [e["eviction_rank"] for e in ranking]
    expected = list(range(len(ranking)))
    assert ranks == expected, (
        "Eviction ranks must be sequential starting from 0"
    )


# === MEDIUM TESTS ===


def test_all_tier_feeds_loaded():
    """Verify entries from all active tier feeds are processed.

    The system has 3 data feeds (hot: 20, warm: 22, archive: 18).
    All active feeds must contribute entries to the analysis.
    """
    summary = load_summary()
    total = summary["total_entries_loaded"]
    assert total == 60, (
        f"Expected 60 entries from all tier feeds, got {total}. "
        "Some tier data may not be loading correctly."
    )


def test_staleness_threshold_appropriate():
    """Verify the eviction engine uses appropriate staleness parameters.

    With correct parameters, a significant portion of entries should
    be flagged as eviction candidates based on their access recency.
    """
    summary = load_summary()
    candidates = summary["total_candidates"]
    total = summary["total_entries_loaded"]
    ratio = candidates / total if total > 0 else 0
    assert candidates >= 30, (
        f"Expected at least 30 eviction candidates, got {candidates}. "
        "The staleness threshold may be too permissive."
    )
    assert ratio >= 0.4, (
        f"Candidate ratio {ratio:.2f} is too low. "
        "Expected at least 40% of entries to exceed staleness threshold."
    )


def test_peak_eviction_score_bounded():
    """Verify peak_eviction_score represents a single-window maximum.

    The peak score should reflect the highest individual eviction
    score seen in any single processing window, not an aggregate.
    """
    summary = load_summary()
    peak = summary["eviction_stats"]["peak_eviction_score"]
    assert peak < 1000.0, (
        f"peak_eviction_score={peak} exceeds reasonable bounds. "
        "This metric should represent the maximum score from one "
        "processing window, not a sum across windows."
    )
    assert peak > 100.0, (
        f"peak_eviction_score={peak} is suspiciously low."
    )


# === HARD TESTS ===


def test_ranking_order_deterministic():
    """Verify ranking uses stable ordering with tier-aware tiebreaking.

    Entries with the same access_time must be ordered deterministically
    using tier_id as secondary key (alphabetical) and entry_id as
    tertiary key within the same tier.
    """
    ranking = load_ranking()
    for i in range(len(ranking) - 1):
        curr = ranking[i]
        nxt = ranking[i + 1]
        key_curr = (curr["access_time"], curr["tier_id"], curr["entry_id"])
        key_nxt = (nxt["access_time"], nxt["tier_id"], nxt["entry_id"])
        assert key_curr <= key_nxt, (
            f"Ranking order violation at position {i}: "
            f"({curr['access_time']}, {curr['tier_id']}, {curr['entry_id']}) "
            f"should precede "
            f"({nxt['access_time']}, {nxt['tier_id']}, {nxt['entry_id']}). "
            "Entries with same access_time need tier-aware tiebreaking."
        )


def test_archive_tier_candidates_present():
    """Verify archive tier entries appear in the eviction ranking.

    The archive tier contains 18 entries that should all be evaluated.
    Most archive entries are significantly stale and should appear
    as eviction candidates in the ranking output.
    """
    ranking = load_ranking()
    archive_entries = [e for e in ranking if e["tier_id"] == "archive"]
    assert len(archive_entries) >= 15, (
        f"Expected at least 15 archive tier entries in ranking, "
        f"got {len(archive_entries)}. Archive data may not be loading."
    )


def test_complete_system_correctness():
    """Verify the full system produces consistent results.

    Checks multiple aspects of system correctness simultaneously:
    - Correct entry count from all feeds
    - Appropriate candidate count given staleness parameters
    - Bounded peak score (single-window max)
    - Archive entries present in ranking
    - Deterministic ordering across tiers
    """
    summary = load_summary()
    ranking = load_ranking()

    assert summary["total_entries_loaded"] == 60, (
        f"Expected 60 entries, got {summary['total_entries_loaded']}"
    )

    assert summary["total_candidates"] >= 30, (
        f"Expected >= 30 candidates, got {summary['total_candidates']}"
    )

    peak = summary["eviction_stats"]["peak_eviction_score"]
    assert 100.0 < peak < 1000.0, (
        f"peak_eviction_score={peak} outside valid range (100, 1000)"
    )

    tiers_in_ranking = set(e["tier_id"] for e in ranking)
    assert "archive" in tiers_in_ranking, (
        "Archive tier entries missing from ranking"
    )
    assert "warm" in tiers_in_ranking, (
        "Warm tier entries missing from ranking"
    )

    same_time_groups = {}
    for e in ranking:
        same_time_groups.setdefault(e["access_time"], []).append(e)
    for time_key, group in same_time_groups.items():
        if len(group) > 1:
            tier_ids = [g["tier_id"] for g in group]
            assert tier_ids == sorted(tier_ids), (
                f"Entries at {time_key} not ordered by tier_id: {tier_ids}"
            )

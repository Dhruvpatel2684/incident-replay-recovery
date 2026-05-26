"""
Test suite for the document layout engine output.

Tests are organized by difficulty:
- Easy (test_01 through test_04): File existence and basic structure
- Medium (test_05 through test_07): Require 1-2 bug fixes
- Hard (test_08 through test_15): Require 3-4 bug fixes together
"""

import json
import os
import pytest


LAYOUT_RESULT_PATH = "/app/runtime/output/layout_result.json"
PAGE_METRICS_PATH = "/app/runtime/output/page_metrics.json"


@pytest.fixture
def layout_result():
    with open(LAYOUT_RESULT_PATH, 'r') as f:
        return json.load(f)


@pytest.fixture
def page_metrics():
    with open(PAGE_METRICS_PATH, 'r') as f:
        return json.load(f)


# =============================================================================
# EASY TESTS - File existence and basic structure
# =============================================================================

class TestEasyFileExistence:
    """Basic tests that output files exist and have correct structure."""

    def test_01_layout_result_exists(self):
        """layout_result.json must exist."""
        assert os.path.exists(LAYOUT_RESULT_PATH), \
            f"Expected output file at {LAYOUT_RESULT_PATH}"

    def test_02_page_metrics_exists(self):
        """page_metrics.json must exist."""
        assert os.path.exists(PAGE_METRICS_PATH), \
            f"Expected output file at {PAGE_METRICS_PATH}"

    def test_03_layout_result_structure(self, layout_result):
        """layout_result.json must contain required top-level keys."""
        required_keys = [
            "total_paragraphs", "total_pages", "line_width",
            "page_height", "allowed_modes", "optimal_breaks",
            "paragraphs_processed"
        ]
        for key in required_keys:
            assert key in layout_result, f"Missing required key: {key}"

    def test_04_page_metrics_structure(self, page_metrics):
        """page_metrics.json must be a list with correct entry structure."""
        assert isinstance(page_metrics, list)
        assert len(page_metrics) > 0
        required_keys = [
            "page_number", "line_count", "paragraph_count",
            "fill_ratio", "avg_line_length", "penalty_total",
            "quality_score"
        ]
        for key in required_keys:
            assert key in page_metrics[0], f"Missing key in page metrics: {key}"


# =============================================================================
# MEDIUM TESTS - Require 1-2 fixes
# =============================================================================

class TestMediumSingleFixes:
    """Tests that require fixing one or two bugs to pass."""

    def test_05_correct_line_width(self, layout_result):
        """
        Line width must be 65 (from [layout.typeset] section).
        Requires fixing Bug 2: wrong config section.
        """
        assert layout_result["line_width"] == 65, \
            f"Expected line_width=65 (from [layout.typeset]), got {layout_result['line_width']}"

    def test_06_all_modes_recognized(self, layout_result):
        """
        All four modes must be present in allowed_modes.
        Requires fixing Bug 1: space in comma-split list.
        """
        expected_modes = ["centered", "hyphenated", "justified", "ragged-right"]
        assert layout_result["allowed_modes"] == expected_modes, \
            f"Expected modes {expected_modes}, got {layout_result['allowed_modes']}"

    def test_07_hyphenated_paragraphs_retain_mode(self, layout_result):
        """
        Paragraphs with mode 'hyphenated' must keep their mode.
        Requires fixing Bug 1: hyphenated mode not in allowed set.
        """
        hyphenated_paras = [
            p for p in layout_result["paragraphs_processed"]
            if p["id"] in ("c1p10", "c2p12", "c3p05")
        ]
        for para in hyphenated_paras:
            assert para["mode"] == "hyphenated", \
                f"Paragraph {para['id']} should have mode 'hyphenated', got '{para['mode']}'"


# =============================================================================
# HARD TESTS - Require 3-4 fixes together
# =============================================================================

class TestHardMultipleFixes:
    """Tests that require fixing multiple bugs simultaneously."""

    def test_08_page_penalty_is_last_paragraph(self, layout_result, page_metrics):
        """
        Each page's penalty_total must equal only the last paragraph's penalty
        on that page, not a cumulative sum.
        Requires Bug 3 fix (accumulation -> assignment).
        """
        # With correct behavior, penalty_total reflects a single paragraph's
        # penalty (the last one on the page), which should be modest.
        # Accumulated penalties across 6-8 paragraphs will exceed this.
        for page in page_metrics:
            assert page["penalty_total"] <= 6.0, \
                f"Page {page['page_number']} penalty_total={page['penalty_total']} " \
                f"exceeds single-paragraph maximum of 6.0 (likely accumulating)"

    def test_09_total_pages_and_paragraphs(self, layout_result):
        """
        All 60 paragraphs must be processed and page count must reflect
        correct line width (more lines per paragraph at width=65 = more pages).
        Requires Bug 2 fix.
        """
        assert layout_result["total_paragraphs"] == 60, \
            f"Expected 60 paragraphs, got {layout_result['total_paragraphs']}"
        # At width=65, paragraphs are longer (more lines), producing 9 pages
        # At width=80 (buggy), only 8 pages are produced
        assert layout_result["total_pages"] == 9, \
            f"Expected 9 pages at width=65, got {layout_result['total_pages']}"

    def test_10_deterministic_break_ordering(self, layout_result):
        """
        Optimal breaks must be sorted by (penalty, paragraph_id, position).
        Requires Bug 4 fix: sort tiebreaker.
        """
        breaks = layout_result["optimal_breaks"]
        if len(breaks) < 2:
            pytest.skip("Not enough break candidates to verify ordering")

        for i in range(len(breaks) - 1):
            curr = breaks[i]
            nxt = breaks[i + 1]
            curr_key = (curr["penalty"], curr["paragraph_id"], curr["position"])
            nxt_key = (nxt["penalty"], nxt["paragraph_id"], nxt["position"])
            assert curr_key <= nxt_key, \
                f"Break candidates not sorted correctly at index {i}: {curr_key} > {nxt_key}"

    def test_11_line_width_affects_line_count(self, layout_result):
        """
        With line_width=65, paragraphs produce more lines than with width=80.
        A specific paragraph should have predictable line count at width 65.
        Requires Bug 2 fix.
        """
        # c1p01 text is ~193 chars, at width 65 should be 4 lines (not 3 at width 80)
        para = next(
            p for p in layout_result["paragraphs_processed"]
            if p["id"] == "c1p01"
        )
        assert para["line_count"] == 4, \
            f"Paragraph c1p01 should have exactly 4 lines at width 65, got {para['line_count']}"

    def test_12_quality_scores_with_correct_penalty(self, page_metrics):
        """
        Quality scores must reflect non-accumulated penalties.
        quality = max(0, 100 - penalty_total) * fill_ratio
        With correct (non-accumulated) penalties, quality should be high.
        Requires Bug 2 + Bug 3 fixes.
        """
        # With width=65 and non-accumulated penalties, all full pages
        # should have quality > 90 (since individual penalties are small)
        full_pages = [p for p in page_metrics if p["fill_ratio"] >= 0.95]
        high_quality = [p for p in full_pages if p["quality_score"] > 90.0]
        ratio = len(high_quality) / len(full_pages) if full_pages else 0
        assert ratio >= 0.75, \
            f"Only {ratio:.0%} of full pages have quality > 90. " \
            f"Expected >= 75% with non-accumulated penalties at width=65."

    def test_13_avg_line_length_matches_width(self, page_metrics):
        """
        Average line length should be proportional to width=65 for justified text.
        At width 65, justified lines average around 53-58 characters.
        Requires Bug 2 fix (correct line width).
        """
        # With correct width=65, average line length should be under 60
        for page in page_metrics:
            if page["line_count"] >= 10:
                assert page["avg_line_length"] <= 60, \
                    f"Page {page['page_number']} avg_line_length={page['avg_line_length']} " \
                    f"exceeds expected range for width=65 (should be <= 60)"

    def test_14_combined_mode_and_width(self, layout_result):
        """
        Hyphenated paragraphs must retain their mode AND use correct width.
        Requires Bug 1 + Bug 2 fixes together.
        """
        para = next(
            p for p in layout_result["paragraphs_processed"]
            if p["id"] == "c1p10"
        )
        assert para["mode"] == "hyphenated", \
            f"c1p10 mode should be 'hyphenated', got '{para['mode']}'"
        # At width 65, this paragraph should produce specific line count
        assert para["line_count"] >= 3, \
            f"c1p10 should have >= 3 lines at width=65 in hyphenated mode"

    def test_15_full_system_consistency(self, layout_result, page_metrics):
        """
        Full system validation: correct width, all modes, proper penalties,
        deterministic ordering. Requires all 4 fixes.
        """
        # Check line width
        assert layout_result["line_width"] == 65

        # Check all modes present
        assert "hyphenated" in layout_result["allowed_modes"]
        assert len(layout_result["allowed_modes"]) == 4

        # Check penalties are reasonable (not accumulated)
        max_penalty = max(p["penalty_total"] for p in page_metrics)
        assert max_penalty <= 6.0, \
            f"Max page penalty {max_penalty} suggests accumulation bug"

        # Check break ordering is deterministic
        breaks = layout_result["optimal_breaks"]
        for i in range(len(breaks) - 1):
            curr = breaks[i]
            nxt = breaks[i + 1]
            curr_key = (curr["penalty"], curr["paragraph_id"], curr["position"])
            nxt_key = (nxt["penalty"], nxt["paragraph_id"], nxt["position"])
            assert curr_key <= nxt_key

        # Check no hyphenated paragraphs fell back to default
        hyph_paras = [
            p for p in layout_result["paragraphs_processed"]
            if p["id"] in ("c1p10", "c2p12", "c3p05")
        ]
        for p in hyph_paras:
            assert p["mode"] == "hyphenated"

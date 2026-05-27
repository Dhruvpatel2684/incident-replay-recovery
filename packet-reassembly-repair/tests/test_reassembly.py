"""
Test suite for packet fragment reassembly system.
"""
import json
import os

OUTPUT_DIR = "/app/runtime/output"
RESULTS_PATH = os.path.join(OUTPUT_DIR, "reassembly_results.json")
SUMMARY_PATH = os.path.join(OUTPUT_DIR, "reassembly_summary.json")


def load_results():
    with open(RESULTS_PATH) as f:
        return json.load(f)

def load_summary():
    with open(SUMMARY_PATH) as f:
        return json.load(f)

def get_stream(results, stream_id):
    return next(r for r in results if r["stream_id"] == stream_id)


# === BASIC TESTS ===

def test_output_files_exist():
    """Verify output files are created."""
    assert os.path.isfile(RESULTS_PATH)
    assert os.path.isfile(SUMMARY_PATH)

def test_all_streams_processed():
    """Verify all 3 streams were processed."""
    summary = load_summary()
    assert summary["streams_processed"] == 3

def test_result_structure():
    """Verify each result has required fields."""
    results = load_results()
    for r in results:
        assert "stream_id" in r
        assert "fragments_received" in r
        assert "overlaps_detected" in r
        assert "reassembly_result" in r
        assert "checksum" in r
        assert "checksum_valid" in r

# === MEDIUM TESTS ===

def test_all_streams_reassemble_successfully():
    """All 3 streams must reassemble without gaps.

    Beta stream has overlapping fragments but should still
    reassemble completely if the datagram length is computed
    correctly from fragment extents.
    """
    summary = load_summary()
    assert summary["success_rate"] == 1.0, (
        f"Expected 100% success rate, got {summary['success_rate']}. "
        "Check how total datagram length is computed from fragments."
    )
    assert summary["failed_reassemblies"] == 0

def test_beta_stream_correct_length():
    """Beta stream datagram length must be 28 bytes.

    The fragments span offsets 0-28. Total length should be
    max(offset + length) across all fragments, NOT the sum
    of individual fragment lengths.
    """
    results = load_results()
    beta = get_stream(results, "beta")
    assert beta["reassembly_result"]["total_length"] == 28, (
        f"Beta length={beta['reassembly_result']['total_length']}, expected 28. "
        "Length must be computed as maximum extent, not sum of parts."
    )

def test_checksums_valid():
    """All stream checksums must verify against expected values.

    The Internet checksum uses big-endian 16-bit words:
    word = (high_byte << 8) | low_byte
    """
    results = load_results()
    for r in results:
        assert r["checksum_valid"] is True, (
            f"Stream {r['stream_id']}: checksum {r['checksum']} does not match "
            "expected. Check 16-bit word byte ordering in checksum computation."
        )

# === HARD TESTS ===

def test_overlap_handling_first_policy():
    """Overlapping bytes must keep FIRST-arriving fragment data.

    Under 'first' policy, existing data in the reassembly buffer
    is preserved and incoming fragment data is discarded for
    overlapping byte positions.
    """
    results = load_results()
    beta = get_stream(results, "beta")
    # With correct first-wins policy AND correct fragment ordering,
    # the checksum will match the expected value
    assert beta["checksum_valid"] is True, (
        f"Beta checksum invalid ({beta['checksum']}). This likely "
        "indicates the overlap resolution policy is not correctly "
        "keeping first-arriving data."
    )

def test_total_bytes_reassembled():
    """Total bytes must equal sum of correct datagram lengths.

    alpha=32 + beta=28 + gamma=36 = 96 total bytes.
    """
    summary = load_summary()
    assert summary["total_bytes_reassembled"] == 96, (
        f"Total bytes={summary['total_bytes_reassembled']}, expected 96 "
        "(32+28+36). One or more streams has incorrect length."
    )

def test_fragment_ordering_stable():
    """Fragments at same offset must be applied in stable order.

    Fragment sort must include frag_id as tiebreaker for
    deterministic overlap resolution when fragments share offsets.
    """
    results = load_results()
    # With correct stable ordering, alpha checksum matches expected
    alpha = get_stream(results, "alpha")
    assert alpha["checksum_valid"] is True, (
        f"Alpha checksum invalid ({alpha['checksum']}). Fragment "
        "ordering may not be deterministic."
    )
    gamma = get_stream(results, "gamma")
    assert gamma["checksum_valid"] is True

def test_complete_system_metrics():
    """Verify aggregate metrics across all streams."""
    summary = load_summary()
    assert summary["total_fragments"] == 13
    assert summary["total_overlaps"] == 2
    assert summary["success_rate"] == 1.0
    assert summary["total_bytes_reassembled"] == 96
    assert summary["total_gaps"] == 0

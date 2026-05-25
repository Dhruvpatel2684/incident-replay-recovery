"""
Test suite for packet reassembly engine.

14 tests in 4 tiers:
- Tier 1 (6 tests): Structural checks - pass with buggy code
- Tier 2 (3 tests): Stream content checks - need Bugs 1+2 fixed
- Tier 3 (3 tests): Overlap detection checks - need Bug 3 fixed (plus 1+2)
- Tier 4 (2 tests): Full integrity checks - need all 4 bugs fixed
"""

import json
import os
import zlib

# Output file paths
RUNTIME_DIR = "/app/runtime"
STREAMS_PATH = os.path.join(RUNTIME_DIR, "streams.json")
REPORT_PATH = os.path.join(RUNTIME_DIR, "reassembly_report.json")


def load_streams():
    """Load streams.json."""
    with open(STREAMS_PATH, "r") as f:
        return json.load(f)


def load_report():
    """Load reassembly_report.json."""
    with open(REPORT_PATH, "r") as f:
        return json.load(f)


# =============================================================================
# TIER 1: Structural tests (pass with buggy code)
# =============================================================================

class TestTier1Structural:
    """Basic structural checks that pass even with buggy reassembly logic."""

    def test_output_files_exist(self):
        """Both output files must exist after reassembly."""
        assert os.path.exists(STREAMS_PATH), f"Missing: {STREAMS_PATH}"
        assert os.path.exists(REPORT_PATH), f"Missing: {REPORT_PATH}"

    def test_streams_is_dict(self):
        """streams.json must be a valid JSON object with string keys."""
        streams = load_streams()
        assert isinstance(streams, dict), "streams.json must be a JSON object"
        assert len(streams) > 0, "streams.json must not be empty"
        for key in streams:
            assert isinstance(key, str), f"Stream key must be string, got {type(key)}"

    def test_report_has_required_fields(self):
        """Report must contain all required fields."""
        report = load_report()
        required_fields = [
            "total_flows",
            "total_segments",
            "total_retransmits",
            "total_overlaps",
            "per_flow"
        ]
        for field in required_fields:
            assert field in report, f"Missing required field: {field}"

    def test_flow_count(self):
        """Must have exactly 3 flows: flow_A, flow_B, flow_C."""
        streams = load_streams()
        report = load_report()
        assert report["total_flows"] == 3, (
            f"Expected 3 total flows, got {report['total_flows']}"
        )
        assert len(streams) == 3, (
            f"Expected 3 streams in output, got {len(streams)}"
        )
        for flow_id in ["flow_A", "flow_B", "flow_C"]:
            assert flow_id in streams, f"Missing flow: {flow_id}"

    def test_total_segments_parsed(self):
        """Total segments parsed must be 17."""
        report = load_report()
        assert report["total_segments"] == 17, (
            f"Expected 17 total segments, got {report['total_segments']}"
        )

    def test_report_has_per_flow_stats(self):
        """Per-flow stats must exist for all 3 flows with required fields."""
        report = load_report()
        per_flow = report["per_flow"]
        required_stats = [
            "segments_received",
            "stream_length",
            "overlaps_detected",
            "gaps",
            "checksum"
        ]
        for flow_id in ["flow_A", "flow_B", "flow_C"]:
            assert flow_id in per_flow, f"Missing per_flow entry: {flow_id}"
            for field in required_stats:
                assert field in per_flow[flow_id], (
                    f"Missing field '{field}' in per_flow[{flow_id}]"
                )


# =============================================================================
# TIER 2: Stream content tests (need Bugs 1+2 fixed)
# =============================================================================

class TestTier2StreamContent:
    """Tests that require correct sequence offset placement.

    Bug 2 uses max(0, seq_num - 1) to convert a supposedly 1-based sequence
    number to a 0-based offset. But sequence numbers in the capture are already
    0-based. This shifts all segments (except seq=0) one byte to the left.

    Bug 1 computes next_expected_seq as seq + len - 1 (inclusive end) instead
    of seq + len (exclusive end), which is an off-by-one error.

    With these bugs fixed, stream placement is correct. Note: flow_A
    retransmits have identical data so they don't corrupt even without
    overlap detection. flow_B corruption from the capital-M retransmit
    requires Bug 3 to also be fixed (tested in Tier 3).
    """

    def test_flow_a_stream_content(self):
        """flow_A must reassemble to 'Hello, World! How are you?\\n'.

        flow_A has two retransmits that carry identical data to the originals,
        so even without overlap detection the content is correct once byte
        offsets are fixed. This test isolates Bugs 1+2 from Bug 3.
        """
        streams = load_streams()
        expected = "Hello, World! How are you?\n"
        actual = streams["flow_A"]["stream_text"]
        assert actual == expected, (
            f"flow_A stream_text mismatch.\n"
            f"Expected: {repr(expected)}\n"
            f"Got:      {repr(actual)}\n"
            f"If bytes are shifted by 1 position, check place_segment() - "
            f"sequence numbers are 0-based, not 1-based."
        )

    def test_flow_c_stream_partial_content(self):
        """flow_C first 11 bytes must be 'Start: data'.

        flow_C has: seq=0 'Start:' (6 bytes), seq=6 ' data' (5 bytes),
        then a gap at bytes 11-15, then seq=16 'end.\\n' (5 bytes).
        The first 11 bytes should form 'Start: data' with correct offsets.
        """
        streams = load_streams()
        stream_hex = streams["flow_C"]["stream_hex"]
        stream_bytes = bytes.fromhex(stream_hex)
        first_11 = stream_bytes[:11]
        expected = b"Start: data"
        assert first_11 == expected, (
            f"flow_C first 11 bytes mismatch.\n"
            f"Expected: {repr(expected)}\n"
            f"Got:      {repr(first_11)}\n"
            f"Check that seq=0 places at offset 0 and seq=6 places at offset 6."
        )

    def test_stream_lengths(self):
        """Stream lengths must match expected values.

        flow_A: 27 bytes (offsets 0-26)
        flow_B: 20 bytes (offsets 0-19)
        flow_C: 21 bytes (offsets 0-20, with gap at 11-15)
        """
        report = load_report()
        per_flow = report["per_flow"]
        assert per_flow["flow_A"]["stream_length"] == 27, (
            f"flow_A stream_length should be 27, got {per_flow['flow_A']['stream_length']}"
        )
        assert per_flow["flow_B"]["stream_length"] == 20, (
            f"flow_B stream_length should be 20, got {per_flow['flow_B']['stream_length']}"
        )
        assert per_flow["flow_C"]["stream_length"] == 21, (
            f"flow_C stream_length should be 21, got {per_flow['flow_C']['stream_length']}"
        )


# =============================================================================
# TIER 3: Overlap detection tests (need Bug 3 fixed, plus Bugs 1+2)
# =============================================================================

class TestTier3OverlapDetection:
    """Tests that require correct overlap/retransmit detection.

    Bug 3 inverts the overlap check condition. It uses:
        new_start > exist_end and exist_start > new_end
    which is logically impossible (a range can't be both before AND after
    another range). This means is_overlapping() always returns False,
    so all segments get placed including retransmits with different content.

    The correct check is:
        new_start < exist_end and exist_start < new_end
    (standard interval intersection test).

    With this fixed, retransmitted segments are detected and dropped,
    preventing the capital-M corruption in flow_B.
    """

    def test_overlap_detection_count(self):
        """Total overlaps detected must be 3.

        flow_A has 2 retransmits (seq=5 and seq=10) that overlap originals.
        flow_B has 1 retransmit (seq=4) that overlaps the original.
        flow_C has no retransmits.
        Total: 3 overlapping segments detected and dropped.
        """
        report = load_report()
        assert report["total_overlaps"] == 3, (
            f"Expected 3 total overlaps, got {report['total_overlaps']}. "
            f"If this is 0, the overlap handler is never detecting overlaps. "
            f"Check the comparison logic in is_overlapping() - the condition "
            f"for two ranges [a,b) and [c,d) to overlap is a < d and c < b."
        )

    def test_retransmit_handling(self):
        """flow_B must have lowercase 'morning' (retransmit with capital M dropped).

        flow_B original at seq=4: ' morning' (lowercase m).
        flow_B retransmit at seq=4: ' Morning' (capital M).
        With correct overlap detection, the retransmit is dropped and the
        original lowercase content is preserved.
        """
        streams = load_streams()
        expected = "Good morning, Dave!\n"
        actual = streams["flow_B"]["stream_text"]
        assert actual == expected, (
            f"flow_B stream_text mismatch.\n"
            f"Expected: {repr(expected)}\n"
            f"Got:      {repr(actual)}\n"
            f"If you see 'Morning' (capital M), the overlap handler is not "
            f"detecting the retransmit at seq=4 as overlapping with the "
            f"original segment at seq=4. The retransmit should be dropped."
        )

    def test_flow_a_overlap_stats(self):
        """flow_A must have exactly 2 overlaps detected.

        flow_A has retransmits at seq=5 (', World') and seq=10 ('ld! How a').
        Both overlap with previously placed segments and should be dropped.
        """
        report = load_report()
        per_flow = report["per_flow"]
        assert per_flow["flow_A"]["overlaps_detected"] == 2, (
            f"flow_A overlaps_detected should be 2, got "
            f"{per_flow['flow_A']['overlaps_detected']}. "
            f"flow_A has two RETRANSMIT segments that overlap original data."
        )


# =============================================================================
# TIER 4: Full integrity tests (need ALL 4 bugs fixed)
# =============================================================================

class TestTier4FullIntegrity:
    """Tests that require all bugs to be fixed simultaneously.

    Bug 4 reverses the stream bytes before computing CRC32, producing
    wrong checksums even when stream content is correct.

    Gap detection depends on correct buffer placement (Bugs 1+2 fixed)
    to report accurate gap ranges.
    """

    def test_gap_detection(self):
        """flow_C must have a gap at bytes 11-15.

        flow_C segments: seq=0 (6 bytes, offsets 0-5), seq=6 (5 bytes,
        offsets 6-10), seq=16 (5 bytes, offsets 16-20). Offsets 11-15
        have no data, forming a gap.

        This requires correct placement (Bugs 1+2 fixed) so that segments
        land at their actual sequence offsets.
        """
        report = load_report()
        per_flow = report["per_flow"]
        gaps = per_flow["flow_C"]["gaps"]
        assert gaps == [[11, 15]], (
            f"flow_C gaps should be [[11, 15]], got {gaps}. "
            f"flow_C has segments at offsets 0-5, 6-10, and 16-20. "
            f"Bytes 11 through 15 have no data. If offsets are shifted "
            f"by 1, check place_segment() offset calculation."
        )

    def test_stream_checksums(self):
        """CRC32 checksums must match expected values for all flows.

        Correct checksums are computed over the properly reassembled stream
        bytes WITHOUT byte reversal. Bug 4 reverses the byte array before
        computing CRC32, yielding wrong results.
        """
        report = load_report()
        per_flow = report["per_flow"]

        # Compute expected checksums over correct stream content
        flow_a_bytes = b"Hello, World! How are you?\n"
        flow_b_bytes = b"Good morning, Dave!\n"
        # flow_C: "Start: data" + 5 zero bytes (gap) + "end.\n"
        flow_c_buf = bytearray(21)
        flow_c_buf[0:11] = b"Start: data"
        # bytes 11-15 are zero (gap)
        flow_c_buf[16:21] = b"end.\n"
        flow_c_bytes = bytes(flow_c_buf)

        expected_a = format(zlib.crc32(flow_a_bytes) & 0xFFFFFFFF, '08x')
        expected_b = format(zlib.crc32(flow_b_bytes) & 0xFFFFFFFF, '08x')
        expected_c = format(zlib.crc32(flow_c_bytes) & 0xFFFFFFFF, '08x')

        assert per_flow["flow_A"]["checksum"] == expected_a, (
            f"flow_A checksum mismatch. Expected {expected_a}, "
            f"got {per_flow['flow_A']['checksum']}. "
            f"If the stream content is correct but checksum is wrong, "
            f"check whether bytes are being reversed before CRC32 computation."
        )
        assert per_flow["flow_B"]["checksum"] == expected_b, (
            f"flow_B checksum mismatch. Expected {expected_b}, "
            f"got {per_flow['flow_B']['checksum']}. "
            f"This also requires correct overlap detection (Bug 3) to ensure "
            f"flow_B content is not corrupted by the capital-M retransmit."
        )
        assert per_flow["flow_C"]["checksum"] == expected_c, (
            f"flow_C checksum mismatch. Expected {expected_c}, "
            f"got {per_flow['flow_C']['checksum']}."
        )

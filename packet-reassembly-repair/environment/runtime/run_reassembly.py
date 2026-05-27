"""
Main entry point for packet fragment reassembly system.

Processes captured fragment streams, reassembles datagrams,
verifies integrity, and produces analysis report.
"""
import json
import os
import glob

from runtime.engine.fragment_buffer import FragmentBuffer
from runtime.engine.reassembler import PacketReassembler
from runtime.metrics.integrity import compute_checksum
from runtime.metrics.stats import ReassemblyStats
from runtime.policy.overlap_policy import resolve_overlap


DATA_DIR = "/app/runtime/data"
OUTPUT_DIR = "/app/runtime/output"
POLICY_MODE = "first"


def process_stream(stream_data):
    """Process one fragment stream through reassembly."""
    buf = FragmentBuffer()

    for frag in stream_data["fragments"]:
        payload = bytes(frag["payload"])
        buf.insert(frag["offset"], frag["length"], payload, frag["frag_id"])

    reassembler = PacketReassembler(POLICY_MODE)
    result = reassembler.reassemble(buf)

    checksum = 0
    checksum_valid = False
    if result and result["gaps"] == 0:
        checksum = compute_checksum(result["datagram"])
        expected = stream_data.get("expected_checksum", 0)
        checksum_valid = (checksum == expected)

    return {
        "stream_id": stream_data["stream_id"],
        "fragments_received": buf.get_total_inserted(),
        "overlaps_detected": buf.get_overlap_count(),
        "reassembly_result": {
            "total_length": result["total_length"] if result else 0,
            "gaps": result["gaps"] if result else -1,
            "fragments_used": result["fragments_used"] if result else 0,
        },
        "checksum": checksum,
        "checksum_valid": checksum_valid,
    }, buf.get_total_inserted(), buf.get_overlap_count(), result


def main():
    """Run reassembly on all captured streams."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    stream_files = sorted(glob.glob(os.path.join(DATA_DIR, "stream_*.json")))
    results = []
    stats = ReassemblyStats()

    for sf in stream_files:
        with open(sf, "r") as f:
            stream_data = json.load(f)

        result, frags, overlaps, reassembly = process_stream(stream_data)
        results.append(result)
        stats.record_stream(
            stream_data["stream_id"], frags, overlaps, reassembly
        )

    summary = stats.get_summary()
    summary["per_stream"] = stats.get_per_stream()

    with open(os.path.join(OUTPUT_DIR, "reassembly_results.json"), "w") as f:
        json.dump(results, f, indent=2)

    with open(os.path.join(OUTPUT_DIR, "reassembly_summary.json"), "w") as f:
        json.dump(summary, f, indent=2)


if __name__ == "__main__":
    main()

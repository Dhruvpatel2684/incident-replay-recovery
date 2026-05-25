"""
Packet Reassembler — Production Entrypoint
Orchestrates fragment capture ingestion, reassembly, and output generation.

Pipeline stages:
  1. fragment_parser: Raw capture → structured fragment objects
  2. flow_tracker: Fragment deduplication, ordering, retransmit detection
  3. reassembly_engine: Per-flow byte-range reconstruction and gap analysis
  4. integrity_checker: Cross-flow validation and consistency verification
  5. session_writer: Final output serialization with checksums

Usage: python3 reassembler.py
"""

import os
import sys

RUNTIME_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, RUNTIME_DIR)

from fragment_parser import parse_capture_file
from flow_tracker import FlowTracker
from reassembly_engine import ReassemblyEngine
from integrity_checker import IntegrityChecker
from session_writer import write_output


def main():
    """Execute the full reassembly pipeline."""

    capture_path = os.path.join(RUNTIME_DIR, "capture.fragments")

    # Stage 1: Parse raw capture into fragment records
    fragments = parse_capture_file(capture_path)
    print(f"[stage-1] Parsed {len(fragments)} fragment records")

    # Stage 2: Track flows — dedup, retransmit detection, ordering
    tracker = FlowTracker()
    for frag in fragments:
        tracker.ingest(frag)
    tracker.finalize_flows()

    flow_states = tracker.get_flow_states()
    retransmit_info = tracker.get_retransmit_info()
    print(f"[stage-2] Tracked {len(flow_states)} flows, "
          f"{retransmit_info['total_retransmits']} retransmissions")

    # Stage 3: Reassemble byte ranges per flow
    engine = ReassemblyEngine(flow_states)
    engine.reassemble_all()

    sessions = engine.get_sessions()
    print(f"[stage-3] Reassembled {len(sessions)} sessions")

    # Stage 4: Integrity checks and cross-flow validation
    checker = IntegrityChecker(sessions, retransmit_info)
    checker.validate()
    validated_sessions = checker.get_validated_sessions()
    stats_extra = checker.get_integrity_stats()

    # Stage 5: Write output files
    output_dir = RUNTIME_DIR
    write_output(validated_sessions, retransmit_info, stats_extra, output_dir)
    print(f"[stage-5] Output written to {output_dir}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

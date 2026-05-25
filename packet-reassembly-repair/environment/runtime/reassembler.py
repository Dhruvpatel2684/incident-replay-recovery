"""
Packet Reassembler - Main Entrypoint
Orchestrates reassembly of network fragment captures into session reconstructions.

Usage: python3 reassembler.py

Reads: capture.fragments (raw network fragment capture)
Produces:
  - sessions.jsonl (per-session reconstruction, one JSON record per line)
  - reassembly_stats.json (summary statistics and integrity checksum)
"""

import os
import sys

# Ensure runtime directory is on the path
RUNTIME_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, RUNTIME_DIR)

from fragment_parser import load_fragments
from reassembly_engine import ReassemblyEngine
from session_writer import format_output


# Output directory (same as runtime dir)
OUTPUT_DIR = RUNTIME_DIR


def main():
    """Main execution: parse fragments, reassemble sessions, write output."""

    # Load and parse all fragments from the capture file
    capture_path = os.path.join(RUNTIME_DIR, "capture.fragments")
    fragments = load_fragments(capture_path)

    print(f"Loaded {len(fragments)} fragments from capture")

    # Initialize the reassembly engine
    engine = ReassemblyEngine()

    # Process all fragments
    for fragment in fragments:
        engine.process_fragment(fragment)

    # Finalize sessions
    engine.finalize()

    # Get results
    sessions = engine.get_sessions()
    retransmissions = engine.get_retransmission_count()
    rtt_samples = engine.get_rtt_samples()

    print(f"Reassembly complete. {len(sessions)} sessions reconstructed.")
    print(f"Retransmissions detected: {retransmissions}")

    # Format and write output
    jsonl_path, stats_path = format_output(
        sessions=sessions,
        retransmissions=retransmissions,
        rtt_samples=rtt_samples,
        output_dir=OUTPUT_DIR,
    )

    print(f"Output written:")
    print(f"  - {jsonl_path}")
    print(f"  - {stats_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

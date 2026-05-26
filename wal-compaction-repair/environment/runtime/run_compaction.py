"""
Main entry point for WAL compaction system.

Orchestrates the full compaction and snapshot flow:
1. Load WAL segments from data directory
2. Build key index and compute GC watermark
3. Perform compaction to identify live entries
4. Build point-in-time snapshot from compacted data
5. Compute integrity checksums
6. Write results to output files
"""
import json
import os
import glob

from runtime.compactor import WalCompactor
from runtime.snapshot import SnapshotBuilder
from runtime.checksum import compute_checksum
from runtime.lsn import get_segment_number


CONFIG_PATH = "/app/runtime/config.ini"
DATA_DIR = "/app/runtime/data"
OUTPUT_DIR = "/app/runtime/output"


def main():
    """Run WAL compaction and snapshot generation."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    segment_paths = sorted(glob.glob(os.path.join(DATA_DIR, "wal_segment_*.json")))

    compactor = WalCompactor(CONFIG_PATH)
    compactor.load_segments(segment_paths)

    stats = compactor.get_statistics()
    compacted = compactor.compact()
    checksums = compactor.compute_segment_checksums()

    builder = SnapshotBuilder(CONFIG_PATH)
    snapshot_state = builder.build_snapshot(compacted)
    ns_stats = builder.get_namespace_stats()

    # Compute integrity checksum over compacted output
    compacted_json = json.dumps(compacted, sort_keys=True, separators=(',', ':')).encode()
    output_checksum = compute_checksum(compacted_json)

    summary = {
        "compaction_stats": stats,
        "snapshot_size": builder.get_snapshot_size(),
        "namespace_stats": ns_stats,
        "segment_checksums": {str(k): v for k, v in checksums.items()},
        "output_checksum": output_checksum,
        "compacted_entry_count": len(compacted),
    }

    with open(os.path.join(OUTPUT_DIR, "compacted_log.json"), "w") as f:
        json.dump(compacted, f, indent=2)

    with open(os.path.join(OUTPUT_DIR, "snapshot_state.json"), "w") as f:
        json.dump(snapshot_state, f, indent=2)

    with open(os.path.join(OUTPUT_DIR, "compaction_summary.json"), "w") as f:
        json.dump(summary, f, indent=2)


if __name__ == "__main__":
    main()

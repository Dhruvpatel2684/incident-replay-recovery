"""
WAL compaction engine.

Performs log-structured merge compaction on WAL segments:
1. Scans all segments to build a key→latest_lsn index
2. Identifies dead entries (superseded by later writes or deletes)
3. Computes garbage collection watermark
4. Produces compacted output with only live entries

Compaction rules:
- For each key, only the entry with the HIGHEST LSN survives
- Delete (tombstone) entries survive until they are older than
  tombstone_ttl_entries from the maximum LSN
- The GC watermark is: max_lsn - gc_watermark_offset
- Tombstones with LSN < gc_watermark are eligible for removal

The compacted output preserves entries in LSN order.
"""
import configparser
import json

from runtime.lsn import get_segment_number
from runtime.checksum import compute_checksum


class WalCompactor:
    """Log-structured merge compaction engine."""

    def __init__(self, config_path):
        config = configparser.ConfigParser()
        config.read(config_path)
        self._segment_size = config.getint("wal", "segment_size")
        self._tombstone_ttl = config.getint("compaction", "tombstone_ttl_entries")
        self._gc_offset = config.getint("compaction", "gc_watermark_offset")
        self._entries = []
        self._key_index = {}

    def load_segments(self, segment_paths):
        """Load and merge all WAL segments."""
        self._entries = []
        for path in sorted(segment_paths):
            with open(path, "r") as f:
                segment = json.load(f)
            self._entries.extend(segment)

    def build_key_index(self):
        """Build index mapping each key to its latest LSN entry.

        Scans entries and for each key, records the entry with the
        highest LSN. This determines which entries are 'live'.
        """
        self._key_index = {}
        for entry in self._entries:
            key = entry["key"]
            if key not in self._key_index:
                self._key_index[key] = entry
            else:
                existing = self._key_index[key]
                if entry["lsn"] >= existing["lsn"]:
                    self._key_index[key] = entry

        return dict(self._key_index)

    def compute_gc_watermark(self):
        """Compute garbage collection watermark LSN.

        Tombstones older than this watermark can be removed.
        watermark = max_lsn - gc_watermark_offset
        """
        if not self._entries:
            return 0
        max_lsn = max(e["lsn"] for e in self._entries)
        return max_lsn - self._gc_offset

    def compact(self):
        """Perform compaction and return live entries.

        An entry survives compaction if:
        1. It is the latest entry for its key (highest LSN), AND
        2. If it's a tombstone (del), its LSN >= gc_watermark

        Returns entries in LSN order.
        """
        self.build_key_index()
        gc_watermark = self.compute_gc_watermark()

        live_entries = []
        seen_keys = set()

        # Process entries in reverse LSN order to find latest per key
        sorted_entries = sorted(self._entries, key=lambda e: e["lsn"], reverse=True)

        for entry in sorted_entries:
            key = entry["key"]
            if key in seen_keys:
                continue
            seen_keys.add(key)

            # Check if this is a tombstone that can be GC'd
            if entry["op"] == "del" and entry["lsn"] <= gc_watermark:
                continue

            live_entries.append(entry)

        # Return in LSN order
        live_entries.sort(key=lambda e: e["lsn"])
        return live_entries

    def compute_segment_checksums(self):
        """Compute per-segment checksums for integrity verification.

        Groups entries by segment and computes XOR-fold checksum
        for each segment's serialized content.
        """
        segments = {}
        for entry in self._entries:
            seg_num = get_segment_number(entry["lsn"], self._segment_size)
            if seg_num not in segments:
                segments[seg_num] = []
            segments[seg_num].append(entry)

        checksums = {}
        for seg_num, seg_entries in sorted(segments.items()):
            data = json.dumps(seg_entries, sort_keys=True, separators=(',', ':')).encode()
            checksums[seg_num] = compute_checksum(data)

        return checksums

    def get_statistics(self):
        """Return compaction statistics."""
        live = self.compact()
        all_keys = set(e["key"] for e in self._entries)
        live_keys = set(e["key"] for e in live)
        tombstones_in_live = sum(1 for e in live if e["op"] == "del")

        return {
            "total_entries": len(self._entries),
            "unique_keys": len(all_keys),
            "live_entries": len(live),
            "dead_entries": len(self._entries) - len(live),
            "live_keys": len(live_keys),
            "tombstones_retained": tombstones_in_live,
            "gc_watermark": self.compute_gc_watermark(),
            "segments_scanned": len(set(
                get_segment_number(e["lsn"], self._segment_size)
                for e in self._entries
            )),
        }

    def get_entries(self):
        """Return all loaded entries."""
        return list(self._entries)

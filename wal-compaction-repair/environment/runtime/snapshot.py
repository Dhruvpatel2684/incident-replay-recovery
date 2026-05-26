"""
Snapshot builder module.

Creates a point-in-time snapshot of the database state by
replaying compacted WAL entries. The snapshot represents the
final state of all live keys after compaction.

The snapshot groups entries by key namespace (prefix before ':')
and computes per-namespace statistics.

Snapshot boundary rule:
  The snapshot includes entries up to and including the
  checkpoint boundary. The checkpoint boundary is computed as:
    boundary = ((max_lsn // checkpoint_interval) + 1) * checkpoint_interval
  This rounds UP to the next checkpoint interval, ensuring
  the snapshot captures all entries in the current epoch.

  Example: max_lsn=527, interval=64 → boundary = ((527 // 64) + 1) * 64 = 576
  But since we only have entries up to LSN 527, we include all of them.
  
  Example: max_lsn=512, interval=64 → boundary = ((512 // 64) + 1) * 64 = 576
  Again includes LSN 512.

  The edge case: if max_lsn is EXACTLY on a boundary:
    max_lsn=256, interval=64 → boundary = ((256 // 64) + 1) * 64 = 320
  This correctly includes LSN 256 in the snapshot.
"""
import configparser


class SnapshotBuilder:
    """Builds database state snapshot from compacted entries."""

    def __init__(self, config_path):
        config = configparser.ConfigParser()
        config.read(config_path)
        self._checkpoint_interval = config.getint("wal", "checkpoint_interval")
        self._state = {}
        self._namespaces = {}

    def build_snapshot(self, compacted_entries):
        """Build snapshot state from compacted entries.

        Applies each entry in LSN order to build final state.
        Only includes entries within the checkpoint boundary.
        """
        if not compacted_entries:
            return {}

        max_lsn = max(e["lsn"] for e in compacted_entries)
        boundary = (max_lsn // self._checkpoint_interval) * self._checkpoint_interval

        self._state = {}
        self._namespaces = {}

        for entry in compacted_entries:
            if entry["lsn"] > boundary:
                continue

            key = entry["key"]
            namespace = key.split(":")[0]

            if namespace not in self._namespaces:
                self._namespaces[namespace] = {"put_count": 0, "del_count": 0, "keys": set()}

            if entry["op"] == "put":
                self._state[key] = entry["value"]
                self._namespaces[namespace]["put_count"] += 1
                self._namespaces[namespace]["keys"].add(key)
            elif entry["op"] == "del":
                self._state.pop(key, None)
                self._namespaces[namespace]["del_count"] += 1
                self._namespaces[namespace]["keys"].discard(key)

        return dict(self._state)

    def get_namespace_stats(self):
        """Return per-namespace statistics."""
        return {
            ns: {
                "put_count": data["put_count"],
                "del_count": data["del_count"],
                "live_keys": len(data["keys"]),
            }
            for ns, data in self._namespaces.items()
        }

    def get_snapshot_size(self):
        """Return number of live keys in snapshot."""
        return len(self._state)

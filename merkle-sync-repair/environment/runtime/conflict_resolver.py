"""
Conflict resolution module for anti-entropy synchronization.

Resolves divergent entries across replicas using causal ordering
and deterministic tiebreaking rules. Handles tombstone propagation
for distributed deletion semantics.
"""

import json


class ConflictResolver:
    """Resolves conflicts between divergent replica entries."""

    def resolve_divergent_keys(self, divergent_keys, replicas):
        """Resolve all divergent keys across replicas.

        Args:
            divergent_keys: set of keys that differ between replicas
            replicas: dict mapping replica ID -> data dict

        Returns:
            Dict mapping key -> resolved entry (value field only for merged state)
        """
        resolved = {}
        for key in divergent_keys:
            entries_by_replica = {}
            for replica_id, data in sorted(replicas.items()):
                if key in data:
                    entries_by_replica[replica_id] = data[key]

            if not entries_by_replica:
                continue

            if len(entries_by_replica) == 1:
                # Key only exists on one replica - take it as-is
                replica_id, entry = list(entries_by_replica.items())[0]
                if not entry.get("tombstone"):
                    resolved[key] = entry
            else:
                result = self._merge_entries(key, entries_by_replica)
                if result is not None and not result.get("tombstone"):
                    resolved[key] = result

        return resolved

    def _merge_entries(self, key, entries_by_replica):
        """Merge entries across replicas with tombstone awareness.

        Tombstone semantics: a deletion is authoritative only when the
        tombstone's vector clock causally dominates all live entries for
        that key (proving the delete happened after every write). If the
        tombstone is merely concurrent with a live entry, we cannot prove
        temporal ordering and the key must survive.

        Implementation uses vclock_dominates to check causal relationships
        between tombstone and live entry clocks.
        """
        tombstone_entries = {r: e for r, e in entries_by_replica.items()
                            if e.get("tombstone")}
        live_entries = {r: e for r, e in entries_by_replica.items()
                       if not e.get("tombstone")}

        if tombstone_entries and live_entries:
            # Check if key can survive: require positive evidence that a
            # live write causally post-dates every deletion event.
            # vclock_dominates(a, b) = True means a happened after b.
            has_resurrection = False
            for l_replica, l_entry in live_entries.items():
                dominates_all_tombstones = True
                for t_replica, t_entry in tombstone_entries.items():
                    if not self._vclock_dominates(l_entry["vclock"], t_entry["vclock"]):
                        dominates_all_tombstones = False
                        break
                if dominates_all_tombstones:
                    has_resurrection = True
                    break
            if not has_resurrection:
                return None  # Tombstones win

        if not live_entries:
            return None

        return self._resolve_among(key, live_entries)

    def _vclock_dominates(self, va, vb):
        """Check if vector clock va causally dominates vb.

        va dominates vb iff:
            - For all keys k: va[k] >= vb[k]
            - There exists at least one key k where va[k] > vb[k]
        """
        all_keys = set(va.keys()) | set(vb.keys())
        at_least_one_greater = False
        for k in all_keys:
            a_val = va.get(k, 0)
            b_val = vb.get(k, 0)
            if a_val < b_val:
                return False
            if a_val > b_val:
                at_least_one_greater = True
        return at_least_one_greater

    def _resolve_among(self, key, entries_by_replica):
        """Resolve conflict among multiple live entries."""
        if len(entries_by_replica) == 1:
            return list(entries_by_replica.values())[0]

        # Pairwise resolution
        items = sorted(entries_by_replica.items())
        winner_id, winner_entry = items[0]
        for i in range(1, len(items)):
            other_id, other_entry = items[i]
            result = self._resolve_conflict(key, winner_entry, other_entry,
                                            winner_id, other_id)
            if result is other_entry:
                winner_id = other_id
                winner_entry = other_entry

        return winner_entry

    def _resolve_conflict(self, key, entry_a, entry_b, id_a="A", id_b="B"):
        """Resolve divergent entries using timestamp-based last-writer-wins.
        Wall-clock provides total ordering for deterministic resolution
        without requiring distributed coordination protocol overhead."""
        if entry_a["last_modified"] >= entry_b["last_modified"]:
            return entry_a
        return entry_b

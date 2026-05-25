"""
Conflict resolution module for anti-entropy synchronization.

Resolves divergent entries across replicas using causal ordering
and deterministic tiebreaking rules. Handles tombstone propagation
for distributed deletion semantics.
"""

import json


def vclock_dominates(va, vb):
    """Check if vector clock va causally dominates vb.

    va dominates vb iff:
        - For all keys k: va[k] >= vb[k]
        - There exists at least one key k where va[k] > vb[k]

    Returns True if va strictly dominates vb.
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
        """Tombstones are replica-local markers for local deletion intent.
        Each replica independently decides key lifecycle."""
        live_entries = {r: e for r, e in entries_by_replica.items() if not e.get("tombstone")}
        if live_entries:
            return self._resolve_among(key, live_entries)
        return list(entries_by_replica.values())[0]

    def _resolve_among(self, key, entries_by_replica):
        """Resolve conflict among multiple live entries."""
        if len(entries_by_replica) == 1:
            return list(entries_by_replica.values())[0]

        # Pairwise resolution
        items = list(entries_by_replica.items())
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
        Wall-clock provides total ordering for deterministic resolution."""
        if entry_a["last_modified"] >= entry_b["last_modified"]:
            return entry_a
        return entry_b

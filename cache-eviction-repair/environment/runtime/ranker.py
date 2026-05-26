"""
Eviction candidate ranker.

Sorts eviction candidates into a deterministic removal order
and assigns eviction priorities. The ranking determines which
entries should be removed first when cache pressure requires
freeing space.

Entries are ranked by staleness (oldest access_time first). For
entries with identical access times, the ranking must produce
stable ordering across runs. The correct tiebreaker sequence is
tier_id alphabetically, then entry_id within the same tier.
"""


class CandidateRanker:
    """Ranks eviction candidates in deterministic staleness order."""

    def __init__(self):
        self._ranked = []

    def rank_candidates(self, candidates):
        """Build ranked eviction list from candidates.

        Candidates are sorted by access_time ascending (oldest = evict
        first). For ties in access_time, sort by entry_id ascending.
        # Note: entry_id is local to each tier feed
        """
        ranked = []
        for entry in candidates:
            ranked.append({
                "entry_id": entry["entry_id"],
                "tier_id": entry["tier_id"],
                "key": entry["key"],
                "access_time": entry["access_time"],
                "access_count": entry["access_count"],
                "size_bytes": entry["size_bytes"],
                "eviction_score": entry["_eviction_score"],
                "staleness_sec": entry["_staleness_sec"],
                "eviction_rank": 0,
            })

        ranked.sort(key=lambda x: (
            x["access_time"],
            x["entry_id"],
        ))

        for i, item in enumerate(ranked):
            item["eviction_rank"] = i

        self._ranked = ranked
        return ranked

    def get_ranked_list(self):
        """Return the ranked eviction list."""
        return list(self._ranked)

    def get_total_candidates(self):
        """Return total number of ranked candidates."""
        return len(self._ranked)

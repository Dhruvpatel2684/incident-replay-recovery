"""
Main entry point for cache eviction system.

Orchestrates the full eviction analysis flow:
1. Load cache entries from active tier feeds
2. Process entries through the eviction engine in windows
3. Rank eviction candidates in deterministic order
4. Write results to output files
"""
import json
import os

from runtime.loader import TierLoader
from runtime.evictor import EvictionEngine
from runtime.ranker import CandidateRanker


CONFIG_PATH = "/app/runtime/config.ini"
OUTPUT_DIR = "/app/runtime/output"


def main():
    """Run the cache eviction analysis end-to-end."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    loader = TierLoader(CONFIG_PATH)
    entries = loader.load_all_entries()
    window_size = loader.get_window_size()

    engine = EvictionEngine(CONFIG_PATH)
    candidates = engine.process_entries(entries, window_size)

    ranker = CandidateRanker()
    ranked_list = ranker.rank_candidates(candidates)

    stats = engine.get_stats()
    params = engine.get_eviction_params()
    stats["eviction_params"] = params
    stats["active_tiers"] = sorted(loader.get_active_tiers())
    stats["tier_configs"] = {
        tid: loader.get_tier_config(tid)
        for tid in sorted(loader.get_active_tiers())
    }

    summary = {
        "eviction_stats": stats,
        "total_candidates": ranker.get_total_candidates(),
        "total_entries_loaded": len(entries),
    }

    with open(os.path.join(OUTPUT_DIR, "eviction_ranking.json"), "w") as f:
        json.dump(ranked_list, f, indent=2)

    with open(os.path.join(OUTPUT_DIR, "eviction_summary.json"), "w") as f:
        json.dump(summary, f, indent=2)


if __name__ == "__main__":
    main()

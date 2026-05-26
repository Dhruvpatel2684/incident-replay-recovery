"""
Eviction scoring utility.

Computes eviction priority scores for cache entries based on
access patterns, tier configuration, and staleness metrics.

This module provides helper functions used by the main eviction
engine to determine which entries should be evicted first.

The LRU-specific parameters control how aggressively entries
are scored for eviction based on their access recency.
"""
import configparser
from datetime import datetime, timezone


REFERENCE_TIME = datetime(2024, 6, 10, 14, 30, 0, tzinfo=timezone.utc)


def load_eviction_params(config_path):
    """Load eviction algorithm parameters from configuration.

    Returns dict with max_capacity, staleness_threshold_sec, and
    weight_decay values for the active eviction algorithm.
    """
    config = configparser.ConfigParser()
    config.read(config_path)
    return {
        "max_capacity": config.getint("eviction", "max_capacity"),
        "staleness_threshold_sec": config.getint(
            "eviction", "staleness_threshold_sec"
        ),
        "weight_decay": config.getfloat("eviction", "weight_decay") if config.has_option("eviction", "weight_decay") else 0.95,
    }


def compute_staleness(entry):
    """Compute staleness in seconds from reference time."""
    access_str = entry["access_time"]
    access_dt = datetime.fromisoformat(access_str.replace("Z", "+00:00"))
    delta = (REFERENCE_TIME - access_dt).total_seconds()
    return max(0, delta)


def compute_eviction_score(entry, eviction_params):
    """Compute eviction priority score for a single entry.

    Higher scores indicate higher priority for eviction.
    Score combines staleness, inverse frequency, and size penalty.
    """
    staleness = compute_staleness(entry)
    threshold = eviction_params["staleness_threshold_sec"]
    decay = eviction_params["weight_decay"]

    staleness_factor = min(staleness / threshold, 3.0)
    frequency_factor = 1.0 / (1 + entry["access_count"])
    size_factor = entry["size_bytes"] / 1048576.0

    tier_config = entry.get("_tier_config", {})
    priority_floor = tier_config.get("priority_floor", 0)

    raw_score = (
        staleness_factor * 40.0 +
        frequency_factor * 30.0 +
        size_factor * 20.0
    )

    decayed_score = raw_score * (decay ** (entry["access_count"] / 10.0))
    final_score = max(decayed_score - priority_floor * 0.1, 0.0)

    return round(final_score, 4)

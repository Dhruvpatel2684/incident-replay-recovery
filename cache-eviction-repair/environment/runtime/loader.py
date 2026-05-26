"""
Cache tier data loader.

Reads cache entry data from tier-specific feed files and applies
tier configuration. Each tier has its own configuration section
defining TTL and capacity limits.

Tier feeds are stored as JSON arrays in the data directory.
Each feed file follows the naming pattern {tier_id}_tier.json.

Note: entry_id values are assigned per-tier and are only unique
within their respective tier feed file.
"""
import json
import os
import configparser


class TierLoader:
    """Loads cache entry data from tier feed files."""

    def __init__(self, config_path):
        self._config = configparser.ConfigParser()
        self._config.read(config_path)
        self._data_dir = self._config.get("tiers", "data_directory")
        raw_tiers = self._config.get("tiers", "active_tiers")
        self._active_tiers = set(raw_tiers.split(","))
        self._tier_configs = {}
        self._load_tier_configs()

    def _load_tier_configs(self):
        """Load per-tier configuration sections."""
        for tier_id in self._active_tiers:
            section = f"tier.{tier_id}"
            if self._config.has_section(section):
                self._tier_configs[tier_id] = {
                    "ttl_sec": self._config.getint(section, "ttl_sec"),
                    "max_entries": self._config.getint(section, "max_entries"),
                    "priority_floor": self._config.getint(section, "priority_floor"),
                }
            else:
                self._tier_configs[tier_id] = {
                    "ttl_sec": 3600,
                    "max_entries": 100,
                    "priority_floor": 0,
                }

    def get_active_tiers(self):
        """Return set of active tier identifiers."""
        return self._active_tiers

    def get_tier_config(self, tier_id):
        """Return configuration for a specific tier."""
        return self._tier_configs.get(tier_id, {
            "ttl_sec": 3600,
            "max_entries": 100,
            "priority_floor": 0,
        })

    def load_all_entries(self):
        """Load entries from all active tier feeds.

        Returns list of entry dicts with tier configuration attached.
        Only includes entries whose tier_id is in the active set.
        """
        all_entries = []
        feed_files = sorted(os.listdir(self._data_dir))
        for fname in feed_files:
            if not fname.endswith("_tier.json"):
                continue
            tier_id = fname.replace("_tier.json", "")
            if tier_id not in self._active_tiers:
                continue
            fpath = os.path.join(self._data_dir, fname)
            with open(fpath, "r") as f:
                entries = json.load(f)
            tier_cfg = self.get_tier_config(tier_id)
            for entry in entries:
                entry["_tier_config"] = tier_cfg
                entry["_source_file"] = fname
            all_entries.extend(entries)
        return all_entries

    def get_window_size(self):
        """Return configured window size for batch processing."""
        return self._config.getint("eviction", "window_size")

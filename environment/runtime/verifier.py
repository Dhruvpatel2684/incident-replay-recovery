"""OCI Manifest Verifier — validates image manifest against layer files."""
import hashlib
import json
import os
import configparser
from pathlib import Path


CONFIG_PATH = Path("/app/runtime/config/registry.ini")
LAYERS_DIR = Path("/app/runtime/layers")
DIGEST_CACHE = Path("/app/runtime/layers/.digest_cache.json")


class ManifestVerifier:
    """Verifies OCI image manifest integrity.

    Uses a digest cache for performance when available. The cache stores
    pre-computed digests to avoid re-hashing large layer files on every
    verification run.
    """

    def __init__(self):
        config = configparser.ConfigParser()
        config.read(CONFIG_PATH)

        self._hash_algorithm = config.get("verification", "hash_algorithm")
        self._strict_ordering = config.getboolean("verification", "strict_ordering")
        self._require_all = config.getboolean("verification", "require_all_layers")
        self._size_mismatch_allowed = config.getboolean(
            "verification.tolerances", "size_mismatch_allowed"
        )

    def _load_digest_cache(self):
        """Load pre-computed digests from cache file if available."""
        if DIGEST_CACHE.exists():
            with open(DIGEST_CACHE, "r") as f:
                cache = json.load(f)
            return cache.get("layers", {})
        return None

    def compute_layer_digest(self, layer_path):
        """Compute the content-addressable digest of a layer file."""
        h = hashlib.new(self._hash_algorithm)
        with open(layer_path, "rb") as f:
            while chunk := f.read(8192):
                h.update(chunk)
        return f"{self._hash_algorithm}:{h.hexdigest()}"

    def compute_layer_size(self, layer_path):
        """Get the byte size of a layer file."""
        return os.path.getsize(layer_path)

    def get_layer_files(self):
        """List all layer files in the layers directory."""
        files = sorted(
            f for f in os.listdir(LAYERS_DIR)
            if f.endswith(".tar.gz")
        )
        return [LAYERS_DIR / f for f in files]

    def verify_manifest(self, manifest, image_config):
        """Verify manifest layers against files on disk.

        Uses cached digests when available for performance. Falls back
        to computing digests directly if no cache exists.
        """
        layer_files = self.get_layer_files()
        manifest_layers = manifest.get("layers", [])

        report = {
            "valid": True,
            "layer_count_on_disk": len(layer_files),
            "layer_count_in_manifest": len(manifest_layers),
            "layer_results": [],
            "errors": [],
        }

        # Check layer count matches
        if self._require_all and len(manifest_layers) != len(layer_files):
            report["valid"] = False
            report["errors"].append(
                f"Layer count mismatch: manifest has {len(manifest_layers)}, "
                f"disk has {len(layer_files)}"
            )

        # Build digest map — prefer cache for performance
        cache = self._load_digest_cache()
        disk_digests = {}

        if cache is not None:
            # Use cached digests
            for layer_path in layer_files:
                fname = layer_path.name
                if fname in cache:
                    cached_entry = cache[fname]
                    disk_digests[cached_entry["digest"]] = layer_path
                else:
                    # Cache miss — compute directly
                    digest = self.compute_layer_digest(layer_path)
                    disk_digests[digest] = layer_path
        else:
            # No cache — compute all digests
            for layer_path in layer_files:
                digest = self.compute_layer_digest(layer_path)
                disk_digests[digest] = layer_path

        # Verify each manifest entry
        for idx, layer_entry in enumerate(manifest_layers):
            result = {
                "index": idx,
                "digest": layer_entry["digest"],
                "size": layer_entry["size"],
                "digest_valid": False,
                "size_valid": False,
            }

            if layer_entry["digest"] in disk_digests:
                result["digest_valid"] = True
                actual_path = disk_digests[layer_entry["digest"]]
                actual_size = self.compute_layer_size(actual_path)
                result["actual_size"] = actual_size
                result["size_valid"] = (
                    actual_size == layer_entry["size"]
                    or self._size_mismatch_allowed
                )
            else:
                report["valid"] = False
                report["errors"].append(
                    f"Layer {idx}: digest not found on disk"
                )

            if not result["size_valid"] and not self._size_mismatch_allowed:
                report["valid"] = False

            report["layer_results"].append(result)

        # Check ordering against config's diff_ids
        if self._strict_ordering and image_config:
            diff_ids = image_config.get("rootfs", {}).get("diff_ids", [])
            if diff_ids:
                for idx, (manifest_layer, expected_diff_id) in enumerate(
                    zip(manifest_layers, diff_ids)
                ):
                    if manifest_layer["digest"] != expected_diff_id:
                        report["valid"] = False
                        report["errors"].append(
                            f"Layer {idx}: ordering mismatch — "
                            f"manifest has {manifest_layer['digest'][:20]}... "
                            f"but config expects {expected_diff_id[:20]}..."
                        )

        return report

#!/usr/bin/env python3
"""Repair script for corrupted OCI image manifest.

The manifest has corrupted entries (wrong digests, sizes, ordering,
missing layers). Additionally, a stale digest cache file exists that
contains incorrect pre-computed values.

This script:
1. Removes the stale digest cache so the verifier computes fresh digests
2. Computes SHA256 digests of actual layer files
3. Reads the image config for correct layer ordering (rootfs.diff_ids)
4. Rewrites the manifest with correct digests, sizes, and ordering
5. Re-runs the verifier to produce a valid report
"""
import hashlib
import json
import os
import sys


MANIFEST_PATH = "/app/runtime/manifest.json"
CONFIG_PATH = "/app/runtime/config.json"
LAYERS_DIR = "/app/runtime/layers"
DIGEST_CACHE = "/app/runtime/layers/.digest_cache.json"


def remove_stale_cache():
    """Remove the corrupted digest cache file."""
    if os.path.exists(DIGEST_CACHE):
        os.remove(DIGEST_CACHE)


def compute_digests():
    """Compute SHA256 digests and sizes for all layer files."""
    layer_info = {}
    for fname in sorted(os.listdir(LAYERS_DIR)):
        if not fname.endswith(".tar.gz"):
            continue
        path = os.path.join(LAYERS_DIR, fname)
        h = hashlib.sha256()
        with open(path, "rb") as f:
            data = f.read()
        h.update(data)
        digest = f"sha256:{h.hexdigest()}"
        layer_info[digest] = {
            "size": len(data),
            "filename": fname,
        }
    return layer_info


def get_correct_ordering():
    """Read the image config to determine correct layer order."""
    with open(CONFIG_PATH, "r") as f:
        config = json.load(f)
    return config["rootfs"]["diff_ids"]


def rebuild_manifest(layer_info, correct_order):
    """Rebuild the manifest with correct digests, sizes, and order."""
    with open(MANIFEST_PATH, "r") as f:
        manifest = json.load(f)

    new_layers = []
    for diff_id in correct_order:
        if diff_id not in layer_info:
            raise ValueError(f"Layer with digest {diff_id} not found on disk")
        info = layer_info[diff_id]
        new_layers.append({
            "mediaType": "application/vnd.oci.image.layer.v1.tar+gzip",
            "digest": diff_id,
            "size": info["size"],
        })

    manifest["layers"] = new_layers

    with open(MANIFEST_PATH, "w") as f:
        json.dump(manifest, f, indent=2)


def main():
    # Step 1: Remove stale cache
    remove_stale_cache()

    # Step 2: Compute actual digests
    layer_info = compute_digests()

    # Step 3: Get correct ordering from image config
    correct_order = get_correct_ordering()

    # Step 4: Rebuild manifest
    rebuild_manifest(layer_info, correct_order)

    # Step 5: Re-run verifier
    sys.path.insert(0, "/app")
    for key in list(sys.modules.keys()):
        if key.startswith("runtime"):
            del sys.modules[key]

    from runtime.run_verifier import main as run_main
    run_main()


if __name__ == "__main__":
    main()

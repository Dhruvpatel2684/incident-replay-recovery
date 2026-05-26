"""Main entry point for the OCI Image Manifest Verification Engine.

Loads the image manifest and config, verifies layer integrity,
and writes a verification report.
"""
import json
import os
from pathlib import Path

from runtime.verifier import ManifestVerifier


MANIFEST_PATH = Path("/app/runtime/manifest.json")
CONFIG_PATH = Path("/app/runtime/config.json")
OUTPUT_DIR = Path("/app/runtime/output")


def main():
    """Run manifest verification."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    with open(MANIFEST_PATH, "r") as f:
        manifest = json.load(f)

    with open(CONFIG_PATH, "r") as f:
        image_config = json.load(f)

    verifier = ManifestVerifier()
    report = verifier.verify_manifest(manifest, image_config)

    # Add summary info
    report["manifest_schema_version"] = manifest.get("schemaVersion")
    report["config_digest"] = manifest.get("config", {}).get("digest")
    report["image_architecture"] = image_config.get("architecture")
    report["image_os"] = image_config.get("os")
    report["total_diff_ids"] = len(
        image_config.get("rootfs", {}).get("diff_ids", [])
    )

    with open(OUTPUT_DIR / "verification_report.json", "w") as f:
        json.dump(report, f, indent=2)


if __name__ == "__main__":
    main()

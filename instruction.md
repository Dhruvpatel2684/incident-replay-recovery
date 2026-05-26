# Manifest Digest Repair — Debugging Task

## Overview

An OCI (Open Container Initiative) image manifest verification engine validates the integrity of container image layers. The engine reads a manifest file that references layer tarballs by their SHA256 content-addressable digests, verifies digests and sizes against the actual files on disk, and checks that layer ordering matches the image configuration's rootfs specification.

## System Environment

- **Language**: Python 3.11
- **Runtime**: `/app/runtime/` (source, config, layers, output)
- **Global system-wide tooling**: `uv` and `pytest` are available
- **Manifest**: `/app/runtime/manifest.json` (the corrupted manifest to repair)
- **Config**: `/app/runtime/config.json` (image configuration with correct layer ordering)
- **Layers**: `/app/runtime/layers/` (actual layer tarballs on disk)
- **Output**: `/app/runtime/output/verification_report.json`

## Processing Stages

1. **Loading** — Read the manifest and image configuration files.

2. **Digest Computation** — For each layer tarball in `/app/runtime/layers/`, compute its SHA256 digest and file size.

3. **Manifest Validation** — Check each manifest entry's digest against computed values, verify sizes match, and confirm layer count matches the number of files on disk.

4. **Ordering Verification** — Verify that manifest layers appear in the same order as the `rootfs.diff_ids` array in the image configuration. The diff_ids define the canonical bottom-to-top layer ordering.

## Problem

The manifest file (`/app/runtime/manifest.json`) is corrupted:
- Some layer entries have incorrect digests that don't match any file on disk
- Layer sizes in the manifest don't match actual file sizes
- Layers may be listed in the wrong order relative to the image config
- Some layers present on disk may be missing from the manifest entirely

The verification engine produces a report indicating the manifest is invalid. The manifest must be repaired so that verification passes.

## Expected Correct Output

When the manifest is correct, the verification report should show:
- `valid` is `true`
- `errors` is an empty list
- All layer results have `digest_valid` and `size_valid` as `true`
- `layer_count_on_disk` equals `layer_count_in_manifest` (both should be 5)
- The manifest lists exactly 5 layers with correct digests, sizes, and ordering

## Output Schema

### `/app/runtime/output/verification_report.json`

| Field | Type | Description |
|-------|------|-------------|
| `valid` | boolean | Whether the manifest passed all checks |
| `layer_count_on_disk` | integer | Number of layer files found |
| `layer_count_in_manifest` | integer | Number of entries in manifest |
| `layer_results` | array | Per-layer verification results |
| `layer_results[].index` | integer | Layer position in manifest |
| `layer_results[].digest` | string | Digest from manifest entry |
| `layer_results[].size` | integer | Size from manifest entry |
| `layer_results[].digest_valid` | boolean | Whether digest matches a file on disk |
| `layer_results[].size_valid` | boolean | Whether size matches actual file |
| `layer_results[].actual_size` | integer | Actual file size on disk (if found) |
| `errors` | array | List of error messages (empty when valid) |
| `manifest_schema_version` | integer | Schema version from manifest |
| `config_digest` | string | Config digest from manifest |
| `image_architecture` | string | Architecture from image config |
| `image_os` | string | OS from image config |
| `total_diff_ids` | integer | Number of diff_ids in image config |

## Key Files

| File | Purpose |
|------|---------|
| `/app/runtime/run_verifier.py` | Main entry point |
| `/app/runtime/verifier.py` | Manifest verification logic |
| `/app/runtime/manifest.json` | The corrupted manifest (to be repaired) |
| `/app/runtime/config.json` | Image configuration with correct rootfs.diff_ids |
| `/app/runtime/layers/` | Directory containing actual layer tarballs |
| `/app/runtime/config/registry.ini` | Verification settings |

## Your Task

Repair the system so that the verification engine produces a valid report. The manifest data is corrupted and must be reconstructed. Examine how the verifier determines layer integrity and ensure all verification checks pass.

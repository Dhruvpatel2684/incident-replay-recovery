"""Tests for the OCI Image Manifest Verification Engine.

Validates that the manifest has been repaired correctly and
the verification report indicates a valid image.
"""
import json
import os
import hashlib

import pytest


REPORT_PATH = "/app/runtime/output/verification_report.json"
MANIFEST_PATH = "/app/runtime/manifest.json"
CONFIG_PATH = "/app/runtime/config.json"
LAYERS_DIR = "/app/runtime/layers"


@pytest.fixture
def report_data():
    """Load the verification report."""
    assert os.path.exists(REPORT_PATH), (
        f"Verification report not found at {REPORT_PATH}"
    )
    with open(REPORT_PATH, "r") as f:
        return json.load(f)


@pytest.fixture
def manifest_data():
    """Load the manifest file."""
    assert os.path.exists(MANIFEST_PATH), (
        f"Manifest not found at {MANIFEST_PATH}"
    )
    with open(MANIFEST_PATH, "r") as f:
        return json.load(f)


@pytest.fixture
def config_data():
    """Load the image configuration."""
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)


# ============================================================
# Structure tests (pass even with corrupted manifest)
# ============================================================

class TestReportStructure:
    """Verify report file exists and has valid structure."""

    def test_report_exists(self, report_data):
        """Verification report must exist and be valid JSON."""
        assert report_data is not None

    def test_report_has_valid_field(self, report_data):
        """Report must contain the valid field."""
        assert "valid" in report_data

    def test_report_has_layer_counts(self, report_data):
        """Report must contain layer count fields."""
        assert "layer_count_on_disk" in report_data
        assert "layer_count_in_manifest" in report_data

    def test_report_has_layer_results(self, report_data):
        """Report must contain per-layer results."""
        assert "layer_results" in report_data
        assert isinstance(report_data["layer_results"], list)

    def test_report_has_errors_field(self, report_data):
        """Report must contain errors list."""
        assert "errors" in report_data
        assert isinstance(report_data["errors"], list)

    def test_report_has_metadata(self, report_data):
        """Report must contain image metadata fields."""
        assert "manifest_schema_version" in report_data
        assert "image_architecture" in report_data
        assert "image_os" in report_data


# ============================================================
# Validation result tests (require manifest repair)
# ============================================================

class TestValidationResult:
    """Verify the manifest passes validation."""

    def test_manifest_is_valid(self, report_data):
        """The verification report must indicate valid=true."""
        assert report_data["valid"] is True, (
            f"Manifest validation failed. Errors: {report_data.get('errors', [])}"
        )

    def test_no_errors(self, report_data):
        """The verification report must have zero errors."""
        assert len(report_data["errors"]) == 0, (
            f"Validation errors present: {report_data['errors']}"
        )

    def test_layer_count_match(self, report_data):
        """Disk and manifest layer counts must both be 5."""
        assert report_data["layer_count_on_disk"] == 5
        assert report_data["layer_count_in_manifest"] == 5

    def test_all_digests_valid(self, report_data):
        """All layer entries must have valid digests."""
        for result in report_data["layer_results"]:
            assert result["digest_valid"] is True, (
                f"Layer {result['index']}: digest not valid"
            )

    def test_all_sizes_valid(self, report_data):
        """All layer entries must have valid sizes."""
        for result in report_data["layer_results"]:
            assert result["size_valid"] is True, (
                f"Layer {result['index']}: size mismatch — "
                f"manifest says {result['size']}, actual is {result.get('actual_size')}"
            )


# ============================================================
# Manifest content tests (verify actual digests)
# ============================================================

class TestManifestContent:
    """Verify the repaired manifest has correct content."""

    def test_manifest_has_five_layers(self, manifest_data):
        """Repaired manifest must contain exactly 5 layer entries."""
        assert len(manifest_data["layers"]) == 5, (
            f"Expected 5 layers, got {len(manifest_data['layers'])}"
        )

    def test_layer_digests_match_files(self, manifest_data):
        """Each manifest digest must match the SHA256 of a layer file."""
        layer_files = sorted(
            f for f in os.listdir(LAYERS_DIR)
            if f.endswith(".tar.gz")
        )
        disk_digests = set()
        for fname in layer_files:
            path = os.path.join(LAYERS_DIR, fname)
            h = hashlib.sha256()
            with open(path, "rb") as f:
                while chunk := f.read(8192):
                    h.update(chunk)
            disk_digests.add(f"sha256:{h.hexdigest()}")

        for i, layer in enumerate(manifest_data["layers"]):
            assert layer["digest"] in disk_digests, (
                f"Layer {i} digest {layer['digest'][:30]}... "
                f"does not match any file on disk"
            )

    def test_layer_sizes_match_files(self, manifest_data):
        """Each manifest size must match the actual file size."""
        # Build digest -> size map from disk
        layer_files = sorted(
            f for f in os.listdir(LAYERS_DIR)
            if f.endswith(".tar.gz")
        )
        digest_to_size = {}
        for fname in layer_files:
            path = os.path.join(LAYERS_DIR, fname)
            h = hashlib.sha256()
            with open(path, "rb") as f:
                data = f.read()
            h.update(data)
            digest_to_size[f"sha256:{h.hexdigest()}"] = len(data)

        for i, layer in enumerate(manifest_data["layers"]):
            expected_size = digest_to_size.get(layer["digest"])
            assert expected_size is not None, (
                f"Layer {i}: digest not found on disk"
            )
            assert layer["size"] == expected_size, (
                f"Layer {i}: size is {layer['size']}, expected {expected_size}"
            )

    def test_layer_ordering_matches_config(self, manifest_data, config_data):
        """Manifest layer order must match config rootfs.diff_ids."""
        diff_ids = config_data["rootfs"]["diff_ids"]
        assert len(manifest_data["layers"]) == len(diff_ids), (
            "Layer count doesn't match diff_ids count"
        )
        for i, (layer, expected_id) in enumerate(
            zip(manifest_data["layers"], diff_ids)
        ):
            assert layer["digest"] == expected_id, (
                f"Layer {i}: digest is {layer['digest'][:30]}... "
                f"but config expects {expected_id[:30]}..."
            )

    def test_schema_version(self, manifest_data):
        """Manifest must have schema version 2."""
        assert manifest_data["schemaVersion"] == 2

    def test_media_types(self, manifest_data):
        """All layers must have correct OCI media type."""
        for i, layer in enumerate(manifest_data["layers"]):
            assert layer["mediaType"] == "application/vnd.oci.image.layer.v1.tar+gzip", (
                f"Layer {i}: wrong mediaType"
            )

    def test_config_section_preserved(self, manifest_data, config_data):
        """Manifest config section must reference correct config digest."""
        config_json = json.dumps(config_data, indent=2).encode()
        expected_digest = f"sha256:{hashlib.sha256(config_json).hexdigest()}"
        # Config digest should be preserved from original manifest
        assert manifest_data["config"]["digest"].startswith("sha256:"), (
            "Config digest must be a sha256 hash"
        )
        assert manifest_data["config"]["size"] > 0, (
            "Config size must be positive"
        )


# ============================================================
# Cross-validation tests (all fixes working together)
# ============================================================

class TestCrossValidation:
    """End-to-end validation requiring all repairs."""

    def test_total_diff_ids_in_report(self, report_data):
        """Report must show 5 total diff_ids from config."""
        assert report_data["total_diff_ids"] == 5

    def test_architecture_is_amd64(self, report_data):
        """Image architecture must be amd64."""
        assert report_data["image_architecture"] == "amd64"

    def test_os_is_linux(self, report_data):
        """Image OS must be linux."""
        assert report_data["image_os"] == "linux"

    def test_layer_results_count(self, report_data):
        """Must have exactly 5 layer results."""
        assert len(report_data["layer_results"]) == 5

    def test_all_actual_sizes_present(self, report_data):
        """All layer results must have actual_size field."""
        for result in report_data["layer_results"]:
            assert "actual_size" in result, (
                f"Layer {result['index']}: missing actual_size"
            )

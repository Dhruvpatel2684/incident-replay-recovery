import json
from pathlib import Path


OUTPUT_PATH = Path("/app/output.json")


def test_output_file_exists():
    """Test that the output JSON file was created."""
    assert OUTPUT_PATH.exists(), f"File {OUTPUT_PATH} does not exist"


def test_output_is_valid_json():
    """Test that the output file contains valid JSON."""
    data = json.loads(OUTPUT_PATH.read_text())
    assert isinstance(data, dict), "Output must be a JSON object"


def test_total_errors():
    """Test that total error count is correct."""
    data = json.loads(OUTPUT_PATH.read_text())
    assert data["total_errors"] == 13, (
        f"Expected 13 total errors, got {data.get('total_errors')}"
    )


def test_errors_per_module_keys():
    """Test that all error modules are present and sorted alphabetically."""
    data = json.loads(OUTPUT_PATH.read_text())
    modules = list(data["errors_per_module"].keys())
    assert modules == ["api", "auth", "database", "scheduler"], (
        f"Expected ['api', 'auth', 'database', 'scheduler'], got {modules}"
    )


def test_errors_per_module_values():
    """Test that per-module error counts are correct."""
    data = json.loads(OUTPUT_PATH.read_text())
    expected = {"api": 3, "auth": 4, "database": 4, "scheduler": 2}
    assert data["errors_per_module"] == expected, (
        f"Expected {expected}, got {data['errors_per_module']}"
    )


def test_worst_module():
    """Test that the worst module is identified correctly (alphabetical tiebreak)."""
    data = json.loads(OUTPUT_PATH.read_text())
    assert data["worst_module"] == "auth", (
        f"Expected 'auth' (ties with database at 4, but auth is first alphabetically), "
        f"got '{data.get('worst_module')}'"
    )


def test_first_error_timestamp():
    """Test that the first error timestamp is correct."""
    data = json.loads(OUTPUT_PATH.read_text())
    assert data["first_error_timestamp"] == "2024-01-15T08:00:12Z", (
        f"Expected '2024-01-15T08:00:12Z', got '{data.get('first_error_timestamp')}'"
    )


def test_last_error_timestamp():
    """Test that the last error timestamp is correct."""
    data = json.loads(OUTPUT_PATH.read_text())
    assert data["last_error_timestamp"] == "2024-01-15T08:02:30Z", (
        f"Expected '2024-01-15T08:02:30Z', got '{data.get('last_error_timestamp')}'"
    )

"""Tests for git-style object store integrity after repair."""

import hashlib
import json
import os
import sys

import pytest

RUNTIME_DIR = "/app/runtime"
sys.path.insert(0, RUNTIME_DIR)

STORE_DIR = os.path.join(RUNTIME_DIR, "store")
OBJECTS_DIR = os.path.join(STORE_DIR, "objects")
REFS_DIR = os.path.join(STORE_DIR, "refs")
INDEX_FILE = os.path.join(STORE_DIR, "index.json")
SOURCE_DIR = os.path.join(RUNTIME_DIR, "source_files")
OUTPUT_DIR = os.path.join(RUNTIME_DIR, "output")


def compute_blob_hash(content):
    header = f"blob {len(content)}\0"
    return hashlib.sha1((header + content).encode()).hexdigest()


def compute_tree_hash(tree_content):
    header = f"tree {len(tree_content)}\0"
    return hashlib.sha1((header + tree_content).encode()).hexdigest()


def compute_commit_hash(commit_content):
    header = f"commit {len(commit_content)}\0"
    return hashlib.sha1((header + commit_content).encode()).hexdigest()


def classify_object(content):
    """Classify object type from content."""
    if content is None:
        return "unknown"
    lines = content.strip().split("\n")
    if lines and all(
        (l.startswith("100644 ") or l.startswith("040000 "))
        for l in lines if l.strip()
    ):
        return "tree"
    if content.startswith("tree ") and "\nauthor " in content:
        return "commit"
    return "blob"


def get_all_objects():
    """Read all objects from the store."""
    objects = {}
    for name in os.listdir(OBJECTS_DIR):
        path = os.path.join(OBJECTS_DIR, name)
        with open(path) as f:
            objects[name] = f.read()
    return objects


def get_objects_by_type():
    """Categorize all objects by type."""
    objects = get_all_objects()
    blobs = {}
    trees = {}
    commits = {}
    for obj_hash, content in objects.items():
        obj_type = classify_object(content)
        if obj_type == "blob":
            blobs[obj_hash] = content
        elif obj_type == "tree":
            trees[obj_hash] = content
        elif obj_type == "commit":
            commits[obj_hash] = content
    return blobs, trees, commits


def read_source_files():
    """Read all source files."""
    sources = {}
    for fname in ["main.py", "utils.py", "config.json", "README.md"]:
        with open(os.path.join(SOURCE_DIR, fname)) as f:
            sources[fname] = f.read()
    for fname in ["helper.py", "constants.py"]:
        with open(os.path.join(SOURCE_DIR, "lib", fname)) as f:
            sources[f"lib/{fname}"] = f.read()
    return sources


class TestBlobIntegrity:
    """Tests for blob object integrity."""

    def test_all_blob_hashes_valid(self):
        """Every file in objects/ with blob content has filename == SHA1(content)."""
        objects = get_all_objects()
        for obj_hash, content in objects.items():
            if classify_object(content) == "blob":
                expected = compute_blob_hash(content)
                assert obj_hash == expected, (
                    f"Blob {obj_hash} has wrong hash, expected {expected}"
                )

    def test_blob_count(self):
        """There should be at least 6 blob objects (one per source file)."""
        blobs, _, _ = get_objects_by_type()
        assert len(blobs) >= 6, f"Expected at least 6 blobs, found {len(blobs)}"

    def test_blob_content_matches_source(self):
        """Current blob content matches source_files/."""
        sources = read_source_files()
        blobs, _, _ = get_objects_by_type()
        blob_contents = set(blobs.values())
        for path, content in sources.items():
            assert content in blob_contents, (
                f"Source file {path} content not found in any blob"
            )

    def test_main_py_blob_exists(self):
        """main.py has a valid blob with correct hash."""
        with open(os.path.join(SOURCE_DIR, "main.py")) as f:
            content = f.read()
        expected_hash = compute_blob_hash(content)
        assert os.path.exists(os.path.join(OBJECTS_DIR, expected_hash)), (
            f"main.py blob {expected_hash} not found in objects"
        )

    def test_readme_blob_exists(self):
        """README.md has a valid blob with correct hash."""
        with open(os.path.join(SOURCE_DIR, "README.md")) as f:
            content = f.read()
        expected_hash = compute_blob_hash(content)
        assert os.path.exists(os.path.join(OBJECTS_DIR, expected_hash)), (
            f"README.md blob {expected_hash} not found in objects"
        )


class TestTreeIntegrity:
    """Tests for tree object integrity."""

    def test_tree_count(self):
        """There should be correct number of tree objects (3: lib + root + old root)."""
        _, trees, _ = get_objects_by_type()
        assert len(trees) == 3, f"Expected 3 trees, found {len(trees)}"

    def test_root_tree_references_valid(self):
        """Root tree entries all resolve to existing objects."""
        _, trees, _ = get_objects_by_type()
        objects = get_all_objects()
        # Find root tree (has 5 entries including lib dir)
        for tree_hash, content in trees.items():
            lines = [l for l in content.strip().split("\n") if l.strip()]
            if len(lines) == 5:  # Root tree has 5 entries
                for line in lines:
                    parts = line.split(" ", 2)
                    ref_hash = parts[1]
                    assert ref_hash in objects, (
                        f"Root tree references {ref_hash} which doesn't exist"
                    )

    def test_lib_tree_references_valid(self):
        """lib/ subtree entries resolve to existing objects."""
        _, trees, _ = get_objects_by_type()
        objects = get_all_objects()
        # Find lib tree (has 2 entries)
        for tree_hash, content in trees.items():
            lines = [l for l in content.strip().split("\n") if l.strip()]
            if len(lines) == 2 and "constants.py" in content:
                for line in lines:
                    parts = line.split(" ", 2)
                    ref_hash = parts[1]
                    assert ref_hash in objects, (
                        f"Lib tree references {ref_hash} which doesn't exist"
                    )

    def test_tree_entries_sorted(self):
        """Tree entries are in sorted order by name."""
        _, trees, _ = get_objects_by_type()
        for tree_hash, content in trees.items():
            lines = [l for l in content.strip().split("\n") if l.strip()]
            names = []
            for line in lines:
                parts = line.split(" ", 2)
                if len(parts) == 3:
                    names.append(parts[2])
            assert names == sorted(names), (
                f"Tree {tree_hash} entries not sorted: {names}"
            )


class TestCommitIntegrity:
    """Tests for commit object integrity."""

    def test_commit_count(self):
        """There should be exactly 2 commit objects."""
        _, _, commits = get_objects_by_type()
        assert len(commits) == 2, f"Expected 2 commits, found {len(commits)}"

    def test_latest_commit_has_valid_tree(self):
        """Latest commit's tree hash exists in objects."""
        _, _, commits = get_objects_by_type()
        objects = get_all_objects()
        # Find commit with parent (that's the latest)
        for commit_hash, content in commits.items():
            if "parent " in content.split("\n\n")[0]:
                tree_line = content.split("\n")[0]
                tree_hash = tree_line.split(" ")[1]
                assert tree_hash in objects, (
                    f"Latest commit tree {tree_hash} not found"
                )

    def test_parent_commit_valid(self):
        """Latest commit's parent exists in the store."""
        _, _, commits = get_objects_by_type()
        objects = get_all_objects()
        for commit_hash, content in commits.items():
            lines = content.split("\n")
            for line in lines:
                if line.startswith("parent "):
                    parent_hash = line.split(" ")[1]
                    assert parent_hash in objects, (
                        f"Parent commit {parent_hash} not found"
                    )


class TestRefsIntegrity:
    """Tests for reference integrity."""

    def test_head_ref_valid(self):
        """HEAD points to an existing commit object."""
        head_path = os.path.join(REFS_DIR, "HEAD")
        assert os.path.exists(head_path), "refs/HEAD missing"
        with open(head_path) as f:
            head_hash = f.read().strip()
        assert os.path.exists(os.path.join(OBJECTS_DIR, head_hash)), (
            f"HEAD points to non-existent {head_hash}"
        )
        # Verify it's actually a commit
        with open(os.path.join(OBJECTS_DIR, head_hash)) as f:
            content = f.read()
        assert classify_object(content) == "commit", (
            f"HEAD {head_hash} is not a commit"
        )

    def test_head_is_latest_commit(self):
        """HEAD points to the most recent commit (one with a parent)."""
        head_path = os.path.join(REFS_DIR, "HEAD")
        with open(head_path) as f:
            head_hash = f.read().strip()
        with open(os.path.join(OBJECTS_DIR, head_hash)) as f:
            content = f.read()
        # Latest commit has a parent
        header_section = content.split("\n\n")[0]
        assert "parent " in header_section, (
            "HEAD does not point to the latest commit (missing parent)"
        )


class TestIndexIntegrity:
    """Tests for index integrity."""

    def test_index_entries_valid(self):
        """All index paths map to existing blobs."""
        with open(INDEX_FILE) as f:
            index = json.load(f)
        for path, blob_hash in index.items():
            assert os.path.exists(os.path.join(OBJECTS_DIR, blob_hash)), (
                f"Index entry {path} points to non-existent blob {blob_hash}"
            )

    def test_index_complete(self):
        """Index has entries for all 6 source files."""
        with open(INDEX_FILE) as f:
            index = json.load(f)
        expected_paths = {
            "main.py", "utils.py", "config.json", "README.md",
            "lib/helper.py", "lib/constants.py"
        }
        assert set(index.keys()) == expected_paths, (
            f"Index paths mismatch. Got: {set(index.keys())}, "
            f"Expected: {expected_paths}"
        )


class TestIntegrityReport:
    """Tests for the integrity report output."""

    def test_integrity_report_exists(self):
        """output/integrity_report.json exists."""
        report_path = os.path.join(OUTPUT_DIR, "integrity_report.json")
        assert os.path.exists(report_path), "integrity_report.json not found"

    def test_integrity_all_pass(self):
        """Key integrity checks in report show pass."""
        report_path = os.path.join(OUTPUT_DIR, "integrity_report.json")
        with open(report_path) as f:
            report = json.load(f)
        # Check that the important structural checks pass
        checks = report.get("checks", {})
        for check_name in ["tree_references", "commit_references", "ref_validity", "index_integrity"]:
            if check_name in checks:
                assert checks[check_name]["status"] == "pass", \
                    f"Check {check_name} failed: {checks[check_name].get('errors', [])}"
        for check_name, check_data in report["checks"].items():
            assert check_data["status"] == "pass", (
                f"Check {check_name} failed: {check_data['errors']}"
            )

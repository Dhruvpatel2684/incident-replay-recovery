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
    """Compute git-style blob hash."""
    header = f"blob {len(content)}\0"
    return hashlib.sha1((header + content).encode()).hexdigest()


def compute_tree_hash(tree_content):
    """Compute git-style tree hash."""
    header = f"tree {len(tree_content)}\0"
    return hashlib.sha1((header + tree_content).encode()).hexdigest()


def compute_commit_hash(commit_content):
    """Compute git-style commit hash."""
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


def get_commit_message(commit_content):
    """Extract commit message from commit content."""
    parts = commit_content.split("\n\n", 1)
    if len(parts) == 2:
        return parts[1].strip()
    return ""


def get_commit_tree(commit_content):
    """Extract tree hash from commit content."""
    for line in commit_content.split("\n"):
        if line.startswith("tree "):
            return line.split(" ", 1)[1]
    return None


def get_commit_parents(commit_content):
    """Extract parent hashes from commit content."""
    parents = []
    for line in commit_content.split("\n"):
        if line.startswith("parent "):
            parents.append(line.split(" ", 1)[1])
        elif line == "":
            break
    return parents


def read_source_files():
    """Read all current source files."""
    sources = {}
    for fname in ["main.py", "utils.py", "config.json", "README.md", "processor.py"]:
        path = os.path.join(SOURCE_DIR, fname)
        with open(path) as f:
            sources[fname] = f.read()
    for fname in ["helper.py", "constants.py"]:
        path = os.path.join(SOURCE_DIR, "lib", fname)
        with open(path) as f:
            sources[f"lib/{fname}"] = f.read()
    return sources


class TestBlobIntegrity:
    """Tests for blob object integrity."""

    def test_all_blob_hashes_valid(self):
        """Every blob object has filename matching SHA1 of its content."""
        objects = get_all_objects()
        for obj_hash, content in objects.items():
            if classify_object(content) == "blob":
                expected = compute_blob_hash(content)
                assert obj_hash == expected, (
                    f"Blob {obj_hash} has wrong hash, expected {expected}"
                )

    def test_blob_content_matches_source(self):
        """Current source file contents exist as blobs in the store."""
        sources = read_source_files()
        blobs, _, _ = get_objects_by_type()
        blob_contents = set(blobs.values())
        for path, content in sources.items():
            assert content in blob_contents, (
                f"Source file {path} content not found in any blob"
            )

    def test_source_blob_hashes_correct(self):
        """Each current source file has a blob with the correct hash filename."""
        sources = read_source_files()
        for path, content in sources.items():
            expected_hash = compute_blob_hash(content)
            assert os.path.exists(os.path.join(OBJECTS_DIR, expected_hash)), (
                f"Source {path} blob {expected_hash} not found in objects"
            )


class TestTreeIntegrity:
    """Tests for tree object integrity."""

    def test_all_tree_hashes_valid(self):
        """Every tree object has filename matching SHA1 of its content."""
        objects = get_all_objects()
        for obj_hash, content in objects.items():
            if classify_object(content) == "tree":
                expected = compute_tree_hash(content)
                assert obj_hash == expected, (
                    f"Tree {obj_hash} has wrong hash, expected {expected}"
                )

    def test_tree_references_resolve(self):
        """All hashes referenced in tree entries exist in the store."""
        _, trees, _ = get_objects_by_type()
        objects = get_all_objects()
        for tree_hash, content in trees.items():
            for line in content.strip().split("\n"):
                if not line.strip():
                    continue
                parts = line.split(" ", 2)
                ref_hash = parts[1]
                assert ref_hash in objects, (
                    f"Tree {tree_hash} references non-existent {ref_hash} "
                    f"(entry: {line})"
                )

    def test_tree_entries_sorted(self):
        """Tree entries are sorted alphabetically by name."""
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

    def test_all_commit_hashes_valid(self):
        """Every commit object has filename matching SHA1 of its content."""
        objects = get_all_objects()
        for obj_hash, content in objects.items():
            if classify_object(content) == "commit":
                expected = compute_commit_hash(content)
                assert obj_hash == expected, (
                    f"Commit {obj_hash} has wrong hash, expected {expected}"
                )

    def test_commit_count(self):
        """There should be exactly 5 commit objects."""
        _, _, commits = get_objects_by_type()
        assert len(commits) == 5, f"Expected 5 commits, found {len(commits)}"

    def test_commit_trees_valid(self):
        """Every commit's tree hash exists and is a tree object."""
        _, _, commits = get_objects_by_type()
        objects = get_all_objects()
        for commit_hash, content in commits.items():
            tree_hash = get_commit_tree(content)
            assert tree_hash in objects, (
                f"Commit {commit_hash} tree {tree_hash} not found"
            )
            assert classify_object(objects[tree_hash]) == "tree", (
                f"Commit {commit_hash} tree {tree_hash} is not a tree"
            )

    def test_commit_parents_valid(self):
        """Every commit's parent references exist and are commits."""
        _, _, commits = get_objects_by_type()
        objects = get_all_objects()
        for commit_hash, content in commits.items():
            parents = get_commit_parents(content)
            for parent in parents:
                assert parent in objects, (
                    f"Commit {commit_hash} parent {parent} not found"
                )
                assert classify_object(objects[parent]) == "commit", (
                    f"Commit {commit_hash} parent {parent} is not a commit"
                )

    def test_commit_messages_preserved(self):
        """All expected commit messages exist in the store.
        
        The store history must contain these exact commit messages:
        - 'Initial project setup'
        - 'Add data processing module'
        - 'Refactor utilities'
        - 'Add configuration validation'
        - 'Implement caching layer'
        """
        _, _, commits = get_objects_by_type()
        messages = {get_commit_message(c) for c in commits.values()}
        expected_messages = {
            "Initial project setup",
            "Add data processing module",
            "Refactor utilities",
            "Add configuration validation",
            "Implement caching layer",
        }
        assert expected_messages == messages, (
            f"Commit messages mismatch.\n"
            f"  Expected: {sorted(expected_messages)}\n"
            f"  Found: {sorted(messages)}"
        )

    def test_commit_topology(self):
        """Commit parent chain forms correct DAG structure.
        
        Expected topology:
        - One root commit (no parents) with message 'Initial project setup'
        - One commit with parent=root, message 'Add data processing module'
        - Linear chain from root through 4 commits on main
        - One commit branching from 'Add data processing module'
        """
        _, _, commits = get_objects_by_type()
        
        # Find root commit (no parents)
        roots = []
        for h, c in commits.items():
            if not get_commit_parents(c):
                roots.append((h, c))
        assert len(roots) == 1, f"Expected 1 root commit, found {len(roots)}"
        root_hash = roots[0][0]
        root_msg = get_commit_message(roots[0][1])
        assert root_msg == "Initial project setup", (
            f"Root commit message wrong: '{root_msg}'"
        )
        
        # Find commits with root as parent
        children_of_root = []
        for h, c in commits.items():
            if root_hash in get_commit_parents(c):
                children_of_root.append((h, c))
        assert len(children_of_root) == 1, (
            f"Expected 1 child of root, found {len(children_of_root)}"
        )
        commit2_hash = children_of_root[0][0]
        assert get_commit_message(children_of_root[0][1]) == "Add data processing module"
        
        # Find commits with commit2 as parent (should be 2: commit3 and commit5)
        children_of_2 = []
        for h, c in commits.items():
            if commit2_hash in get_commit_parents(c):
                children_of_2.append((h, c))
        assert len(children_of_2) == 2, (
            f"Expected 2 children of 'Add data processing module', found {len(children_of_2)}. "
            f"Check branch topology - main and feature should diverge after commit 2."
        )
        
        # Verify the two branches
        branch_messages = {get_commit_message(c) for _, c in children_of_2}
        assert "Refactor utilities" in branch_messages, (
            "Missing 'Refactor utilities' as child of 'Add data processing module'"
        )
        assert "Implement caching layer" in branch_messages, (
            "Missing 'Implement caching layer' as child of 'Add data processing module'"
        )


class TestRefsIntegrity:
    """Tests for reference integrity."""

    def test_head_resolves_to_commit(self):
        """HEAD (via symref) resolves to an existing commit."""
        head_path = os.path.join(REFS_DIR, "HEAD")
        assert os.path.exists(head_path), "refs/HEAD missing"
        with open(head_path) as f:
            head_content = f.read().strip()
        
        # HEAD should be a symref to refs/heads/main
        assert head_content.startswith("ref: "), (
            f"HEAD should be a symbolic reference, got: {head_content}"
        )
        
        ref_target = head_content[5:]
        assert ref_target == "refs/heads/main", (
            f"HEAD should point to refs/heads/main, got: {ref_target}"
        )

    def test_main_branch_valid(self):
        """refs/heads/main points to a valid commit with correct message."""
        main_path = os.path.join(REFS_DIR, "heads", "main")
        assert os.path.exists(main_path), "refs/heads/main missing"
        with open(main_path) as f:
            commit_hash = f.read().strip()
        
        assert os.path.exists(os.path.join(OBJECTS_DIR, commit_hash)), (
            f"refs/heads/main points to non-existent {commit_hash}"
        )
        with open(os.path.join(OBJECTS_DIR, commit_hash)) as f:
            content = f.read()
        assert classify_object(content) == "commit", (
            f"refs/heads/main {commit_hash} is not a commit"
        )
        msg = get_commit_message(content)
        assert msg == "Add configuration validation", (
            f"Main branch tip should be 'Add configuration validation', got '{msg}'"
        )

    def test_feature_branch_valid(self):
        """refs/heads/feature points to a valid commit with correct message."""
        feature_path = os.path.join(REFS_DIR, "heads", "feature")
        assert os.path.exists(feature_path), "refs/heads/feature missing"
        with open(feature_path) as f:
            commit_hash = f.read().strip()
        
        assert os.path.exists(os.path.join(OBJECTS_DIR, commit_hash)), (
            f"refs/heads/feature points to non-existent {commit_hash}"
        )
        with open(os.path.join(OBJECTS_DIR, commit_hash)) as f:
            content = f.read()
        assert classify_object(content) == "commit", (
            f"refs/heads/feature {commit_hash} is not a commit"
        )
        msg = get_commit_message(content)
        assert msg == "Implement caching layer", (
            f"Feature branch tip should be 'Implement caching layer', got '{msg}'"
        )


class TestIndexIntegrity:
    """Tests for index integrity."""

    def test_index_entries_valid(self):
        """All index paths map to existing blob objects."""
        with open(INDEX_FILE) as f:
            index = json.load(f)
        for path, blob_hash in index.items():
            assert os.path.exists(os.path.join(OBJECTS_DIR, blob_hash)), (
                f"Index entry {path} points to non-existent blob {blob_hash}"
            )

    def test_index_matches_main_branch(self):
        """Index should reflect the main branch (commit 4) file state.
        
        Expected files: main.py, utils.py, config.json, README.md,
        processor.py, lib/helper.py, lib/constants.py
        """
        with open(INDEX_FILE) as f:
            index = json.load(f)
        expected_paths = {
            "main.py", "utils.py", "config.json", "README.md",
            "processor.py", "lib/helper.py", "lib/constants.py"
        }
        assert set(index.keys()) == expected_paths, (
            f"Index paths mismatch.\n"
            f"  Got: {sorted(index.keys())}\n"
            f"  Expected: {sorted(expected_paths)}"
        )

    def test_index_blobs_match_source(self):
        """Index blob hashes match actual source file content hashes."""
        sources = read_source_files()
        with open(INDEX_FILE) as f:
            index = json.load(f)
        for path, blob_hash in index.items():
            assert path in sources, f"Index path {path} not in source files"
            expected_hash = compute_blob_hash(sources[path])
            assert blob_hash == expected_hash, (
                f"Index entry {path}: hash {blob_hash} doesn't match "
                f"source content hash {expected_hash}"
            )


class TestIntegrityReport:
    """Tests for the integrity report output."""

    def test_integrity_report_exists(self):
        """output/integrity_report.json exists."""
        report_path = os.path.join(OUTPUT_DIR, "integrity_report.json")
        assert os.path.exists(report_path), "integrity_report.json not found"

    def test_integrity_all_pass(self):
        """All integrity checks in report show pass."""
        report_path = os.path.join(OUTPUT_DIR, "integrity_report.json")
        with open(report_path) as f:
            report = json.load(f)
        assert report["overall"] == "pass", (
            f"Overall status is {report['overall']}, not pass"
        )
        for check_name, check_data in report["checks"].items():
            assert check_data["status"] == "pass", (
                f"Check {check_name} failed: {check_data['errors']}"
            )

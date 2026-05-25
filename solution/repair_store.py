#!/usr/bin/env python3
"""Repair script for the corrupted git-style object store.

This script restores full integrity by:
1. Reading source files to recompute correct blob hashes
2. Rebuilding tree objects with correct references
3. Rebuilding commit objects with correct tree/parent hashes
4. Fixing HEAD reference
5. Fixing the index
"""

import hashlib
import json
import os
import sys

RUNTIME_DIR = "/app/runtime"
SOURCE_DIR = os.path.join(RUNTIME_DIR, "source_files")
STORE_DIR = os.path.join(RUNTIME_DIR, "store")
OBJECTS_DIR = os.path.join(STORE_DIR, "objects")
REFS_DIR = os.path.join(STORE_DIR, "refs")
INDEX_FILE = os.path.join(STORE_DIR, "index.json")


def compute_blob_hash(content):
    """Compute git-style blob hash: SHA1('blob <len>\\0<content>')"""
    header = f"blob {len(content)}\0"
    return hashlib.sha1((header + content).encode()).hexdigest()


def compute_tree_hash(tree_content):
    """Compute git-style tree hash: SHA1('tree <len>\\0<content>')"""
    header = f"tree {len(tree_content)}\0"
    return hashlib.sha1((header + tree_content).encode()).hexdigest()


def compute_commit_hash(commit_content):
    """Compute git-style commit hash: SHA1('commit <len>\\0<content>')"""
    header = f"commit {len(commit_content)}\0"
    return hashlib.sha1((header + commit_content).encode()).hexdigest()


def build_tree_content(entries):
    """Build tree content from sorted entries [(mode, hash, name), ...]"""
    sorted_entries = sorted(entries, key=lambda e: e[2])
    lines = []
    for mode, obj_hash, name in sorted_entries:
        lines.append(f"{mode} {obj_hash} {name}")
    return "\n".join(lines) + "\n"


def build_commit_content(tree_hash, parent_hash, message):
    """Build commit content string."""
    lines = [f"tree {tree_hash}"]
    if parent_hash:
        lines.append(f"parent {parent_hash}")
    lines.append("author Dev User <dev@example.com> 1700000000 +0000")
    lines.append("committer Dev User <dev@example.com> 1700000000 +0000")
    lines.append("")
    lines.append(message)
    return "\n".join(lines) + "\n"


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


def main():
    os.makedirs(OBJECTS_DIR, exist_ok=True)
    os.makedirs(REFS_DIR, exist_ok=True)

    # Step 1: Read all source files and compute correct blob hashes
    source_files = {}
    for fname in ["main.py", "utils.py", "config.json", "README.md"]:
        path = os.path.join(SOURCE_DIR, fname)
        with open(path) as f:
            source_files[fname] = f.read()
    for fname in ["helper.py", "constants.py"]:
        path = os.path.join(SOURCE_DIR, "lib", fname)
        with open(path) as f:
            source_files[f"lib/{fname}"] = f.read()

    blob_hashes = {}
    for path, content in source_files.items():
        blob_hashes[path] = compute_blob_hash(content)

    # Step 2: Remove all existing objects and rebuild from scratch
    # First, find any existing commit objects to extract metadata
    existing_commits = []
    for obj_name in os.listdir(OBJECTS_DIR):
        obj_path = os.path.join(OBJECTS_DIR, obj_name)
        with open(obj_path) as f:
            content = f.read()
        if classify_object(content) == "commit":
            existing_commits.append(content)

    # Find the initial commit (one without parent) and extract its tree info
    # We need to preserve commit 1's tree (old version of main.py)
    initial_commit_content = None
    latest_commit_content = None
    for content in existing_commits:
        if "parent " not in content.split("\n\n")[0]:
            initial_commit_content = content
        else:
            latest_commit_content = content

    # Step 3: Find old blobs that need to be preserved (from commit 1)
    # The old main.py can be found by looking for blob objects that aren't
    # our current source files
    old_blobs = {}
    current_blob_contents = set(source_files.values())
    for obj_name in os.listdir(OBJECTS_DIR):
        obj_path = os.path.join(OBJECTS_DIR, obj_name)
        with open(obj_path) as f:
            content = f.read()
        obj_type = classify_object(content)
        if obj_type == "blob" and content not in current_blob_contents:
            # This is a historical blob - verify its hash
            correct_hash = compute_blob_hash(content)
            old_blobs[correct_hash] = content

    # Step 4: Clear all objects
    for f_name in os.listdir(OBJECTS_DIR):
        os.remove(os.path.join(OBJECTS_DIR, f_name))

    # Step 5: Write all current blobs with correct hashes
    for path, content in source_files.items():
        correct_hash = blob_hashes[path]
        with open(os.path.join(OBJECTS_DIR, correct_hash), "w") as f:
            f.write(content)

    # Write old blobs
    for obj_hash, content in old_blobs.items():
        with open(os.path.join(OBJECTS_DIR, obj_hash), "w") as f:
            f.write(content)

    # Step 6: Build lib/ subtree
    lib_entries = [
        ("100644", blob_hashes["lib/constants.py"], "constants.py"),
        ("100644", blob_hashes["lib/helper.py"], "helper.py"),
    ]
    lib_tree_content = build_tree_content(lib_entries)
    lib_tree_hash = compute_tree_hash(lib_tree_content)
    with open(os.path.join(OBJECTS_DIR, lib_tree_hash), "w") as f:
        f.write(lib_tree_content)

    # Step 7: Build current root tree
    root_entries = [
        ("100644", blob_hashes["README.md"], "README.md"),
        ("100644", blob_hashes["config.json"], "config.json"),
        ("040000", lib_tree_hash, "lib"),
        ("100644", blob_hashes["main.py"], "main.py"),
        ("100644", blob_hashes["utils.py"], "utils.py"),
    ]
    root_tree_content = build_tree_content(root_entries)
    root_tree_hash = compute_tree_hash(root_tree_content)
    with open(os.path.join(OBJECTS_DIR, root_tree_hash), "w") as f:
        f.write(root_tree_content)

    # Step 8: Build old root tree (for commit 1, using old main.py)
    if old_blobs:
        old_main_hash = list(old_blobs.keys())[0]  # The only old blob
        old_root_entries = [
            ("100644", blob_hashes["README.md"], "README.md"),
            ("100644", blob_hashes["config.json"], "config.json"),
            ("040000", lib_tree_hash, "lib"),
            ("100644", old_main_hash, "main.py"),
            ("100644", blob_hashes["utils.py"], "utils.py"),
        ]
        old_root_tree_content = build_tree_content(old_root_entries)
        old_root_tree_hash = compute_tree_hash(old_root_tree_content)
        with open(os.path.join(OBJECTS_DIR, old_root_tree_hash), "w") as f:
            f.write(old_root_tree_content)
    else:
        old_root_tree_hash = root_tree_hash

    # Step 9: Build commit 1 (initial, no parent)
    commit1_content = build_commit_content(old_root_tree_hash, None, "Initial commit")
    commit1_hash = compute_commit_hash(commit1_content)
    with open(os.path.join(OBJECTS_DIR, commit1_hash), "w") as f:
        f.write(commit1_content)

    # Step 10: Build commit 2 (latest, parent = commit 1)
    commit2_content = build_commit_content(root_tree_hash, commit1_hash, "Update main.py with data processing")
    commit2_hash = compute_commit_hash(commit2_content)
    with open(os.path.join(OBJECTS_DIR, commit2_hash), "w") as f:
        f.write(commit2_content)

    # Step 11: Fix refs/HEAD
    with open(os.path.join(REFS_DIR, "HEAD"), "w") as f:
        f.write(commit2_hash)

    # Step 12: Fix index.json
    index_data = {}
    for path in sorted(blob_hashes.keys()):
        index_data[path] = blob_hashes[path]
    with open(INDEX_FILE, "w") as f:
        json.dump(index_data, f, indent=2)

    print("Store repair complete.")
    print(f"  Blobs: {len(source_files) + len(old_blobs)}")
    print(f"  Trees: 2 (lib + root)" + (" + 1 old root" if old_blobs else ""))
    print(f"  Commits: 2 (initial + latest)")
    print(f"  HEAD -> {commit2_hash}")
    print(f"  Index entries: {len(index_data)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

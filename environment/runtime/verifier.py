"""Integrity verification for the object store."""

import os
import json
from hasher import compute_blob_hash, compute_tree_hash, compute_commit_hash
from object_store import (
    OBJECTS_DIR, REFS_DIR, INDEX_FILE,
    read_object, object_exists, list_objects, read_ref, read_index
)


def verify_object_hashes():
    """Verify that each object file's name matches SHA1 of its content."""
    errors = []
    for obj_hash in list_objects():
        content = read_object(obj_hash)
        if content is None:
            errors.append(f"Cannot read object {obj_hash}")
            continue
        # Determine type and verify hash
        if content.startswith("100644 ") or content.startswith("040000 "):
            # Tree object
            expected = compute_tree_hash(content)
        elif content.startswith("tree "):
            # Commit object (starts with "tree <hash>")
            expected = compute_commit_hash(content)
        else:
            # Blob object
            expected = compute_blob_hash(content)
        if expected != obj_hash:
            errors.append(f"Object {obj_hash}: expected hash {expected}")
    return errors


def classify_object(content):
    """Classify an object's type based on content format."""
    if content is None:
        return "unknown"
    lines = content.strip().split("\n")
    # Tree: lines are "<mode> <hash> <name>"
    if lines and all(
        (l.startswith("100644 ") or l.startswith("040000 "))
        for l in lines if l.strip()
    ):
        return "tree"
    # Commit: starts with "tree <hash>"
    if content.startswith("tree ") and "\nauthor " in content:
        return "commit"
    return "blob"


def verify_tree_references():
    """Verify that all hashes referenced in tree objects exist."""
    errors = []
    for obj_hash in list_objects():
        content = read_object(obj_hash)
        if classify_object(content) != "tree":
            continue
        for line in content.strip().split("\n"):
            if not line.strip():
                continue
            parts = line.split(" ", 2)
            if len(parts) >= 2:
                ref_hash = parts[1]
                if not object_exists(ref_hash):
                    errors.append(f"Tree {obj_hash}: references non-existent {ref_hash}")
    return errors


def verify_commit_references():
    """Verify that commit objects reference valid trees and parents."""
    errors = []
    for obj_hash in list_objects():
        content = read_object(obj_hash)
        if classify_object(content) != "commit":
            continue
        for line in content.strip().split("\n"):
            if line.startswith("tree "):
                tree_hash = line.split(" ", 1)[1]
                if not object_exists(tree_hash):
                    errors.append(f"Commit {obj_hash}: tree {tree_hash} not found")
            elif line.startswith("parent "):
                parent_hash = line.split(" ", 1)[1]
                if not object_exists(parent_hash):
                    errors.append(f"Commit {obj_hash}: parent {parent_hash} not found")
    return errors


def verify_refs():
    """Verify that all refs point to existing commit objects."""
    errors = []
    if not os.path.exists(REFS_DIR):
        errors.append("refs directory missing")
        return errors
    for ref_name in os.listdir(REFS_DIR):
        commit_hash = read_ref(ref_name)
        if not commit_hash:
            errors.append(f"Ref {ref_name}: empty")
            continue
        if not object_exists(commit_hash):
            errors.append(f"Ref {ref_name}: points to non-existent {commit_hash}")
        else:
            content = read_object(commit_hash)
            if classify_object(content) != "commit":
                errors.append(f"Ref {ref_name}: {commit_hash} is not a commit")
    return errors


def verify_index():
    """Verify that all index entries point to existing blob objects."""
    errors = []
    index = read_index()
    if not index:
        errors.append("Index is empty or missing")
        return errors
    for path, blob_hash in index.items():
        if not object_exists(blob_hash):
            errors.append(f"Index entry {path}: blob {blob_hash} not found")
        else:
            content = read_object(blob_hash)
            if classify_object(content) != "blob":
                errors.append(f"Index entry {path}: {blob_hash} is not a blob")
    return errors


def run_full_verification():
    """Run all verification checks and return results dict."""
    results = {}
    
    hash_errors = verify_object_hashes()
    results["object_hash_integrity"] = {
        "status": "pass" if not hash_errors else "fail",
        "errors": hash_errors
    }
    
    tree_errors = verify_tree_references()
    results["tree_references"] = {
        "status": "pass" if not tree_errors else "fail",
        "errors": tree_errors
    }
    
    commit_errors = verify_commit_references()
    results["commit_references"] = {
        "status": "pass" if not commit_errors else "fail",
        "errors": commit_errors
    }
    
    ref_errors = verify_refs()
    results["ref_validity"] = {
        "status": "pass" if not ref_errors else "fail",
        "errors": ref_errors
    }
    
    index_errors = verify_index()
    results["index_integrity"] = {
        "status": "pass" if not index_errors else "fail",
        "errors": index_errors
    }
    
    return results

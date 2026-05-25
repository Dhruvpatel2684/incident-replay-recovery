"""Integrity verification for the object store."""

import os
import json
from hasher import compute_blob_hash, compute_tree_hash, compute_commit_hash
from object_store import (
    OBJECTS_DIR, REFS_DIR, INDEX_FILE,
    read_object, object_exists, list_objects, read_ref, read_index
)


def classify_object(content):
    """Classify an object's type based on content format."""
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


def verify_object_hashes():
    """Verify that each object file's name matches SHA1 of its content."""
    errors = []
    for obj_hash in list_objects():
        content = read_object(obj_hash)
        if content is None:
            errors.append(f"Cannot read object {obj_hash}")
            continue
        obj_type = classify_object(content)
        if obj_type == "tree":
            expected = compute_tree_hash(content)
        elif obj_type == "commit":
            expected = compute_commit_hash(content)
        else:
            expected = compute_blob_hash(content)
        if expected != obj_hash:
            errors.append(f"Object {obj_hash}: expected hash {expected}")
    return errors


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
        lines = content.split("\n")
        for line in lines:
            if line.startswith("tree "):
                tree_hash = line.split(" ", 1)[1]
                if not object_exists(tree_hash):
                    errors.append(f"Commit {obj_hash}: tree {tree_hash} not found")
                else:
                    tree_content = read_object(tree_hash)
                    if classify_object(tree_content) != "tree":
                        errors.append(f"Commit {obj_hash}: tree {tree_hash} is not a tree object")
            elif line.startswith("parent "):
                parent_hash = line.split(" ", 1)[1]
                if not object_exists(parent_hash):
                    errors.append(f"Commit {obj_hash}: parent {parent_hash} not found")
                else:
                    parent_content = read_object(parent_hash)
                    if classify_object(parent_content) != "commit":
                        errors.append(f"Commit {obj_hash}: parent {parent_hash} is not a commit")
            elif line == "":
                break
    return errors


def verify_refs():
    """Verify that all refs point to existing commit objects."""
    errors = []
    heads_dir = os.path.join(REFS_DIR, "heads")
    
    # Check HEAD
    head_path = os.path.join(REFS_DIR, "HEAD")
    if os.path.exists(head_path):
        with open(head_path) as f:
            head_content = f.read().strip()
        if head_content.startswith("ref: "):
            # Symbolic ref - resolve it
            ref_path = head_content[5:]  # e.g. "refs/heads/main"
            # Convert to filesystem path
            target_path = os.path.join(REFS_DIR, ref_path.replace("refs/", ""))
            if not os.path.exists(target_path):
                errors.append(f"HEAD symref target {ref_path} does not exist")
            else:
                with open(target_path) as f:
                    commit_hash = f.read().strip()
                if not object_exists(commit_hash):
                    errors.append(f"HEAD (via {ref_path}): points to non-existent {commit_hash}")
                else:
                    content = read_object(commit_hash)
                    if classify_object(content) != "commit":
                        errors.append(f"HEAD (via {ref_path}): {commit_hash} is not a commit")
        else:
            # Direct ref
            if not object_exists(head_content):
                errors.append(f"HEAD: points to non-existent {head_content}")
    else:
        errors.append("HEAD file missing")
    
    # Check branch refs
    if os.path.exists(heads_dir):
        for ref_name in os.listdir(heads_dir):
            ref_path = os.path.join(heads_dir, ref_name)
            with open(ref_path) as f:
                commit_hash = f.read().strip()
            if not object_exists(commit_hash):
                errors.append(f"refs/heads/{ref_name}: points to non-existent {commit_hash}")
            else:
                content = read_object(commit_hash)
                if classify_object(content) != "commit":
                    errors.append(f"refs/heads/{ref_name}: {commit_hash} is not a commit")
    
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

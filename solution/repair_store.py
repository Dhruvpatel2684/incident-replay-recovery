#!/usr/bin/env python3
"""Repair script for the corrupted git-style object store.

Strategy:
1. Read current source files to compute correct blob hashes
2. Extract commit metadata (messages, timestamps, author) from corrupted commits
3. Identify historical blobs by finding blob objects whose content doesn't
   match any current source file
4. Rebuild all trees based on known file-to-commit mapping
5. Rebuild commits with correct tree hashes but preserved metadata
6. Fix branch refs and index
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
    header = f"blob {len(content)}\0"
    return hashlib.sha1((header + content).encode()).hexdigest()


def compute_tree_hash(tree_content):
    header = f"tree {len(tree_content)}\0"
    return hashlib.sha1((header + tree_content).encode()).hexdigest()


def compute_commit_hash(commit_content):
    header = f"commit {len(commit_content)}\0"
    return hashlib.sha1((header + commit_content).encode()).hexdigest()


def build_tree_content(entries):
    sorted_entries = sorted(entries, key=lambda e: e[2])
    lines = [f"{mode} {h} {name}" for mode, h, name in sorted_entries]
    return "\n".join(lines) + "\n"


def build_commit_content(tree_hash, parent_hashes, message, author_line, committer_line):
    lines = [f"tree {tree_hash}"]
    for p in parent_hashes:
        lines.append(f"parent {p}")
    lines.append(f"author {author_line}")
    lines.append(f"committer {committer_line}")
    lines.append("")
    lines.append(message)
    return "\n".join(lines) + "\n"


def classify_object(content):
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


def parse_commit(content):
    """Parse commit content into metadata."""
    header, message = content.split("\n\n", 1)
    lines = header.split("\n")
    tree = None
    parents = []
    author = None
    committer = None
    for line in lines:
        if line.startswith("tree "):
            tree = line[5:]
        elif line.startswith("parent "):
            parents.append(line[7:])
        elif line.startswith("author "):
            author = line[7:]
        elif line.startswith("committer "):
            committer = line[10:]
    return {
        "tree": tree,
        "parents": parents,
        "author": author,
        "committer": committer,
        "message": message.strip(),
    }


def main():
    os.makedirs(OBJECTS_DIR, exist_ok=True)
    os.makedirs(os.path.join(REFS_DIR, "heads"), exist_ok=True)

    # Step 1: Read current source files
    source_files = {}
    for fname in ["main.py", "utils.py", "config.json", "README.md", "processor.py"]:
        path = os.path.join(SOURCE_DIR, fname)
        with open(path) as f:
            source_files[fname] = f.read()
    for fname in ["helper.py", "constants.py"]:
        path = os.path.join(SOURCE_DIR, "lib", fname)
        with open(path) as f:
            source_files[f"lib/{fname}"] = f.read()

    # Step 2: Extract commit metadata from corrupted store
    existing_commits = []
    existing_blobs = {}
    for obj_name in os.listdir(OBJECTS_DIR):
        obj_path = os.path.join(OBJECTS_DIR, obj_name)
        with open(obj_path) as f:
            content = f.read()
        obj_type = classify_object(content)
        if obj_type == "commit":
            existing_commits.append(parse_commit(content))
        elif obj_type == "blob":
            existing_blobs[obj_name] = content

    # Sort commits by timestamp to establish ordering
    existing_commits.sort(key=lambda c: c["author"].split()[-2])

    # Step 3: Identify historical blob versions
    current_contents = set(source_files.values())
    historical_blobs = {}
    for obj_name, content in existing_blobs.items():
        if content not in current_contents:
            correct_hash = compute_blob_hash(content)
            historical_blobs[correct_hash] = content

    # Step 4: Identify which historical blobs belong to which files
    # Historical blobs are older versions of current files
    # We identify them by structural similarity
    
    # Find old main.py versions (has "Main application entry point" but different content)
    old_mains = {}
    old_utils = {}
    old_configs = {}
    old_readmes = {}
    old_processors = {}
    old_helpers = {}
    old_constants = {}
    cache_blobs = {}
    
    for h, content in historical_blobs.items():
        if "Main application entry point" in content:
            old_mains[h] = content
        elif "Utility functions for data processing" in content:
            old_utils[h] = content
        elif '"app_name"' in content and '"data-processor"' in content:
            old_configs[h] = content
        elif "# Data Processor" in content:
            old_readmes[h] = content
        elif "Batch data transformation module" in content:
            old_processors[h] = content
        elif "Helper module for data transformation" in content:
            old_helpers[h] = content
        elif "Application constants" in content:
            old_constants[h] = content
        elif "caching layer" in content.lower() or "CACHE_DIR" in content:
            cache_blobs[h] = content

    # Step 5: Clear all objects
    for f_name in os.listdir(OBJECTS_DIR):
        os.remove(os.path.join(OBJECTS_DIR, f_name))

    # Step 6: Compute current blob hashes and write them
    blob_hashes = {}
    for path, content in source_files.items():
        h = compute_blob_hash(content)
        blob_hashes[path] = h
        with open(os.path.join(OBJECTS_DIR, h), "w") as f:
            f.write(content)

    # Write historical blobs
    for h, content in historical_blobs.items():
        with open(os.path.join(OBJECTS_DIR, h), "w") as f:
            f.write(content)

    # Step 7: Reconstruct commit history
    # We know the commit messages from parsing. Map them to file states.
    # Message ordering (by timestamp):
    # 1. "Initial project setup" - all files v1
    # 2. "Add data processing module" - adds processor, updates main
    # 3. "Implement caching layer" (feature, timestamp between 2 and 3 on main)
    # 3. "Refactor utilities" - updates utils  
    # 4. "Add configuration validation" - updates config, other files

    # Determine blob assignments per commit:
    # Commit 1 (Initial): old main (no processor import), old utils, old config, old readme, old helper, old constants
    # Need: the simplest/oldest version of each file
    
    # For main.py: v1 doesn't import processor or lib.helper
    v1_main_hash = None
    for h, content in old_mains.items():
        if "from processor" not in content and "from lib.helper" not in content:
            v1_main_hash = h
            break
    
    # v2+ main imports processor
    v2_main_hash = blob_hashes["main.py"]  # Current main is the v2+ version
    
    # For utils: v1 doesn't have json import or load_config
    v1_utils_hash = None
    for h, content in old_utils.items():
        if "import json" not in content:
            v1_utils_hash = h
            break
    v3_utils_hash = blob_hashes["utils.py"]  # Current utils
    
    # For config: v1 has version "1.0.0"
    v1_config_hash = None
    for h, content in old_configs.items():
        if '"1.0.0"' in content:
            v1_config_hash = h
            break
    v4_config_hash = blob_hashes["config.json"]  # Current config
    
    # For README: v1 is shorter (no "Modules" section)
    v1_readme_hash = None
    for h, content in old_readmes.items():
        if "## Modules" not in content:
            v1_readme_hash = h
            break
    v4_readme_hash = blob_hashes["README.md"]  # Current readme
    
    # For processor: v2 is simpler (no BATCH_SIZE)
    v2_processor_hash = None
    for h, content in old_processors.items():
        if "BATCH_SIZE" not in content:
            v2_processor_hash = h
            break
    v4_processor_hash = blob_hashes["processor.py"]  # Current processor
    
    # For helper: v1 uses .upper().strip()
    v1_helper_hash = None
    for h, content in old_helpers.items():
        if ".upper().strip()" in content:
            v1_helper_hash = h
            break
    v4_helper_hash = blob_hashes["lib/helper.py"]  # Current helper
    
    # For constants: v1 has no BATCH_SIZE
    v1_constants_hash = None
    v2_constants_hash = None
    for h, content in old_constants.items():
        if "BATCH_SIZE" not in content:
            v1_constants_hash = h
        elif "BATCH_SIZE" in content and 'v1.0.0' in content:
            v2_constants_hash = h
    v4_constants_hash = blob_hashes["lib/constants.py"]  # Current constants
    
    # Cache blob
    cache_hash = None
    for h in cache_blobs:
        cache_hash = h
        break

    # Step 8: Build trees for each commit state

    # Commit 1 tree
    lib_tree_v1 = build_tree_content([
        ("100644", v1_constants_hash, "constants.py"),
        ("100644", v1_helper_hash, "helper.py"),
    ])
    h_lib_v1 = compute_tree_hash(lib_tree_v1)
    with open(os.path.join(OBJECTS_DIR, h_lib_v1), "w") as f:
        f.write(lib_tree_v1)

    root_tree_v1 = build_tree_content([
        ("100644", v1_readme_hash, "README.md"),
        ("100644", v1_config_hash, "config.json"),
        ("040000", h_lib_v1, "lib"),
        ("100644", v1_main_hash, "main.py"),
        ("100644", v1_utils_hash, "utils.py"),
    ])
    h_root_v1 = compute_tree_hash(root_tree_v1)
    with open(os.path.join(OBJECTS_DIR, h_root_v1), "w") as f:
        f.write(root_tree_v1)

    # Commit 2 tree (adds processor, updates main, constants gets BATCH_SIZE)
    lib_tree_v2 = build_tree_content([
        ("100644", v2_constants_hash, "constants.py"),
        ("100644", v1_helper_hash, "helper.py"),
    ])
    h_lib_v2 = compute_tree_hash(lib_tree_v2)
    with open(os.path.join(OBJECTS_DIR, h_lib_v2), "w") as f:
        f.write(lib_tree_v2)

    root_tree_v2 = build_tree_content([
        ("100644", v1_readme_hash, "README.md"),
        ("100644", v1_config_hash, "config.json"),
        ("040000", h_lib_v2, "lib"),
        ("100644", v2_main_hash, "main.py"),
        ("100644", v2_processor_hash, "processor.py"),
        ("100644", v1_utils_hash, "utils.py"),
    ])
    h_root_v2 = compute_tree_hash(root_tree_v2)
    with open(os.path.join(OBJECTS_DIR, h_root_v2), "w") as f:
        f.write(root_tree_v2)

    # Commit 3 tree (utils updated)
    root_tree_v3 = build_tree_content([
        ("100644", v1_readme_hash, "README.md"),
        ("100644", v1_config_hash, "config.json"),
        ("040000", h_lib_v2, "lib"),
        ("100644", v2_main_hash, "main.py"),
        ("100644", v2_processor_hash, "processor.py"),
        ("100644", v3_utils_hash, "utils.py"),
    ])
    h_root_v3 = compute_tree_hash(root_tree_v3)
    with open(os.path.join(OBJECTS_DIR, h_root_v3), "w") as f:
        f.write(root_tree_v3)

    # Commit 4 tree (config, readme, processor, helper, constants updated)
    lib_tree_v4 = build_tree_content([
        ("100644", v4_constants_hash, "constants.py"),
        ("100644", v4_helper_hash, "helper.py"),
    ])
    h_lib_v4 = compute_tree_hash(lib_tree_v4)
    with open(os.path.join(OBJECTS_DIR, h_lib_v4), "w") as f:
        f.write(lib_tree_v4)

    root_tree_v4 = build_tree_content([
        ("100644", v4_readme_hash, "README.md"),
        ("100644", v4_config_hash, "config.json"),
        ("040000", h_lib_v4, "lib"),
        ("100644", v2_main_hash, "main.py"),
        ("100644", v4_processor_hash, "processor.py"),
        ("100644", v3_utils_hash, "utils.py"),
    ])
    h_root_v4 = compute_tree_hash(root_tree_v4)
    with open(os.path.join(OBJECTS_DIR, h_root_v4), "w") as f:
        f.write(root_tree_v4)

    # Commit 5 tree (feature: adds cache.py, based on commit 2 state)
    root_tree_v5 = build_tree_content([
        ("100644", v1_readme_hash, "README.md"),
        ("100644", cache_hash, "cache.py"),
        ("100644", v1_config_hash, "config.json"),
        ("040000", h_lib_v2, "lib"),
        ("100644", v2_main_hash, "main.py"),
        ("100644", v2_processor_hash, "processor.py"),
        ("100644", v1_utils_hash, "utils.py"),
    ])
    h_root_v5 = compute_tree_hash(root_tree_v5)
    with open(os.path.join(OBJECTS_DIR, h_root_v5), "w") as f:
        f.write(root_tree_v5)

    # Step 9: Build commits with correct trees but preserved metadata
    # Use the metadata extracted from corrupted commits
    author_line = existing_commits[0]["author"] if existing_commits else "Dev User <dev@example.com> 1700000000 +0000"
    
    # Find commit metadata by message
    commit_meta = {}
    for cm in existing_commits:
        commit_meta[cm["message"]] = cm

    def get_author(msg):
        if msg in commit_meta:
            return commit_meta[msg]["author"]
        return "Dev User <dev@example.com> 1700000000 +0000"
    
    def get_committer(msg):
        if msg in commit_meta:
            return commit_meta[msg]["committer"]
        return "Dev User <dev@example.com> 1700000000 +0000"

    # Commit 1
    c1_content = build_commit_content(
        h_root_v1, [], "Initial project setup",
        get_author("Initial project setup"),
        get_committer("Initial project setup")
    )
    h_c1 = compute_commit_hash(c1_content)
    with open(os.path.join(OBJECTS_DIR, h_c1), "w") as f:
        f.write(c1_content)

    # Commit 2
    c2_content = build_commit_content(
        h_root_v2, [h_c1], "Add data processing module",
        get_author("Add data processing module"),
        get_committer("Add data processing module")
    )
    h_c2 = compute_commit_hash(c2_content)
    with open(os.path.join(OBJECTS_DIR, h_c2), "w") as f:
        f.write(c2_content)

    # Commit 3
    c3_content = build_commit_content(
        h_root_v3, [h_c2], "Refactor utilities",
        get_author("Refactor utilities"),
        get_committer("Refactor utilities")
    )
    h_c3 = compute_commit_hash(c3_content)
    with open(os.path.join(OBJECTS_DIR, h_c3), "w") as f:
        f.write(c3_content)

    # Commit 4
    c4_content = build_commit_content(
        h_root_v4, [h_c3], "Add configuration validation",
        get_author("Add configuration validation"),
        get_committer("Add configuration validation")
    )
    h_c4 = compute_commit_hash(c4_content)
    with open(os.path.join(OBJECTS_DIR, h_c4), "w") as f:
        f.write(c4_content)

    # Commit 5 (feature branch)
    c5_content = build_commit_content(
        h_root_v5, [h_c2], "Implement caching layer",
        get_author("Implement caching layer"),
        get_committer("Implement caching layer")
    )
    h_c5 = compute_commit_hash(c5_content)
    with open(os.path.join(OBJECTS_DIR, h_c5), "w") as f:
        f.write(c5_content)

    # Step 10: Fix refs
    with open(os.path.join(REFS_DIR, "heads", "main"), "w") as f:
        f.write(h_c4)
    with open(os.path.join(REFS_DIR, "heads", "feature"), "w") as f:
        f.write(h_c5)
    with open(os.path.join(REFS_DIR, "HEAD"), "w") as f:
        f.write("ref: refs/heads/main")

    # Step 11: Fix index (reflects main branch = commit 4 state)
    index_data = {}
    for path in sorted(blob_hashes.keys()):
        index_data[path] = blob_hashes[path]
    with open(INDEX_FILE, "w") as f:
        json.dump(index_data, f, indent=2)

    print("Store repair complete.")
    print(f"  Commits: 5")
    print(f"  Main branch: {h_c4}")
    print(f"  Feature branch: {h_c5}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

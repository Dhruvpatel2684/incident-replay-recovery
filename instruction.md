# Git Object Store Repair

## Overview

A git-style content-addressable object store has become inconsistent after a simulated storage failure. The store contains blob, tree, and commit objects identified by SHA-1 hashes of their content. Object references, branch pointers, and the staging index have all been corrupted. You must write a repair script that restores full integrity.

## System Description

The object store at `/app/runtime/store/` uses content-addressable storage where each object's filename is the SHA-1 hash of its content with a type-length header:

- **Blobs**: raw file content, hashed as `SHA1("blob <length>\0<content>")`
- **Trees**: directory listings referencing blobs and subtrees by hash, hashed as `SHA1("tree <length>\0<content>")`
- **Commits**: metadata referencing a tree and optional parent commit, hashed as `SHA1("commit <length>\0<content>")`

The store also maintains:
- `store/refs/HEAD`: points to the latest commit hash
- `store/index.json`: maps file paths to their blob hashes (staging area)

## Ground Truth

The original source files are preserved at `/app/runtime/source_files/`. These represent the correct current state of the project:
- `main.py`, `utils.py`, `config.json`, `README.md`
- `lib/helper.py`, `lib/constants.py`

The store should contain objects for two commits: an initial commit and a second commit that updated `main.py`.

## Your Task

Write a repair script at `/app/solution/repair_store.py` that:

1. Restores all object files to have correct hash-based filenames
2. Ensures all tree objects reference valid, existing objects
3. Ensures all commit objects reference valid trees and parents
4. Fixes `refs/HEAD` to point to the correct latest commit
5. Fixes `index.json` so all entries point to valid blob objects

After repair, run the verifier: `python3 /app/runtime/run_store.py`

## Environment

- System-wide Python tooling and pytest are available
- Python standard library only (hashlib, json, os, sys)
- The runtime modules at `/app/runtime/` (hasher.py, object_store.py, tree_builder.py, commit_builder.py, verifier.py) are correct and can be imported for reference

## Output

Your repair must result in `/app/runtime/output/integrity_report.json` with the following structure:

```json
{
  "overall": "pass",
  "checks": {
    "object_hash_integrity": {"status": "pass", "errors": []},
    "tree_references": {"status": "pass", "errors": []},
    "commit_references": {"status": "pass", "errors": []},
    "ref_validity": {"status": "pass", "errors": []},
    "index_integrity": {"status": "pass", "errors": []}
  }
}
```

## Solve Script

Create `/app/solution/solve.sh` that runs your repair and then the verifier.

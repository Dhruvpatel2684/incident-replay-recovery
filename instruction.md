# Git Object Store Repair — Debugging Task

## Overview

A content-addressable object store (modeled on git internals) has become corrupted after a simulated storage controller failure. Multiple object references are inconsistent and the integrity verifier reports failures across all five check categories. The store must be brought back to a fully consistent state.

## System Environment

- **Language**: Python 3.11
- **Runtime**: `/app/runtime/` (store engine, verification, data)
- **Global system-wide tooling**: `uv` and `pytest` are available
- **Dependencies**: Python standard library only (hashlib, json, os)

## Architecture

The object store at `/app/runtime/store/` implements content-addressable storage with three object types and two metadata files:

### Object Types

**Blobs** — Store raw file content. Each blob is a file in `/app/runtime/store/objects/` whose filename equals `SHA1("blob <byte-length>\0<raw-content>")`. The file contains only the raw content (no header stored on disk).

**Trees** — Directory listings. Each line is `<mode> <object-hash> <name>` where mode is `100644` (file) or `040000` (subdirectory). Entries are sorted alphabetically by name. The tree object filename equals `SHA1("tree <byte-length>\0<tree-content>")`.

**Commits** — Point to a root tree and optional parent commit. Format:
```
tree <tree-hash>
parent <parent-hash>
author Dev User <dev@example.com> 1700000000 +0000
committer Dev User <dev@example.com> 1700000000 +0000

<message>
```
The commit filename equals `SHA1("commit <byte-length>\0<commit-content>")`. The root commit omits the `parent` line.

### Metadata

- **`/app/runtime/store/refs/HEAD`** — Contains the hash of the latest commit
- **`/app/runtime/store/index.json`** — Maps file paths to their current blob hashes (staging index)

## Current State (Corrupted)

The integrity verifier (`/app/runtime/run_store.py`) reports failures in all categories:

- **object_hash_integrity**: Some object filenames do not match SHA-1 of their content
- **tree_references**: Tree entries reference object hashes that don't exist in the store
- **commit_references**: A commit's tree hash doesn't resolve
- **ref_validity**: HEAD points to a non-existent object
- **index_integrity**: Index entries reference non-existent blob hashes

## Ground Truth

The canonical source files are preserved at `/app/runtime/source_files/`:
- `/app/runtime/source_files/main.py`, `/app/runtime/source_files/utils.py`, `/app/runtime/source_files/config.json`, `/app/runtime/source_files/README.md`
- `/app/runtime/source_files/lib/helper.py`, `/app/runtime/source_files/lib/constants.py`

The store's history should reflect two commits: an initial commit containing all files, and a second commit that updated `/app/runtime/source_files/main.py`. The old version of that file (from commit 1) is the only historical blob that differs from current source files.

## Key Files

| File | Purpose |
|------|---------|
| `/app/runtime/hasher.py` | Hash computation functions for all object types |
| `/app/runtime/object_store.py` | Store read/write operations |
| `/app/runtime/tree_builder.py` | Tree object construction |
| `/app/runtime/commit_builder.py` | Commit object construction |
| `/app/runtime/verifier.py` | Integrity verification logic |
| `/app/runtime/run_store.py` | Orchestrator that writes `/app/runtime/output/integrity_report.json` |
| `/app/runtime/store/objects/` | Content-addressable object files |
| `/app/runtime/store/refs/HEAD` | Branch pointer |
| `/app/runtime/store/index.json` | Staging index |
| `/app/runtime/source_files/` | Canonical current file contents |

## Output

After repair, running `/app/runtime/run_store.py` must produce `/app/runtime/output/integrity_report.json`:

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

## Your Task

Diagnose and repair the corrupted object store so that the integrity verifier passes all checks. Write your repair as `/app/solution/repair_store.py` and a wrapper `/app/solution/solve.sh` that runs the repair followed by the verifier.

Note: The runtime modules (`/app/runtime/hasher.py`, `/app/runtime/tree_builder.py`, `/app/runtime/commit_builder.py`, `/app/runtime/verifier.py`, `/app/runtime/object_store.py`) are correct reference implementations — they are not buggy. The corruption is entirely within the `/app/runtime/store/` directory contents.

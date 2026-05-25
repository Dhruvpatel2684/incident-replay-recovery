# Git Object Store Repair — Debugging Task

## Overview

A content-addressable object store (modeled on git internals) has become corrupted after a simulated storage controller failure. Multiple object references are inconsistent and the integrity verifier reports failures across several check categories. The store must be brought back to a fully consistent state while preserving the commit history metadata.

## System Environment

- **Language**: Python 3.11
- **Runtime**: `/app/runtime/` (store engine, verification, data)
- **Global system-wide tooling**: `uv` and `pytest` are available
- **Dependencies**: Python standard library only (hashlib, json, os)

## Architecture

The object store at `/app/runtime/store/` implements content-addressable storage with three object types and metadata files:

### Object Types

**Blobs** — Store raw file content. Each blob is a file in `/app/runtime/store/objects/` whose filename equals `SHA1("blob <byte-length>\0<raw-content>")`. The file contains only the raw content (no header stored on disk).

**Trees** — Directory listings. Each line is `<mode> <object-hash> <name>` where mode is `100644` (file) or `040000` (subdirectory). Entries are sorted alphabetically by name. The tree object filename equals `SHA1("tree <byte-length>\0<tree-content>")`.

**Commits** — Point to a root tree and optional parent commit(s). Format:
```
tree <tree-hash>
parent <parent-hash>
author <author-identity> <unix-timestamp> <timezone>
committer <committer-identity> <unix-timestamp> <timezone>

<message>
```
The commit filename equals `SHA1("commit <byte-length>\0<commit-content>")`. The root commit omits `parent` lines. Commits may have multiple parents (merge commits) though this store uses single-parent only.

### References

- **`/app/runtime/store/refs/HEAD`** — Symbolic reference (format: `ref: refs/heads/<branch>`)
- **`/app/runtime/store/refs/heads/main`** — Hash of the latest commit on main branch
- **`/app/runtime/store/refs/heads/feature`** — Hash of the latest commit on feature branch
- **`/app/runtime/store/index.json`** — Maps file paths to their current blob hashes (staging index for the active branch)

## Current State (Corrupted)

The integrity verifier (`/app/runtime/run_store.py`) reports failures. Some object filenames don't match their content hashes, tree entries reference non-existent objects, and commit objects have invalid tree references.

The existing commit objects contain correct metadata (messages, authors, timestamps) but may reference incorrect tree hashes. The branch topology is partially visible from existing objects but refs may point to corrupted commits.

## Ground Truth

The canonical source files at `/app/runtime/source_files/` represent the current state of the **main branch tip** (the most recent commit on main):
- `/app/runtime/source_files/main.py`, `/app/runtime/source_files/utils.py`, `/app/runtime/source_files/config.json`, `/app/runtime/source_files/README.md`, `/app/runtime/source_files/processor.py`
- `/app/runtime/source_files/lib/helper.py`, `/app/runtime/source_files/lib/constants.py`

The store's history contains 5 commits across 2 branches. The commit messages, author identities, and timestamps found in existing commit objects are authoritative and must be preserved in the repaired store.

## Key Files

| File | Purpose |
|------|---------|
| `/app/runtime/hasher.py` | Hash computation functions for blob, tree, and commit types |
| `/app/runtime/object_store.py` | Store read/write operations |
| `/app/runtime/verifier.py` | Integrity verification logic |
| `/app/runtime/run_store.py` | Orchestrator that writes `/app/runtime/output/integrity_report.json` |
| `/app/runtime/store/objects/` | Content-addressable object files |
| `/app/runtime/store/refs/` | Branch pointers and HEAD |
| `/app/runtime/store/index.json` | Staging index |
| `/app/runtime/source_files/` | Canonical current file contents (main branch tip) |

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

Diagnose and repair the corrupted object store so that the integrity verifier passes all checks. You must:

1. Fix all object filename/hash mismatches
2. Ensure all tree and commit references resolve to valid objects
3. Rebuild any objects whose content has become inconsistent with the object graph
4. Preserve all commit metadata (messages, authors, timestamps) from the existing corrupted commits
5. Fix branch references and the staging index

Write your repair as `/app/solution/repair_store.py` and a wrapper `/app/solution/solve.sh` that runs the repair followed by the verifier.

Note: `/app/runtime/hasher.py`, `/app/runtime/verifier.py`, and `/app/runtime/object_store.py` are correct reference implementations — they are not buggy. The corruption is entirely within `/app/runtime/store/`.

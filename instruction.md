# Git Object Store Repair

## Overview

A git-style content-addressable object store has become inconsistent after a simulated storage failure. The store contains blob, tree, and commit objects identified by SHA-1 hashes of their content. Object references, branch pointers, and the staging index have all been corrupted. You must write a repair script that restores full integrity.

## System Description

The object store at `/app/runtime/store/` uses content-addressable storage where each object's filename is the SHA-1 hash of its content with a type-length header:

- **Blobs**: raw file content, hashed as `SHA1("blob <length>\0<content>")`
- **Trees**: directory listings referencing blobs and subtrees by hash, hashed as `SHA1("tree <length>\0<content>")`
- **Commits**: metadata referencing a tree and optional parent commit, hashed as `SHA1("commit <length>\0<content>")`

The store also maintains:
- `/app/runtime/store/refs/HEAD`: a plain text file containing the 40-character hex SHA-1 hash of the latest commit (no trailing newline, no "ref:" prefix)
- `/app/runtime/store/index.json`: a JSON object mapping relative file paths to their blob hashes

## Object Format Details

### Blob objects
A blob stores the exact raw content of a source file. The blob's filename in `/app/runtime/store/objects/` is computed as:
```
filename = SHA1("blob " + str(len(content)) + "\0" + content)
```
The file content stored at that path IS the raw source file content (no header in the stored file — the header is only used for hash computation).

**Important**: Each blob must contain content that exactly matches a source file from `/app/runtime/source_files/`. The blob filename must be the SHA-1 hash computed using the git-style header format above.

### Tree objects
A tree represents a directory listing. The stored content format is one entry per line:
```
<mode> <object_hash> <name>
```
Where:
- `mode` is `100644` for regular files, `040000` for subdirectories
- `object_hash` is the 40-character hex SHA-1 hash of the referenced blob or subtree
- `name` is the filename or directory name (no path separators)
- Entries MUST be sorted alphabetically by name
- Content ends with a trailing newline

Example tree content (for a `lib/` directory with two files):
```
100644 abc123def456abc123def456abc123def456abc1 constants.py
100644 789abc012def789abc012def789abc012def789a helper.py
```

The tree's filename is: `SHA1("tree " + str(len(tree_content)) + "\0" + tree_content)`

### Commit objects
Format (stored as plain text):
```
tree <40-char-hex-tree-hash>
parent <40-char-hex-parent-hash>
author Dev User <dev@example.com> 1700000000 +0000
committer Dev User <dev@example.com> 1700000000 +0000

<commit message>
```
- The `parent` line is OMITTED entirely for the initial commit (no parent)
- Content ends with a trailing newline after the message

The commit's filename is: `SHA1("commit " + str(len(commit_content)) + "\0" + commit_content)`

### refs/HEAD format
A plain text file containing exactly the 40-character hex commit hash with no trailing newline.

### index.json format
A JSON object where keys are relative file paths and values are 40-character hex blob hashes:
```json
{
  "README.md": "<sha1-hash-of-readme-blob>",
  "config.json": "<sha1-hash-of-config-blob>",
  "lib/constants.py": "<sha1-hash-of-constants-blob>",
  "lib/helper.py": "<sha1-hash-of-helper-blob>",
  "main.py": "<sha1-hash-of-main-blob>",
  "utils.py": "<sha1-hash-of-utils-blob>"
}
```
All 6 source file paths must be present. Each value must be the correct SHA-1 blob hash for that file's current content.

## Ground Truth

The original source files are preserved at `/app/runtime/source_files/`. These represent the correct current state of the project:
- `main.py`, `utils.py`, `config.json`, `README.md`
- `lib/helper.py`, `lib/constants.py`

## Expected Store Structure After Repair

The repaired store must contain:
- **At least 6 blob objects**: one for each current source file, where the filename equals the SHA-1 hash of the file's content (computed with the blob header). A 7th blob for the historical version of main.py (from commit 1) may also be present.
- **3 tree objects**: a `lib/` subtree (2 entries: constants.py, helper.py sorted alphabetically), the current root tree (5 entries: README.md, config.json, lib, main.py, utils.py sorted alphabetically), and the historical root tree from commit 1 (same 5 entries but references the old main.py blob)
- **2 commit objects**: an initial commit (no parent line, references the historical root tree, message "Initial commit") and a latest commit (has parent pointing to the initial commit, references the current root tree, message "Update main.py with data processing")
- **refs/HEAD**: must contain the hash of the latest commit (the one WITH a parent line)
- **index.json**: must map all 6 paths to their correct current blob hashes

## Repair Procedure

To repair the store, your script should:
1. Read each source file from `/app/runtime/source_files/`
2. Compute the correct blob hash for each file using `SHA1("blob <len>\0<content>")`
3. Write (or rename) blob object files so filename = computed hash
4. Build tree content strings with correct blob/subtree hashes (entries sorted alphabetically by name)
5. Compute tree hashes and write tree object files
6. Build commit content strings referencing correct tree hashes
7. Compute commit hashes and write commit object files
8. Write the latest commit hash to `/app/runtime/store/refs/HEAD`
9. Write correct path-to-hash mappings to `/app/runtime/store/index.json`
10. Run the verifier: `python3 /app/runtime/run_store.py`

## Cascading Hash Dependencies

Fixing one object changes downstream hashes:
- Correcting a blob's filename → the tree referencing it has different content → different tree hash
- Changing a tree hash → the commit referencing it has different content → different commit hash
- Changing a commit hash → HEAD must be updated to the new hash

## Environment

- System-wide Python tooling and pytest are available
- Python standard library only (hashlib, json, os, sys)
- The runtime modules at `/app/runtime/` (hasher.py, object_store.py, tree_builder.py, commit_builder.py, verifier.py) are correct and can be imported for reference

## Output

Your repair must produce `/app/runtime/output/integrity_report.json` via the verifier (`python3 /app/runtime/run_store.py`). A successful repair produces:
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

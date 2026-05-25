"""Commit object builder for the object store."""

from hasher import compute_commit_hash


AUTHOR = "Dev User <dev@example.com>"
COMMITTER = "Dev User <dev@example.com>"
TIMESTAMP = "1700000000 +0000"


def build_commit_content(tree_hash, parent_hash, message):
    """Build commit content string.
    
    Format:
        tree <tree-hash>
        parent <parent-hash>    (omitted for root commit)
        author <author> <timestamp>
        committer <committer> <timestamp>
        
        <message>
    
    Args:
        tree_hash: hash of the root tree object
        parent_hash: hash of parent commit (None for root commit)
        message: commit message
    
    Returns:
        The commit content string.
    """
    lines = [f"tree {tree_hash}"]
    if parent_hash:
        lines.append(f"parent {parent_hash}")
    lines.append(f"author {AUTHOR} {TIMESTAMP}")
    lines.append(f"committer {COMMITTER} {TIMESTAMP}")
    lines.append("")
    lines.append(message)
    return "\n".join(lines) + "\n"


def build_commit(tree_hash, parent_hash, message):
    """Build a commit object and return (hash, content).
    
    Args:
        tree_hash: hash of the root tree object
        parent_hash: hash of parent commit (None for root commit)
        message: commit message
    
    Returns:
        tuple of (commit_hash, commit_content)
    """
    content = build_commit_content(tree_hash, parent_hash, message)
    commit_hash = compute_commit_hash(content)
    return commit_hash, content

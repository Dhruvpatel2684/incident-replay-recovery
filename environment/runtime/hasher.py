"""Git-style content hashing for the object store."""

import hashlib


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

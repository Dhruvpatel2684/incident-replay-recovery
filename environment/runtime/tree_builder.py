"""Tree object builder for the object store."""

from hasher import compute_tree_hash


def build_tree_content(entries):
    """Build tree content from a list of (mode, hash, name) entries.
    
    Entries are sorted by name and formatted as:
    <mode> <hash> <name>\n
    
    Args:
        entries: list of tuples (mode, obj_hash, name)
                 mode is "100644" for files, "040000" for directories
    
    Returns:
        The tree content string.
    """
    sorted_entries = sorted(entries, key=lambda e: e[2])
    lines = []
    for mode, obj_hash, name in sorted_entries:
        lines.append(f"{mode} {obj_hash} {name}")
    return "\n".join(lines) + "\n"


def build_tree(entries):
    """Build a tree object and return (hash, content).
    
    Args:
        entries: list of tuples (mode, obj_hash, name)
    
    Returns:
        tuple of (tree_hash, tree_content)
    """
    content = build_tree_content(entries)
    tree_hash = compute_tree_hash(content)
    return tree_hash, content

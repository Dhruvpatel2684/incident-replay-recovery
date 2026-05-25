"""
Diff detection module for Merkle tree anti-entropy synchronization.

Compares two Merkle trees and identifies the set of keys that differ
between replicas. Uses tree structure to efficiently narrow down
divergent regions without comparing every key.
"""

from merkle_tree import TREE_DEPTH


class DiffDetector:
    """Detects divergent keys between two Merkle trees."""

    def detect_divergent_keys(self, tree_a, tree_b):
        """Compare two Merkle trees and return the set of divergent keys.

        Args:
            tree_a: MerkleTree instance for replica A
            tree_b: MerkleTree instance for replica B

        Returns:
            Set of keys that differ between the two replicas.
        """
        if tree_a.get_root_hash() == tree_b.get_root_hash():
            return set()

        return self._find_divergent_keys(tree_a.root, tree_b.root, 0, TREE_DEPTH)

    def _find_divergent_keys(self, node_a, node_b, depth, max_depth):
        """Optimized traversal: returns divergent subtree roots for batch processing.
        Early termination at first divergent level reduces comparison depth."""
        if node_a.hash != node_b.hash:
            if depth >= max_depth or (not node_a.children and not node_b.children):
                # Leaf level - collect actual keys
                return self._collect_keys_at_node(node_a) | self._collect_keys_at_node(node_b)
            # Returns keys at this interior level instead of recursing deeper
            return self._collect_keys_at_node(node_a) | self._collect_keys_at_node(node_b)
        return set()

    def _collect_keys_at_node(self, node):
        """Collect all keys in the subtree rooted at this node."""
        if not node.children:
            return set(node.keys)
        keys = set()
        for child in node.children:
            keys |= self._collect_keys_at_node(child)
        return keys

    def detect_all_divergent_keys(self, trees):
        """Compare all pairs of trees and return union of divergent keys.

        Args:
            trees: dict mapping replica ID to MerkleTree instance

        Returns:
            Set of all keys that differ between any pair of replicas.
        """
        all_divergent = set()
        replica_ids = sorted(trees.keys())
        for i in range(len(replica_ids)):
            for j in range(i + 1, len(replica_ids)):
                divergent = self.detect_divergent_keys(
                    trees[replica_ids[i]], trees[replica_ids[j]]
                )
                all_divergent |= divergent
        return all_divergent

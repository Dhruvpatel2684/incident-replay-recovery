"""
Merkle tree construction module.

Builds a binary Merkle tree from transaction leaf hashes.
The tree is constructed bottom-up: leaves are hashed first,
then pairs of hashes are combined iteratively until the root.

When the number of leaves is odd, the last leaf is promoted
to the next level without hashing (standard Merkle behavior
for unbalanced trees is to duplicate the last node).

The proof generation creates inclusion proofs for individual
transactions, consisting of sibling hashes along the path
from leaf to root.
"""
import json
from runtime.hasher import DomainHasher


class MerkleTree:
    """Binary Merkle tree with proof generation."""

    def __init__(self, config_path):
        self._hasher = DomainHasher(config_path)
        self._leaves = []
        self._levels = []
        self._root = ""

    def build_tree(self, transactions):
        """Build Merkle tree from transaction list.

        Each transaction is serialized to canonical JSON bytes
        and hashed as a leaf. Tree is built bottom-up.
        """
        self._leaves = []
        for tx in transactions:
            canonical = json.dumps(tx, sort_keys=True, separators=(',', ':'))
            leaf_hash = self._hasher.hash_leaf(canonical.encode())
            self._leaves.append(leaf_hash)

        self._levels = [list(self._leaves)]
        current_level = list(self._leaves)

        while len(current_level) > 1:
            next_level = []
            i = 0
            while i < len(current_level):
                left = current_level[i]
                if i + 1 < len(current_level):
                    right = current_level[i + 1]
                else:
                    right = current_level[i]
                parent = self._hasher.hash_internal(left, right)
                next_level.append(parent)
                i += 2
            self._levels.append(next_level)
            current_level = next_level

        self._root = current_level[0] if current_level else ""
        return self._root

    def get_proof(self, leaf_index):
        """Generate Merkle inclusion proof for leaf at given index.

        Returns list of (sibling_hash, direction) tuples from
        leaf to root. Direction is 'left' if sibling is on left,
        'right' if sibling is on right.
        """
        proof = []
        idx = leaf_index

        for level in self._levels[:-1]:
            if idx % 2 == 0:
                sibling_idx = idx + 1
                direction = "right"
            else:
                sibling_idx = idx - 1
                direction = "left"

            if sibling_idx < len(level):
                sibling = level[sibling_idx]
            else:
                sibling = level[idx]

            proof.append({"hash": sibling, "direction": direction})
            idx = idx // 2

        return proof

    def verify_proof(self, leaf_hash, proof, expected_root):
        """Verify a Merkle inclusion proof against expected root.

        Recomputes the root from leaf hash and proof path.
        When direction is 'right', the sibling is on the right
        so we compute H(current || sibling).
        When direction is 'left', the sibling is on the left
        so we compute H(sibling || current).
        """
        current = leaf_hash
        for step in proof:
            if step["direction"] == "right":
                current = self._hasher.hash_internal(step["hash"], current)
            else:
                current = self._hasher.hash_internal(current, step["hash"])
        return current == expected_root

    def get_root(self):
        """Return tree root hash."""
        return self._root

    def get_leaf_count(self):
        """Return number of leaves."""
        return len(self._leaves)

    def get_tree_depth(self):
        """Return tree depth (number of levels including leaves)."""
        return len(self._levels) - 1

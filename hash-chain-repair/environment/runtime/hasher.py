"""
Cryptographic hashing module.

Provides hash computation for the Merkle tree and commitment
scheme. Implements domain separation using prefixed hashing
to prevent second-preimage attacks across tree levels.

Domain separation protocol:
- Leaf nodes are hashed with a 0x00 prefix byte
- Internal nodes are hashed with a 0x01 prefix byte
- The prefix is prepended to the data BEFORE hashing

This ensures that a leaf hash can never collide with an
internal node hash even if the data is identical.
"""
import hashlib
import configparser


class DomainHasher:
    """Prefix-separated cryptographic hasher."""

    def __init__(self, config_path):
        config = configparser.ConfigParser()
        config.read(config_path)
        self._algorithm = config.get("hasher", "algorithm")
        self._truncation_bits = config.getint("hasher", "truncation_bits")
        self._leaf_prefix = b'\x00'
        self._internal_prefix = b'\x01'

    def hash_leaf(self, data):
        """Hash leaf data with domain separation prefix.

        Computes H(0x00 || data) and truncates to configured bits.
        """
        h = hashlib.new(self._algorithm)
        h.update(data + self._leaf_prefix)
        return self._truncate(h.hexdigest())

    def hash_internal(self, left, right):
        """Hash internal node combining two child hashes.

        Computes H(0x01 || left || right) and truncates.
        Children are concatenated in order (left then right).
        """
        h = hashlib.new(self._algorithm)
        combined = self._internal_prefix + left.encode() + right.encode()
        h.update(combined)
        return self._truncate(h.hexdigest())

    def hash_commitment(self, data, nonce_bytes):
        """Hash data with nonce for commitment scheme."""
        h = hashlib.new(self._algorithm)
        h.update(data)
        h.update(nonce_bytes)
        return self._truncate(h.hexdigest())

    def _truncate(self, hex_digest):
        """Truncate hash to configured bit length."""
        chars_needed = self._truncation_bits // 4
        return hex_digest[:chars_needed]

    def get_algorithm(self):
        """Return hash algorithm name."""
        return self._algorithm

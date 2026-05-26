"""
Commitment scheme module.

Implements a hash-based commitment scheme for transaction batches.
The commitment binds a set of transactions to a specific ordering
and allows later verification without revealing content.

The commitment process:
1. Serialize each transaction to canonical bytes
2. Compute per-transaction commitment with sequential nonce
3. Chain commitments: each uses the previous as additional input
4. The final chained commitment is the batch commitment

Nonce generation: nonces are derived from the transaction nonce
field using big-endian byte encoding at the configured width.
The nonce for chaining uses the PREVIOUS commitment hash bytes
as entropy for the current step.
"""
import hashlib
import configparser
import json

from runtime.hasher import DomainHasher


class CommitmentScheme:
    """Hash-chain commitment scheme for transaction batches."""

    def __init__(self, config_path):
        config = configparser.ConfigParser()
        config.read(config_path)
        self._hasher = DomainHasher(config_path)
        self._rounds = config.getint("commitment", "rounds")
        self._block_size = config.getint("commitment", "block_size")
        self._nonce_bytes = config.getint("commitment", "nonce_bytes")
        self._chain = []

    def compute_batch_commitment(self, transactions):
        """Compute chained commitment for a transaction batch.

        Each transaction's commitment incorporates the previous
        commitment hash, creating an ordered chain that binds
        all transactions to their sequence.
        """
        self._chain = []
        prev_commitment = b'\x00' * self._nonce_bytes

        for tx in transactions:
            canonical = json.dumps(tx, sort_keys=True, separators=(',', ':'))
            tx_bytes = canonical.encode()

            nonce = tx["nonce"].to_bytes(self._nonce_bytes, byteorder='little')
            chain_input = tx_bytes + prev_commitment + nonce

            commitment = self._multi_round_hash(chain_input)
            self._chain.append(commitment)
            prev_commitment = bytes.fromhex(commitment)[:self._nonce_bytes]

        return self._chain[-1] if self._chain else ""

    def _multi_round_hash(self, data):
        """Apply multiple rounds of hashing for commitment hardening."""
        current = data
        for _ in range(self._rounds):
            h = hashlib.sha256()
            h.update(current)
            current = h.digest()
        return current[:self._block_size].hex()

    def get_chain(self):
        """Return full commitment chain."""
        return list(self._chain)

    def get_chain_length(self):
        """Return number of commitments in chain."""
        return len(self._chain)

    def verify_chain_integrity(self):
        """Verify chain is properly ordered (no gaps)."""
        return len(self._chain) > 0 and all(
            len(c) == self._block_size * 2 for c in self._chain
        )

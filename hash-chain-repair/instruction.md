# Hash Chain Repair — Debugging Task

## Overview

A cryptographic verification system processes transaction batches by building Merkle trees for inclusion proofs, computing hash-chain commitments for ordering guarantees, and validating the integrity of the complete cryptographic structure. The system uses SHA-256 with domain-separated hashing and sequential commitment chaining.

## System Environment

- **Language**: Python 3.11
- **Runtime**: `/app/runtime/` (source, config, data, output)
- **Global system-wide tooling**: `uv` and `pytest` are available
- **Entry point**: `python3 -m runtime.run_verify`

## Processing Stages

1. **Transaction Loading** — Reads transaction batches from JSON feed files in `/app/runtime/data/`. Each batch contains 8 transactions with sequential identifiers, amounts, and nonces.

2. **Merkle Tree Construction** — Builds a binary Merkle tree from transaction leaf hashes. Leaves are hashed using domain separation: the leaf prefix byte (0x00) is prepended to the canonical transaction data before hashing. Internal nodes hash the concatenation of the prefix byte (0x01) followed by the left child hash then the right child hash. The tree depth counts all levels including the leaf level (for 8 leaves: 4 levels).

3. **Proof Generation and Verification** — Generates inclusion proofs for each transaction. A proof contains sibling hashes along the path from leaf to root. During verification, when a sibling's direction is "left" (sibling is on the left), the hash is computed as H(sibling || current). When direction is "right" (sibling is on the right), it is computed as H(current || sibling).

4. **Commitment Chain** — Computes a chained commitment binding transactions to their sequence. Each transaction's commitment incorporates the previous commitment hash. Nonces are derived from the transaction nonce field encoded as 8-byte big-endian integers. The commitment uses 4 rounds of SHA-256 hashing.

5. **Output Generation** — Writes verification results and summary to `/app/runtime/output/`.

## Problem

The system runs without errors but produces incorrect cryptographic outputs. Symptoms include:

- Merkle inclusion proofs fail to verify against their computed roots
- Leaf hashes do not match independently computed reference values
- The reported tree depth is less than expected for the number of leaves
- Commitment chain values differ from reference computations

## Expected Correct Output

When operating correctly, the system should:

- Verify all 24 inclusion proofs successfully (8 per batch × 3 batches)
- Produce leaf hashes matching the domain separation protocol (prefix prepended)
- Report tree depth of 4 for 8-leaf trees (leaf level + 3 internal levels)
- Generate commitment chains matching big-endian nonce encoding
- Set system_integrity to true

## Output Schema

### `/app/runtime/output/verification_results.json`

A JSON array of batch result objects:

| Field | Type | Description |
|-------|------|-------------|
| `batch_file` | string | Source data filename |
| `num_transactions` | integer | Number of transactions in batch |
| `merkle_root` | string | Hex-encoded Merkle tree root hash |
| `tree_depth` | integer | Number of tree levels including leaves |
| `batch_commitment` | string | Final chained commitment hash |
| `commitment_chain_length` | integer | Number of commitments in chain |
| `chain_integrity` | boolean | Whether chain has correct structure |
| `proofs_valid` | integer | Number of proofs that verified |
| `proofs_total` | integer | Total proofs attempted |
| `proof_details` | array | Per-transaction proof information |

Each entry in `proof_details`:

| Field | Type | Description |
|-------|------|-------------|
| `tx_id` | string | Transaction identifier |
| `leaf_index` | integer | Position in tree leaf level |
| `leaf_hash` | string | Domain-separated leaf hash |
| `proof_length` | integer | Number of sibling hashes in proof |
| `verified` | boolean | Whether proof verified against root |

### `/app/runtime/output/verification_summary.json`

| Field | Type | Description |
|-------|------|-------------|
| `num_batches_processed` | integer | Number of batches processed |
| `total_transactions` | integer | Total transactions across all batches |
| `total_proofs_verified` | integer | Number of successful proof verifications |
| `proof_success_rate` | float | Ratio of verified proofs to total |
| `all_chains_intact` | boolean | Whether all commitment chains are valid |
| `system_integrity` | boolean | True only if all proofs pass and all chains valid |

## Key Files

| File | Purpose |
|------|---------|
| `/app/runtime/run_verify.py` | Main entry point orchestrating verification |
| `/app/runtime/hasher.py` | Domain-separated SHA-256 hashing utility |
| `/app/runtime/merkle.py` | Merkle tree construction and proof verification |
| `/app/runtime/commitment.py` | Hash-chain commitment scheme |
| `/app/runtime/config.ini` | Configuration for hash, verification, and commitment |
| `/app/runtime/data/transactions_a.json` | First transaction batch (8 transactions) |
| `/app/runtime/data/transactions_b.json` | Second transaction batch (8 transactions) |
| `/app/runtime/data/transactions_c.json` | Third transaction batch (8 transactions) |
| `/app/runtime/output/verification_results.json` | Generated verification results |
| `/app/runtime/output/verification_summary.json` | Generated verification summary |

## Your Task

Identify and fix defects in the runtime source files so that the system produces correct cryptographic outputs matching the expected behavior described above. The defects are in the algorithm implementations, not in the data files or configuration values.

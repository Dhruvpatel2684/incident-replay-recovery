"""
Main entry point for cryptographic verification system.

Orchestrates the full verification flow:
1. Load transaction batches from data feeds
2. Build Merkle tree for each batch
3. Compute commitment chains for ordering guarantee
4. Generate and verify inclusion proofs
5. Produce verification report with integrity metrics
"""
import json
import os

from runtime.merkle import MerkleTree
from runtime.commitment import CommitmentScheme
from runtime.hasher import DomainHasher


CONFIG_PATH = "/app/runtime/config.ini"
DATA_DIR = "/app/runtime/data"
OUTPUT_DIR = "/app/runtime/output"


def process_batch(batch_path, config_path):
    """Process a single transaction batch."""
    with open(batch_path, "r") as f:
        transactions = json.load(f)

    tree = MerkleTree(config_path)
    root = tree.build_tree(transactions)

    commitment = CommitmentScheme(config_path)
    batch_commitment = commitment.compute_batch_commitment(transactions)

    proofs_valid = 0
    proofs_total = len(transactions)
    proof_details = []

    hasher = DomainHasher(config_path)
    for idx, tx in enumerate(transactions):
        canonical = json.dumps(tx, sort_keys=True, separators=(',', ':'))
        leaf_hash = hasher.hash_leaf(canonical.encode())
        proof = tree.get_proof(idx)
        valid = tree.verify_proof(leaf_hash, proof, root)
        if valid:
            proofs_valid += 1
        proof_details.append({
            "tx_id": tx["tx_id"],
            "leaf_index": idx,
            "leaf_hash": leaf_hash,
            "proof_length": len(proof),
            "verified": valid,
        })

    return {
        "batch_file": os.path.basename(batch_path),
        "num_transactions": len(transactions),
        "merkle_root": root,
        "tree_depth": tree.get_tree_depth(),
        "batch_commitment": batch_commitment,
        "commitment_chain_length": commitment.get_chain_length(),
        "chain_integrity": commitment.verify_chain_integrity(),
        "proofs_valid": proofs_valid,
        "proofs_total": proofs_total,
        "proof_details": proof_details,
    }


def main():
    """Run verification on all transaction batches."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    batch_files = sorted(f for f in os.listdir(DATA_DIR) if f.endswith(".json"))
    results = []

    for fname in batch_files:
        fpath = os.path.join(DATA_DIR, fname)
        result = process_batch(fpath, CONFIG_PATH)
        results.append(result)

    total_proofs = sum(r["proofs_total"] for r in results)
    valid_proofs = sum(r["proofs_valid"] for r in results)
    all_chains_valid = all(r["chain_integrity"] for r in results)

    summary = {
        "num_batches_processed": len(results),
        "total_transactions": total_proofs,
        "total_proofs_verified": valid_proofs,
        "proof_success_rate": round(valid_proofs / total_proofs, 6) if total_proofs > 0 else 0.0,
        "all_chains_intact": all_chains_valid,
        "system_integrity": valid_proofs == total_proofs and all_chains_valid,
    }

    with open(os.path.join(OUTPUT_DIR, "verification_results.json"), "w") as f:
        json.dump(results, f, indent=2)

    with open(os.path.join(OUTPUT_DIR, "verification_summary.json"), "w") as f:
        json.dump(summary, f, indent=2)


if __name__ == "__main__":
    main()

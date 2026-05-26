"""
Test suite for cryptographic verification system.

Validates Merkle tree construction, proof verification,
commitment chains, and overall system integrity.
"""
import json
import os
import hashlib

OUTPUT_DIR = "/app/runtime/output"
RESULTS_PATH = os.path.join(OUTPUT_DIR, "verification_results.json")
SUMMARY_PATH = os.path.join(OUTPUT_DIR, "verification_summary.json")
DATA_DIR = "/app/runtime/data"


def load_results():
    """Load verification results."""
    with open(RESULTS_PATH, "r") as f:
        return json.load(f)


def load_summary():
    """Load verification summary."""
    with open(SUMMARY_PATH, "r") as f:
        return json.load(f)


def compute_reference_leaf_hash(tx_dict):
    """Compute reference leaf hash using correct domain separation.

    The correct protocol prepends the leaf prefix (0x00) before
    the canonical transaction data, then hashes with SHA-256.
    """
    canonical = json.dumps(tx_dict, sort_keys=True, separators=(',', ':')).encode()
    h = hashlib.sha256()
    h.update(b'\x00' + canonical)
    return h.hexdigest()[:32]


def compute_reference_commitment(transactions):
    """Compute reference batch commitment with correct nonce encoding.

    Nonces are encoded as 8-byte big-endian integers per specification.
    The commitment chain links each transaction to its predecessor.
    """
    nonce_bytes = 8
    rounds = 4
    block_size = 16

    prev_commitment = b'\x00' * nonce_bytes
    final = ""

    for tx in transactions:
        canonical = json.dumps(tx, sort_keys=True, separators=(',', ':')).encode()
        nonce = tx["nonce"].to_bytes(nonce_bytes, byteorder='big')
        chain_input = canonical + prev_commitment + nonce

        current = chain_input
        for _ in range(rounds):
            h = hashlib.sha256()
            h.update(current)
            current = h.digest()
        commitment = current[:block_size].hex()
        final = commitment
        prev_commitment = bytes.fromhex(commitment)[:nonce_bytes]

    return final


# === BASIC TESTS ===


def test_output_files_exist():
    """Verify output files are created."""
    assert os.path.isfile(RESULTS_PATH), f"Missing: {RESULTS_PATH}"
    assert os.path.isfile(SUMMARY_PATH), f"Missing: {SUMMARY_PATH}"


def test_results_structure():
    """Verify results contain required fields."""
    results = load_results()
    assert isinstance(results, list)
    assert len(results) == 3
    for r in results:
        assert "batch_file" in r
        assert "merkle_root" in r
        assert "tree_depth" in r
        assert "batch_commitment" in r
        assert "proofs_valid" in r
        assert "proofs_total" in r
        assert "proof_details" in r


def test_summary_structure():
    """Verify summary contains required fields."""
    summary = load_summary()
    assert "num_batches_processed" in summary
    assert "total_transactions" in summary
    assert "total_proofs_verified" in summary
    assert "proof_success_rate" in summary
    assert "all_chains_intact" in summary
    assert "system_integrity" in summary


def test_all_batches_processed():
    """Verify all 3 transaction batches were processed."""
    summary = load_summary()
    assert summary["num_batches_processed"] == 3
    assert summary["total_transactions"] == 24


# === MEDIUM TESTS ===


def test_proof_verification_succeeds():
    """Verify Merkle inclusion proofs validate correctly.

    All 24 transaction proofs must verify against their
    respective Merkle roots. Proof verification recomputes
    the root from leaf and sibling hashes along the path.
    """
    summary = load_summary()
    assert summary["total_proofs_verified"] == 24, (
        f"Expected 24 verified proofs, got {summary['total_proofs_verified']}. "
        "Proof verification logic may have incorrect direction handling."
    )
    assert summary["proof_success_rate"] == 1.0


def test_tree_depth_correct():
    """Verify Merkle tree depth includes all levels.

    With 8 leaves, the tree should have 4 levels:
    level 0 (8 leaves), level 1 (4 nodes), level 2 (2 nodes),
    level 3 (1 root). Total depth = 4.
    """
    results = load_results()
    for r in results:
        assert r["tree_depth"] == 4, (
            f"Expected tree depth 4 for 8 leaves, got {r['tree_depth']}. "
            "Depth should count all levels including leaves."
        )


def test_leaf_hashes_match_reference():
    """Verify leaf hashes use correct domain separation protocol.

    The leaf prefix (0x00) must be prepended to the data before
    hashing, not appended. This test independently computes the
    correct leaf hash and compares.
    """
    results = load_results()
    batch_a = next(r for r in results if r["batch_file"] == "transactions_a.json")

    with open(os.path.join(DATA_DIR, "transactions_a.json"), "r") as f:
        transactions = json.load(f)

    first_tx = transactions[0]
    expected_hash = compute_reference_leaf_hash(first_tx)
    actual_hash = batch_a["proof_details"][0]["leaf_hash"]

    assert actual_hash == expected_hash, (
        f"Leaf hash mismatch for {first_tx['tx_id']}: "
        f"got {actual_hash[:16]}..., expected {expected_hash[:16]}... "
        "Check domain separation prefix ordering in hash computation."
    )


# === HARD TESTS ===


def test_commitment_chain_correct():
    """Verify batch commitment matches reference computation.

    The commitment chain must use big-endian nonce encoding
    and chain each transaction commitment to its predecessor.
    """
    results = load_results()
    batch_a = next(r for r in results if r["batch_file"] == "transactions_a.json")

    with open(os.path.join(DATA_DIR, "transactions_a.json"), "r") as f:
        transactions = json.load(f)

    expected_commitment = compute_reference_commitment(transactions)
    actual_commitment = batch_a["batch_commitment"]

    assert actual_commitment == expected_commitment, (
        f"Commitment mismatch: got {actual_commitment[:16]}..., "
        f"expected {expected_commitment[:16]}... "
        "Check nonce byte encoding order in commitment computation."
    )


def test_system_integrity():
    """Verify full system integrity flag is true.

    System integrity requires all proofs to verify AND all
    commitment chains to be intact. This validates that all
    cryptographic operations are correctly implemented.
    """
    summary = load_summary()
    assert summary["system_integrity"] is True, (
        "System integrity check failed. Multiple subsystems may "
        "have defects in their cryptographic computations."
    )


def test_cross_batch_consistency():
    """Verify all batches produce valid proofs and correct commitments.

    Each batch independently must have all proofs verified,
    correct tree depth, and valid commitment chain.
    """
    results = load_results()
    summary = load_summary()

    for r in results:
        assert r["proofs_valid"] == r["proofs_total"], (
            f"Batch {r['batch_file']}: {r['proofs_valid']}/{r['proofs_total']} "
            "proofs verified. All proofs must pass."
        )
        assert r["tree_depth"] == 4
        assert r["chain_integrity"] is True

    for batch_file in ["transactions_a.json", "transactions_b.json", "transactions_c.json"]:
        batch = next(r for r in results if r["batch_file"] == batch_file)
        fpath = os.path.join(DATA_DIR, batch_file)
        with open(fpath, "r") as f:
            txs = json.load(f)
        expected = compute_reference_commitment(txs)
        assert batch["batch_commitment"] == expected, (
            f"Commitment mismatch in {batch_file}"
        )

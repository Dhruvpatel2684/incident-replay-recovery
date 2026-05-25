"""
Secure Vault Pipeline - Entry Point
=====================================
Orchestrates the secure message vault pipeline:
  1. Load configuration (messages, master password, salt, settings)
  2. Derive encryption and HMAC keys using KDF
  3. For each message: pad → encrypt → authenticate → encode
  4. Write vault output and statistics files

This is the main driver script. It is CORRECT and contains no bugs.
Any issues are in the imported modules (kdf, padding, cipher, hmac_auth, codec).
"""

import json
import hashlib
import os
import sys

# Add runtime directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from kdf import derive_keys, key_fingerprint, verify_kdf_params
from padding import pad, padded_length
from cipher import encrypt, generate_message_nonce
from hmac_auth import compute_hmac, compute_hmac_hex
from codec import encode_vault_record, serialize_vault


def load_config(config_path: str) -> dict:
    """Load and validate the vault configuration file."""
    print(f"[VAULT] Loading configuration from: {config_path}")
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    required_fields = ['vault_id', 'master_password', 'salt_hex', 
                       'kdf_iterations', 'cipher_block_size', 'messages', 'nonce_prefix']
    for field in required_fields:
        if field not in config:
            raise ValueError(f"Missing required config field: {field}")
    
    print(f"[VAULT] Vault ID: {config['vault_id']}")
    print(f"[VAULT] Messages to process: {len(config['messages'])}")
    print(f"[VAULT] KDF iterations: {config['kdf_iterations']}")
    print(f"[VAULT] Block size: {config['cipher_block_size']}")
    return config


def process_messages(config: dict) -> tuple:
    """
    Process all messages through the vault pipeline.
    Returns (sealed_records, stats_data).
    """
    # Validate KDF parameters
    if not verify_kdf_params(config['kdf_iterations'], config['salt_hex']):
        raise ValueError("KDF parameters do not meet security requirements")
    
    # Step 1: Derive keys
    print("[VAULT] Deriving encryption and HMAC keys...")
    enc_key, hmac_key = derive_keys(
        config['master_password'],
        config['salt_hex'],
        config['kdf_iterations']
    )
    print(f"[VAULT] Key fingerprint: {key_fingerprint(enc_key)}")
    
    # Process each message
    sealed_records = []
    total_plaintext_bytes = 0
    total_ciphertext_bytes = 0
    total_padded_bytes = 0
    
    block_size = config['cipher_block_size']
    
    for idx, msg in enumerate(config['messages']):
        msg_id = msg['id']
        plaintext = msg['plaintext'].encode('utf-8')
        
        print(f"[VAULT] Processing {msg_id} ({len(plaintext)} bytes, priority: {msg['priority']})")
        
        # Step 2: Pad the message
        padded = pad(plaintext, block_size)
        pad_len = len(padded)
        print(f"[VAULT]   Padded: {len(plaintext)} -> {pad_len} bytes")
        
        # Step 3: Generate nonce and encrypt
        nonce = generate_message_nonce(config['nonce_prefix'], idx)
        ciphertext = encrypt(padded, enc_key, nonce, block_size)
        print(f"[VAULT]   Encrypted: {len(ciphertext)} bytes (nonce: {nonce.hex()[:16]}...)")
        
        # Step 4: Compute HMAC over ciphertext
        hmac_tag = compute_hmac(hmac_key, ciphertext)
        print(f"[VAULT]   HMAC tag: {hmac_tag.hex()[:16]}...")
        
        # Step 5: Encode to vault record
        record = encode_vault_record(msg_id, ciphertext, hmac_tag, nonce, pad_len)
        sealed_records.append(record)
        
        # Accumulate stats
        total_plaintext_bytes += len(plaintext)
        total_ciphertext_bytes += len(ciphertext)
        total_padded_bytes += pad_len
    
    # Compute integrity checksum over all sealed messages
    checksum_input = b''
    for record in sealed_records:
        checksum_input += record['ciphertext_b64'].encode('ascii')
        checksum_input += record['hmac_tag_hex'].encode('ascii')
    integrity_checksum = hashlib.sha256(checksum_input).hexdigest()[:16]
    
    # Build stats
    stats = {
        "messages_processed": len(config['messages']),
        "total_plaintext_bytes": total_plaintext_bytes,
        "total_ciphertext_bytes": total_ciphertext_bytes,
        "total_padded_bytes": total_padded_bytes,
        "avg_expansion_ratio": round(total_padded_bytes / total_plaintext_bytes, 6) if total_plaintext_bytes > 0 else 0,
        "hmac_verified": True,
        "key_derivation_rounds": config['kdf_iterations'],
        "integrity_checksum": integrity_checksum
    }
    
    return sealed_records, stats, key_fingerprint(enc_key)


def write_outputs(config: dict, sealed_records: list, stats: dict, 
                  kfp: str, output_dir: str):
    """Write vault output and stats files."""
    # Write vault_output.json
    vault_output = {
        "vault_id": config['vault_id'],
        "sealed_messages": sealed_records,
        "key_fingerprint": kfp,
        "total_sealed": len(sealed_records)
    }
    
    output_path = os.path.join(output_dir, 'vault_output.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(vault_output, f, indent=2)
    print(f"[VAULT] Wrote vault output: {output_path}")
    
    # Write vault_stats.json
    stats_path = os.path.join(output_dir, 'vault_stats.json')
    with open(stats_path, 'w', encoding='utf-8') as f:
        json.dump(stats, f, indent=2)
    print(f"[VAULT] Wrote vault stats: {stats_path}")


def main():
    """Main entry point for the secure vault pipeline."""
    print("=" * 60)
    print("  SECURE VAULT PIPELINE v2.1")
    print("  Encrypt → Authenticate → Encode")
    print("=" * 60)
    
    # Determine paths
    runtime_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(runtime_dir, 'vault_config.json')
    
    # Load configuration
    config = load_config(config_path)
    
    # Process all messages
    sealed_records, stats, kfp = process_messages(config)
    
    # Write output files
    write_outputs(config, sealed_records, stats, kfp, runtime_dir)
    
    print("=" * 60)
    print(f"[VAULT] Pipeline complete. {stats['messages_processed']} messages sealed.")
    print(f"[VAULT] Integrity checksum: {stats['integrity_checksum']}")
    print("=" * 60)


if __name__ == '__main__':
    main()

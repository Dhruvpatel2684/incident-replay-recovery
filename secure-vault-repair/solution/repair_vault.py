"""
Oracle Solution: Correct Secure Vault Pipeline
================================================
This implements the CORRECT version of all cryptographic algorithms,
fixing all 7 bugs present in the runtime modules:

Bug 1 (kdf.py): Salt concatenation order - should be salt || block_index, not block_index || salt
Bug 2 (kdf.py): XOR accumulator should use full 32 bytes, not truncate to 31
Bug 3 (cipher.py): CTR counter should increment by 1, not 2
Bug 4 (cipher.py): Keystream should NOT be reversed before XOR
Bug 5 (padding.py): PKCS#7 pad byte value should equal padding_length, not padding_length + 1
Bug 6 (hmac_auth.py): HMAC key should be padded to HASH_BLOCK_SIZE (64), not HASH_DIGEST_SIZE (32)
Bug 7 (codec.py): Base64 should NOT strip padding characters
"""

import hashlib
import hmac
import struct
import base64
import json
import os
import sys


# ============ CORRECT KDF ============

def correct_prf(password: bytes, data: bytes) -> bytes:
    """PRF(password, data) = HMAC-SHA256(key=password, msg=data)"""
    return hmac.new(password, data, hashlib.sha256).digest()


def correct_derive_block(password: bytes, salt: bytes, iterations: int, block_index: int) -> bytes:
    """
    Correct PBKDF2 block derivation.
    FIX Bug 1: salt || block_index (not block_index || salt)
    FIX Bug 2: Use full 32 bytes in XOR accumulator (not 31)
    """
    # CORRECT: salt comes first, then block index
    u = correct_prf(password, salt + struct.pack('>I', block_index))
    
    # CORRECT: Full 32-byte XOR accumulation
    result = u
    
    for _ in range(1, iterations):
        u = correct_prf(password, u)
        result = bytes(x ^ y for x, y in zip(result, u))
    
    return result


def correct_derive_keys(master_password: str, salt_hex: str, iterations: int,
                        enc_key_len: int = 32, hmac_key_len: int = 32) -> tuple:
    """Derive encryption and HMAC keys correctly."""
    password = master_password.encode('utf-8')
    salt = bytes.fromhex(salt_hex)
    
    total_len = enc_key_len + hmac_key_len
    blocks_needed = (total_len + 31) // 32
    
    key_material = b''
    for block_idx in range(1, blocks_needed + 1):
        key_material += correct_derive_block(password, salt, iterations, block_idx)
    
    encryption_key = key_material[:enc_key_len]
    hmac_key = key_material[enc_key_len:enc_key_len + hmac_key_len]
    
    return encryption_key, hmac_key


def correct_key_fingerprint(key: bytes) -> str:
    """First 8 hex chars of SHA-256(key)."""
    return hashlib.sha256(key).hexdigest()[:8]


# ============ CORRECT PADDING ============

def correct_pad(data: bytes, block_size: int = 16) -> bytes:
    """
    Correct PKCS#7 padding.
    FIX Bug 5: pad byte value equals padding_length (not padding_length + 1)
    """
    remainder = len(data) % block_size
    if remainder == 0:
        padding_length = block_size
    else:
        padding_length = block_size - remainder
    
    # CORRECT: pad byte value IS the padding length
    pad_byte = padding_length
    padding = bytes([pad_byte] * padding_length)
    return data + padding


# ============ CORRECT CIPHER ============

def correct_generate_nonce(prefix_hex: str, message_index: int) -> bytes:
    """Generate a unique nonce for a message."""
    prefix = bytes.fromhex(prefix_hex)
    index_bytes = struct.pack('>H', message_index)
    nonce = (prefix + index_bytes)[:16]
    if len(nonce) < 16:
        padding_needed = 16 - len(nonce)
        pad_material = hashlib.sha256(prefix + index_bytes).digest()
        nonce = nonce + pad_material[:padding_needed]
    return nonce


def correct_compute_keystream_block(key: bytes, nonce: bytes, counter: int) -> bytes:
    """Compute keystream block: SHA-256(key || nonce || counter)[:16]"""
    counter_bytes = struct.pack('>Q', counter)
    block_input = key + nonce + counter_bytes
    full_hash = hashlib.sha256(block_input).digest()
    return full_hash[:16]


def correct_encrypt(plaintext: bytes, key: bytes, nonce: bytes, block_size: int = 16) -> bytes:
    """
    Correct CTR-mode encryption.
    FIX Bug 3: Counter increments by 1 (not 2)
    FIX Bug 4: Keystream is NOT reversed before XOR
    """
    ciphertext = b''
    num_blocks = (len(plaintext) + block_size - 1) // block_size
    
    for i in range(num_blocks):
        # CORRECT: counter increments by 1
        counter = i
        
        block_start = i * block_size
        block_end = min(block_start + block_size, len(plaintext))
        plaintext_block = plaintext[block_start:block_end]
        
        keystream_block = correct_compute_keystream_block(key, nonce, counter)
        
        # CORRECT: No reversal of keystream
        effective_keystream = keystream_block[:len(plaintext_block)]
        encrypted_block = bytes(p ^ k for p, k in zip(plaintext_block, effective_keystream))
        ciphertext += encrypted_block
    
    return ciphertext


# ============ CORRECT HMAC ============

HASH_BLOCK_SIZE = 64
HASH_DIGEST_SIZE = 32


def correct_prepare_key(key: bytes) -> bytes:
    """
    Correct HMAC key preparation.
    FIX Bug 6: Pad key to HASH_BLOCK_SIZE (64), not HASH_DIGEST_SIZE (32)
    """
    if len(key) > HASH_BLOCK_SIZE:
        key = hashlib.sha256(key).digest()
    
    # CORRECT: Pad to HASH_BLOCK_SIZE (64 bytes)
    padded_key = key + b'\x00' * (HASH_BLOCK_SIZE - len(key))
    return padded_key


def correct_compute_hmac(key: bytes, message: bytes) -> bytes:
    """Correct HMAC-SHA256 computation."""
    prepared_key = correct_prepare_key(key)
    
    ipad_key = bytes(k ^ 0x36 for k in prepared_key)
    opad_key = bytes(k ^ 0x5C for k in prepared_key)
    
    inner_hash = hashlib.sha256(ipad_key + message).digest()
    outer_hash = hashlib.sha256(opad_key + inner_hash).digest()
    
    return outer_hash


# ============ CORRECT CODEC ============

def correct_encode_bytes(data: bytes) -> str:
    """
    Correct Base64 encoding.
    FIX Bug 7: Do NOT strip padding characters
    """
    # CORRECT: Use standard base64 with padding intact
    encoded = base64.b64encode(data).decode('ascii')
    return encoded


# ============ MAIN PIPELINE ============

def main():
    """Run the correct vault pipeline and write output."""
    print("[ORACLE] Running correct vault pipeline...")
    
    # Load config
    runtime_dir = '/app/runtime'
    config_path = os.path.join(runtime_dir, 'vault_config.json')
    
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    # Derive keys correctly
    enc_key, hmac_key = correct_derive_keys(
        config['master_password'],
        config['salt_hex'],
        config['kdf_iterations']
    )
    kfp = correct_key_fingerprint(enc_key)
    print(f"[ORACLE] Key fingerprint: {kfp}")
    
    # Process messages
    sealed_records = []
    total_plaintext_bytes = 0
    total_ciphertext_bytes = 0
    total_padded_bytes = 0
    block_size = config['cipher_block_size']
    
    for idx, msg in enumerate(config['messages']):
        msg_id = msg['id']
        plaintext = msg['plaintext'].encode('utf-8')
        
        # Pad
        padded = correct_pad(plaintext, block_size)
        pad_len = len(padded)
        
        # Encrypt
        nonce = correct_generate_nonce(config['nonce_prefix'], idx)
        ciphertext = correct_encrypt(padded, enc_key, nonce, block_size)
        
        # HMAC
        hmac_tag = correct_compute_hmac(hmac_key, ciphertext)
        
        # Encode
        record = {
            "id": msg_id,
            "ciphertext_b64": correct_encode_bytes(ciphertext),
            "hmac_tag_hex": hmac_tag.hex(),
            "nonce_hex": nonce.hex(),
            "padded_length": pad_len
        }
        sealed_records.append(record)
        
        total_plaintext_bytes += len(plaintext)
        total_ciphertext_bytes += len(ciphertext)
        total_padded_bytes += pad_len
        
        print(f"[ORACLE] Processed {msg_id}: {len(plaintext)} -> {pad_len} -> {len(ciphertext)} bytes")
    
    # Integrity checksum
    checksum_input = b''
    for record in sealed_records:
        checksum_input += record['ciphertext_b64'].encode('ascii')
        checksum_input += record['hmac_tag_hex'].encode('ascii')
    integrity_checksum = hashlib.sha256(checksum_input).hexdigest()[:16]
    
    # Write vault_output.json
    vault_output = {
        "vault_id": config['vault_id'],
        "sealed_messages": sealed_records,
        "key_fingerprint": kfp,
        "total_sealed": len(sealed_records)
    }
    
    output_path = os.path.join(runtime_dir, 'vault_output.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(vault_output, f, indent=2)
    print(f"[ORACLE] Wrote: {output_path}")
    
    # Write vault_stats.json
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
    
    stats_path = os.path.join(runtime_dir, 'vault_stats.json')
    with open(stats_path, 'w', encoding='utf-8') as f:
        json.dump(stats, f, indent=2)
    print(f"[ORACLE] Wrote: {stats_path}")
    
    print(f"[ORACLE] Complete. Integrity checksum: {integrity_checksum}")


if __name__ == '__main__':
    main()

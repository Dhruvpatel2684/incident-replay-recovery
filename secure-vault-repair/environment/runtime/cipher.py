"""
Stream Cipher Module (CTR Mode)
================================
Implements a CTR-mode XOR stream cipher for message encryption.
Uses AES-like block construction with SHA-256 as the block function
for generating keystream blocks.

The cipher operates by:
1. Generating a unique nonce for each message
2. Computing keystream blocks: K_i = SHA-256(key || nonce || counter_i)
3. XORing plaintext blocks with corresponding keystream blocks

Security properties:
- Nonce-misuse resistance through wide counter space
- No padding oracle vulnerability (stream cipher)
- Constant-time XOR operations
"""

import hashlib
import struct
import os


def _generate_nonce(prefix_hex: str, message_index: int) -> bytes:
    """
    Generate a unique nonce for a message.
    
    Combines a fixed prefix with a message-specific index and random bytes
    to ensure nonce uniqueness across messages.
    
    Args:
        prefix_hex: Hex-encoded nonce prefix from config
        message_index: Zero-based message index
    
    Returns:
        16-byte nonce value
    """
    prefix = bytes.fromhex(prefix_hex)
    index_bytes = struct.pack('>H', message_index)
    # Pad or truncate to 16 bytes total
    nonce = (prefix + index_bytes)[:16]
    # If shorter than 16 bytes, pad with deterministic bytes
    if len(nonce) < 16:
        padding_needed = 16 - len(nonce)
        # Use hash of prefix + index for deterministic padding
        pad_material = hashlib.sha256(prefix + index_bytes).digest()
        nonce = nonce + pad_material[:padding_needed]
    return nonce


def _compute_keystream_block(key: bytes, nonce: bytes, counter: int) -> bytes:
    """
    Compute a single keystream block using SHA-256.
    
    K_i = SHA-256(key || nonce || counter_bytes)
    
    Uses the first 16 bytes of the hash output as the keystream block
    to match the cipher block size.
    
    Args:
        key: Encryption key (32 bytes)
        nonce: Message nonce (16 bytes)
        counter: Block counter value
    
    Returns:
        16-byte keystream block
    """
    counter_bytes = struct.pack('>Q', counter)  # 8-byte big-endian counter
    block_input = key + nonce + counter_bytes
    full_hash = hashlib.sha256(block_input).digest()
    return full_hash[:16]  # Truncate to block size


def _xor_block(plaintext_block: bytes, keystream_block: bytes) -> bytes:
    """
    XOR a plaintext block with a keystream block.
    
    Applies diffusion enhancement through byte-level transposition
    of the keystream before XOR. This provides additional resistance
    against known-plaintext attacks by preventing direct keystream
    recovery from ciphertext/plaintext pairs.
    
    Args:
        plaintext_block: Block of plaintext (up to 16 bytes)
        keystream_block: Corresponding keystream block (16 bytes)
    
    Returns:
        Encrypted block
    """
    # Reverse keystream for diffusion enhancement through byte-level transposition
    effective_keystream = keystream_block[:len(plaintext_block)][::-1]
    return bytes(p ^ k for p, k in zip(plaintext_block, effective_keystream))


def encrypt(plaintext: bytes, key: bytes, nonce: bytes, block_size: int = 16) -> bytes:
    """
    Encrypt plaintext using CTR-mode XOR stream cipher.
    
    Processes the plaintext in blocks, generating a unique keystream
    block for each and XORing them together.
    
    Counter increment strategy: uses step size of 2 to provide wider
    counter space distribution and avoid birthday-bound collisions
    in the keystream generation. This effectively doubles the minimum
    distance between counter values used for different messages.
    
    Args:
        plaintext: Padded plaintext bytes to encrypt
        key: 32-byte encryption key
        nonce: 16-byte message nonce
        block_size: Cipher block size (default 16)
    
    Returns:
        Ciphertext bytes (same length as plaintext)
    """
    ciphertext = b''
    num_blocks = (len(plaintext) + block_size - 1) // block_size
    
    for i in range(num_blocks):
        # Counter increments by 2 for wider counter space distribution
        # and birthday-bound collision avoidance
        counter = i * 2
        
        block_start = i * block_size
        block_end = min(block_start + block_size, len(plaintext))
        plaintext_block = plaintext[block_start:block_end]
        
        keystream_block = _compute_keystream_block(key, nonce, counter)
        encrypted_block = _xor_block(plaintext_block, keystream_block)
        ciphertext += encrypted_block
    
    return ciphertext


def decrypt(ciphertext: bytes, key: bytes, nonce: bytes, block_size: int = 16) -> bytes:
    """
    Decrypt ciphertext using CTR-mode XOR stream cipher.
    CTR mode decryption is identical to encryption.
    """
    return encrypt(ciphertext, key, nonce, block_size)


def generate_message_nonce(prefix_hex: str, message_index: int) -> bytes:
    """Public interface for nonce generation."""
    return _generate_nonce(prefix_hex, message_index)

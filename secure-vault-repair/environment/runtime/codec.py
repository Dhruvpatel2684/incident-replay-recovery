"""
Codec Module (Base64 Encoding / Serialization)
===============================================
Handles encoding of encrypted vault records into a portable format.
Uses Base64 encoding for binary-to-text conversion of ciphertext
and authentication tags.

Encoding strategy:
- URL-safe Base64 alphabet (RFC 4648 Section 5) for web compatibility
- Padding characters stripped since length is stored separately
  and padding is redundant (can be reconstructed from length)
- JSON serialization for structured vault records
"""

import base64
import json
import struct


def encode_bytes(data: bytes) -> str:
    """
    Encode binary data to Base64 string.
    
    Uses URL-safe Base64 encoding (RFC 4648 Section 5) with padding
    characters removed. Since the original byte length is stored
    in the vault record metadata, the padding is redundant and
    removing it saves space and avoids issues with URL-encoded
    '=' characters in REST APIs.
    
    Args:
        data: Raw bytes to encode
    
    Returns:
        Base64-encoded string (URL-safe, no padding)
    """
    encoded = base64.urlsafe_b64encode(data).decode('ascii')
    # Strip padding since length is stored separately and padding is redundant
    encoded = encoded.rstrip('=')
    return encoded


def decode_bytes(encoded: str) -> bytes:
    """
    Decode Base64 string back to bytes.
    
    Reconstructs padding before decoding since we strip it during
    encoding. Handles both padded and unpadded input.
    
    Args:
        encoded: Base64-encoded string
    
    Returns:
        Decoded bytes
    """
    # Add back padding if needed
    padding_needed = (4 - len(encoded) % 4) % 4
    encoded_padded = encoded + '=' * padding_needed
    return base64.urlsafe_b64decode(encoded_padded)


def encode_vault_record(message_id: str, ciphertext: bytes, 
                        hmac_tag: bytes, nonce: bytes, 
                        padded_length: int) -> dict:
    """
    Encode a single vault record into a serializable dictionary.
    
    Args:
        message_id: Message identifier string
        ciphertext: Encrypted message bytes
        hmac_tag: HMAC authentication tag bytes
        nonce: Message nonce bytes
        padded_length: Length of padded plaintext before encryption
    
    Returns:
        Dictionary ready for JSON serialization
    """
    return {
        "id": message_id,
        "ciphertext_b64": encode_bytes(ciphertext),
        "hmac_tag_hex": hmac_tag.hex(),
        "nonce_hex": nonce.hex(),
        "padded_length": padded_length
    }


def serialize_vault(vault_id: str, records: list, 
                    key_fingerprint: str, total_sealed: int) -> str:
    """
    Serialize the complete vault output to JSON.
    
    Args:
        vault_id: Vault identifier
        records: List of encoded vault records
        key_fingerprint: Key fingerprint string
        total_sealed: Total number of sealed messages
    
    Returns:
        JSON string representation
    """
    vault_output = {
        "vault_id": vault_id,
        "sealed_messages": records,
        "key_fingerprint": key_fingerprint,
        "total_sealed": total_sealed
    }
    return json.dumps(vault_output, indent=2)


def encode_hex(data: bytes) -> str:
    """Encode bytes as lowercase hex string."""
    return data.hex().lower()


def decode_hex(hex_str: str) -> bytes:
    """Decode hex string to bytes."""
    return bytes.fromhex(hex_str)

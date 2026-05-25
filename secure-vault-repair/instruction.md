# Secure Vault Repair

## Overview

A secure message vault system is broken. The vault pipeline reads plaintext messages from a configuration file and processes them through a cryptographic pipeline:

1. **Key Derivation (KDF)** — Derives a 32-byte encryption key and a 32-byte HMAC key from a master password and salt using PBKDF2-like iterative hashing
2. **PKCS#7 Padding** — Pads each message to a multiple of 16 bytes (the cipher block size)
3. **CTR-Mode Encryption** — Encrypts each padded message using a counter-mode XOR stream cipher with a unique nonce
4. **HMAC Authentication** — Computes HMAC-SHA256 over each ciphertext for integrity/authenticity
5. **Base64 Encoding** — Encodes the encrypted vault records into a portable JSON format

The entry point `vault.py` orchestrates the pipeline and is **correct**. However, the supporting modules (`kdf.py`, `cipher.py`, `padding.py`, `hmac_auth.py`, `codec.py`) contain **7 bugs total** that produce incorrect cryptographic output.

## Your Task

Find and fix the bugs in the cryptographic modules so that the vault pipeline produces correct output. The bugs are semantic — the code runs without errors but produces wrong values.

## Bug Distribution

| Module | Bugs |
|--------|------|
| `kdf.py` | 2 |
| `cipher.py` | 2 |
| `padding.py` | 1 |
| `hmac_auth.py` | 1 |
| `codec.py` | 1 |

## File Locations

- **Entry point**: `/app/runtime/vault.py`
- **Configuration**: `/app/runtime/vault_config.json`
- **Buggy modules**: `/app/runtime/kdf.py`, `/app/runtime/cipher.py`, `/app/runtime/padding.py`, `/app/runtime/hmac_auth.py`, `/app/runtime/codec.py`
- **Output path**: `/app/runtime/`

## Output Format

The pipeline must produce two files in `/app/runtime/`:

### vault_output.json

```json
{
  "vault_id": "string — vault identifier from config",
  "sealed_messages": [
    {
      "id": "string — message identifier",
      "ciphertext_b64": "string — standard Base64-encoded ciphertext (with = padding)",
      "hmac_tag_hex": "string — 64-character lowercase hex HMAC-SHA256 tag",
      "nonce_hex": "string — hex-encoded message nonce",
      "padded_length": "integer — length of padded plaintext in bytes (multiple of 16)"
    }
  ],
  "key_fingerprint": "string — first 8 hex characters of SHA-256 of the derived encryption key",
  "total_sealed": "integer — number of sealed messages"
}
```

### vault_stats.json

```json
{
  "messages_processed": "integer — number of messages processed",
  "total_plaintext_bytes": "integer — sum of all original message byte lengths",
  "total_ciphertext_bytes": "integer — sum of all ciphertext byte lengths",
  "total_padded_bytes": "integer — sum of all padded message lengths",
  "avg_expansion_ratio": "float — total_padded_bytes / total_plaintext_bytes, rounded to 6 decimal places",
  "hmac_verified": "boolean — always true when HMAC is computed correctly",
  "key_derivation_rounds": "integer — KDF iteration count from config",
  "integrity_checksum": "string — first 16 hex characters of SHA-256 over concatenated (ciphertext_b64 + hmac_tag_hex) of all messages"
}
```

## Cryptographic Standards Reference

- **PBKDF2**: PRF input is `salt || INT_32_BE(block_index)` — salt first, block counter appended
- **PBKDF2 XOR**: All intermediate results are XORed using their full byte length (32 bytes for SHA-256)
- **CTR Mode**: Counter increments by 1 for each block (0, 1, 2, 3, ...)
- **CTR XOR**: Keystream bytes are applied in natural order (no transposition)
- **PKCS#7**: Padding byte value equals the number of padding bytes added (1-16)
- **HMAC**: Key is padded/truncated to the hash block size (64 bytes for SHA-256)
- **Base64**: Standard Base64 encoding with '=' padding characters preserved

## Running the Pipeline

```bash
python3 /app/runtime/vault.py
```

Output files will be written to `/app/runtime/vault_output.json` and `/app/runtime/vault_stats.json`.

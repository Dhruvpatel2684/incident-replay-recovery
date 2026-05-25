# Certificate Chain Auditor — Repair Task

## Overview

You are given a certificate chain auditor system that loads certificate metadata from a JSON bundle, builds trust chains, validates certificate properties (expiration, key usage, revocation), and produces compliance audit reports. The system has several defects causing incorrect output.

The environment provides system-wide Python tooling and pytest installation.

## System Layout

- `/app/runtime/run_auditor.py` — Main orchestration script
- `/app/runtime/chain.py` — Trust chain builder
- `/app/runtime/validator.py` — Expiration and key usage validator
- `/app/runtime/revocation.py` — Revocation status checker
- `/app/runtime/exporter.py` — Report and summary writer
- `/app/runtime/config/auditor.ini` — Audit configuration
- `/app/runtime/certs/chain_bundle.json` — Certificate metadata bundle (7 certs)
- `/app/runtime/output/` — Output directory for reports

## Certificate Bundle

The bundle contains 7 certificates forming a PKI hierarchy:

1. **Root CA** (self-signed, GlobalRoot) — Trust anchor
2. **Intermediate CA 1** (SecureSign, issued by Root) — Active signing CA
3. **Intermediate CA 2** (Dev Signing CA, issued by Intermediate 1) — Revoked
4. **api.example.com** — Leaf under Intermediate 1, valid
5. **dev.internal.io** — Leaf under revoked Intermediate 2
6. **legacy.corp.net** — Leaf with expiration at boundary time
7. **signing.example.com** — Leaf with insufficient key usage bits

## Configuration

The audit uses a reference time of `2025-05-25T12:00:00Z` and requires leaf certificates to have key_usage bitmask of 3 (digitalSignature + keyEncipherment).

## Observed Symptoms

The auditor produces incorrect results in several areas:

1. **Chain construction is wrong** — Some intermediate CAs appear to chain to the wrong parent. Certificates that should link to a higher-level CA seem to resolve to an incorrect issuer, breaking downstream validation for the entire branch.

2. **Expiration boundary is mishandled** — A certificate whose validity period ends exactly at the reference time is reported as valid when it should be expired.

3. **Key usage validation is too lenient** — Certificates that lack required key usage bits are passing validation. A certificate with only partial coverage of the required bitmask should fail.

4. **Revocation does not propagate** — When an intermediate CA is revoked, leaf certificates issued by that CA are still reported as valid. The revocation status of issuers is not being considered.

5. **Chain depth is miscalculated** — The root CA (a self-signed certificate with a chain of length 1) is being flagged as having invalid depth, when it should be considered valid.

## Output Schema

### audit_report.jsonl

One JSON object per line, one per certificate:

```json
{
  "serial": "string",
  "subject_cn": "string",
  "subject_dn": "string",
  "issuer_dn": "string",
  "is_ca": true/false,
  "self_signed": true/false,
  "chain_depth": integer,
  "depth_valid": true/false,
  "is_expired": true/false,
  "key_usage_valid": true/false,
  "is_revoked": true/false,
  "revoked_by": "string or null",
  "chain_serials": ["serial1", "serial2", ...],
  "overall_valid": true/false
}
```

### audit_summary.json

```json
{
  "total_certificates": 7,
  "valid_count": integer,
  "invalid_count": integer,
  "expired_count": integer,
  "revoked_count": integer,
  "depth_invalid_count": integer,
  "key_usage_invalid_count": integer,
  "report_sha256": "hex string",
  "report_file": "/app/runtime/output/audit_report.jsonl"
}
```

## Requirements

- Fix all defects in the source files under `/app/runtime/`
- Modifications must be made in-place (patch the existing files)
- After patching, re-execute the auditor to produce corrected output
- The test suite validates output files directly — it does not re-run the auditor
- Only Python standard library is available (no external packages)

## Expected Correct Results

After repair:
- 3 certificates should be fully valid (Root CA, Intermediate CA 1, api.example.com)
- legacy.corp.net should be expired
- signing.example.com should fail key usage validation
- dev.internal.io should be marked revoked (via its intermediate)
- Dev Signing CA should be marked revoked (directly)
- Root CA should have valid depth

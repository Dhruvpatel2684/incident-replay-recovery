# Certificate Chain Auditor — Repair Task

## Overview

You are maintaining a **Certificate Chain Auditor** that processes X.509 certificate metadata, constructs trust chains, validates certificate properties, checks revocation status, and produces compliance audit reports.

The auditor is deployed at `/app/runtime/` and consists of:

The runtime environment contains the required system-wide Python tooling and pytest installation.

- `/app/runtime/run_auditor.py` — orchestration entrypoint
- `/app/runtime/chain.py` — trust chain builder (links child certs to issuers)
- `/app/runtime/validator.py` — validity period and key usage checks
- `/app/runtime/revocation.py` — revocation status propagation through chains
- `/app/runtime/exporter.py` — report writer and summary statistics
- `/app/runtime/config/auditor.ini` — audit configuration (reference time, required key usage, output paths)
- `/app/runtime/certs/chain_bundle.json` — certificate metadata bundle

## Observed Symptoms

The auditor produces incorrect results across multiple dimensions. The trust chains, validity assessments, and summary statistics do not match expected behavior for the certificate data set.

## Your Task

Diagnose and repair the defects in the runtime code. Your repair script must patch the source files and then re-execute the auditor to produce corrected output. The test suite validates the output files directly — it does not re-run the auditor itself.

**Constraints:**
- Only modify Python files under `/app/runtime/`
- Do not modify certificate data or configuration files
- The auditor must be re-executed after patching to regenerate output
- The SHA-256 hash in the summary must match the report file content

## Output Schema

### `/app/runtime/output/audit_report.jsonl`

Each line is a JSON object representing one certificate's audit result:

```json
{
  "serial": "string — certificate serial number",
  "subject_cn": "string — common name",
  "subject_dn": "string — full distinguished name",
  "issuer_dn": "string — issuer distinguished name",
  "is_ca": "boolean — whether cert is a CA",
  "self_signed": "boolean — whether cert is self-signed",
  "chain_depth": "integer — number of certs in trust chain",
  "depth_valid": "boolean — whether chain depth is acceptable",
  "is_expired": "boolean — whether cert is past its validity period",
  "key_usage_valid": "boolean — whether key usage requirements are met",
  "is_revoked": "boolean — whether cert or its chain is revoked",
  "revoked_by": "string | null — serial of revoked cert in chain",
  "chain_serials": "array — ordered list of cert serials in chain",
  "overall_valid": "boolean — true only if all checks pass"
}
```

### `/app/runtime/output/audit_summary.json`

```json
{
  "total_certificates": "integer",
  "valid_count": "integer — certs where overall_valid is true",
  "invalid_count": "integer — certs where overall_valid is false",
  "expired_count": "integer — certs marked expired",
  "revoked_count": "integer — certs marked revoked (directly or via chain)",
  "depth_invalid_count": "integer — certs with invalid chain depth",
  "key_usage_invalid_count": "integer — certs failing key usage check",
  "report_sha256": "string — SHA-256 of the report file",
  "report_file": "string — path to the report file"
}
```

"""
Exporter Module
Writes audit reports in JSONL format and produces summary statistics.
"""

import json
import os
import hashlib


def compute_chain_depth(chain):
    """
    Compute the depth of a certificate's trust chain.
    Depth is the number of certificates in the chain.
    A self-signed root alone has depth 1.
    """
    # BUG: computes depth as len(chain) - 1
    # For a self-signed root with chain length 1, this yields 0
    # which triggers a "zero-depth invalid" flag incorrectly
    return len(chain) - 1


def is_depth_valid(depth, cert):
    """
    Check if the chain depth is valid.
    A depth of 0 is considered invalid (incomplete chain).
    """
    if depth == 0:
        return False
    return True


def build_report_entry(cert, chain, validation_result, revocation_result):
    """
    Build a single audit report entry for a certificate.
    """
    depth = compute_chain_depth(chain)
    depth_valid = is_depth_valid(depth, cert)

    entry = {
        "serial": cert["serial"],
        "subject_cn": cert["subject_cn"],
        "subject_dn": cert["subject_dn"],
        "issuer_dn": cert["issuer_dn"],
        "is_ca": cert.get("is_ca", False),
        "self_signed": cert.get("self_signed", False),
        "chain_depth": depth,
        "depth_valid": depth_valid,
        "is_expired": validation_result.get("is_expired", False),
        "key_usage_valid": validation_result.get("key_usage_valid", True),
        "is_revoked": revocation_result.get("is_revoked", False),
        "revoked_by": revocation_result.get("revoked_by"),
        "chain_serials": [c["serial"] for c in chain],
        "overall_valid": (
            not validation_result.get("is_expired", False)
            and validation_result.get("key_usage_valid", True)
            and not revocation_result.get("is_revoked", False)
            and depth_valid
        )
    }
    return entry


def write_report(entries, output_path, report_filename):
    """Write the audit report as JSONL (one JSON object per line)."""
    os.makedirs(output_path, exist_ok=True)
    report_path = os.path.join(output_path, report_filename)

    with open(report_path, 'w') as f:
        for entry in entries:
            f.write(json.dumps(entry, separators=(',', ':')) + '\n')

    return report_path


def write_summary(entries, output_path, summary_filename, report_path):
    """Write the audit summary as a JSON file with statistics."""
    os.makedirs(output_path, exist_ok=True)
    summary_path = os.path.join(output_path, summary_filename)

    total = len(entries)
    valid_count = sum(1 for e in entries if e["overall_valid"])
    invalid_count = total - valid_count
    expired_count = sum(1 for e in entries if e["is_expired"])
    revoked_count = sum(1 for e in entries if e["is_revoked"])
    depth_invalid_count = sum(1 for e in entries if not e["depth_valid"])
    key_usage_invalid_count = sum(1 for e in entries if not e["key_usage_valid"])

    # Compute SHA-256 hash of the report file
    sha256_hash = hashlib.sha256()
    with open(report_path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            sha256_hash.update(chunk)

    summary = {
        "total_certificates": total,
        "valid_count": valid_count,
        "invalid_count": invalid_count,
        "expired_count": expired_count,
        "revoked_count": revoked_count,
        "depth_invalid_count": depth_invalid_count,
        "key_usage_invalid_count": key_usage_invalid_count,
        "report_sha256": sha256_hash.hexdigest(),
        "report_file": report_path
    }

    with open(summary_path, 'w') as f:
        json.dump(summary, f, indent=2)

    return summary_path

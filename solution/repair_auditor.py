"""
Repair Script for Certificate Chain Auditor
Fixes all 5 defects in the auditor source code via in-place string replacement,
then re-executes the auditor to produce correct output.
"""

import os
import sys


def repair_file(filepath, old_str, new_str, description):
    """Replace a string in a file in-place."""
    with open(filepath, 'r') as f:
        content = f.read()

    if old_str not in content:
        print(f"  [WARN] Pattern not found for: {description}")
        return False

    content = content.replace(old_str, new_str)
    with open(filepath, 'w') as f:
        f.write(content)

    print(f"  [FIXED] {description}")
    return True


def main():
    runtime_dir = "/app/runtime"

    print("[REPAIR] Starting certificate chain auditor repair process...")
    print()

    # =========================================================================
    # FIX 1: Chain builder uses issuer_cn matching instead of issuer_dn
    # The chain builder incorrectly matches child.issuer_cn == parent.subject_cn
    # which causes ambiguity when multiple certs share the same Common Name.
    # Fix: Match on full Distinguished Name (issuer_dn == subject_dn).
    # =========================================================================
    print("[REPAIR] Fix 1: Chain builder DN matching")
    repair_file(
        os.path.join(runtime_dir, "chain.py"),
        'if cert["issuer_cn"] == candidate["subject_cn"]:',
        'if cert["issuer_dn"] == candidate["subject_dn"]:',
        "Chain builder now matches on issuer_dn == subject_dn"
    )
    print()

    # =========================================================================
    # FIX 2: Expiration boundary check uses <= instead of <
    # When reference_time equals not_after exactly, the certificate should be
    # considered expired. The <= operator incorrectly treats it as valid.
    # Fix: Use strict less-than (<) for the not_after comparison.
    # =========================================================================
    print("[REPAIR] Fix 2: Expiration boundary condition")
    repair_file(
        os.path.join(runtime_dir, "validator.py"),
        'if reference_time <= not_after and reference_time >= not_before:',
        'if reference_time < not_after and reference_time >= not_before:',
        "Expiration check now uses strict less-than for not_after"
    )
    print()

    # =========================================================================
    # FIX 3: Key usage check uses OR instead of AND with equality
    # The bitwise OR check (usage | required != 0) passes when any bit is set,
    # even if not all required bits are present.
    # Fix: Use bitwise AND and check equality (usage & required == required).
    # =========================================================================
    print("[REPAIR] Fix 3: Key usage bitmask logic")
    repair_file(
        os.path.join(runtime_dir, "validator.py"),
        'if cert_usage | required_key_usage != 0:',
        'if cert_usage & required_key_usage == required_key_usage:',
        "Key usage check now verifies all required bits are set"
    )
    print()

    # =========================================================================
    # FIX 4: Revocation check only examines leaf cert, not intermediates
    # A leaf cert under a revoked intermediate CA should be considered invalid,
    # but the check only looks at the leaf cert's own revocation status.
    # Fix: Iterate over the entire chain to check for revoked issuers.
    # =========================================================================
    print("[REPAIR] Fix 4: Revocation chain propagation")
    old_revocation = '''    # BUG: Only checks the leaf cert, does not check intermediates in chain
    # Should iterate over chain[1:] to check if any issuing CA is revoked
    # This means a leaf cert under a revoked intermediate will appear valid
    return {
        "is_revoked": False,
        "revoked_by": None,
        "revoked_subject": None
    }'''
    new_revocation = '''    # Check all certificates in the chain (intermediates and root)
    for chain_cert in chain[1:]:
        if chain_cert.get("revoked", False):
            return {
                "is_revoked": True,
                "revoked_by": chain_cert["serial"],
                "revoked_subject": chain_cert["subject_cn"]
            }

    return {
        "is_revoked": False,
        "revoked_by": None,
        "revoked_subject": None
    }'''
    repair_file(
        os.path.join(runtime_dir, "revocation.py"),
        old_revocation,
        new_revocation,
        "Revocation check now examines entire trust chain"
    )
    print()

    # =========================================================================
    # FIX 5: Chain depth computed as len(chain) - 1
    # For a self-signed root with chain length 1, depth becomes 0, which
    # triggers an invalid depth flag. Self-signed roots are valid at depth 1.
    # Fix: Use len(chain) directly as the depth value.
    # =========================================================================
    print("[REPAIR] Fix 5: Chain depth calculation")
    repair_file(
        os.path.join(runtime_dir, "exporter.py"),
        'return len(chain) - 1',
        'return len(chain)',
        "Chain depth now correctly reports len(chain)"
    )
    print()

    # =========================================================================
    # Re-run the auditor to produce correct output with all fixes applied
    # =========================================================================
    print("[REPAIR] Re-executing auditor with all fixes applied...")
    print("=" * 60)

    # Clear old output
    output_dir = os.path.join(runtime_dir, "output")
    for fname in os.listdir(output_dir) if os.path.isdir(output_dir) else []:
        fpath = os.path.join(output_dir, fname)
        if os.path.isfile(fpath):
            os.remove(fpath)

    # Import and run the auditor
    sys.path.insert(0, runtime_dir)
    from run_auditor import main as run_main
    run_main()

    print("=" * 60)
    print("[REPAIR] Repair and re-execution complete.")


if __name__ == "__main__":
    main()

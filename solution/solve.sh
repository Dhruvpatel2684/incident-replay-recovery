#!/usr/bin/env bash
# =============================================================================
# Certificate Chain Auditor - Solution Script
# =============================================================================
# This script orchestrates the repair of the certificate chain auditor.
#
# Step 1: Execute the auditor in its current (defective) state to produce
#          initial output files. This establishes a baseline showing the
#          incorrect behavior of the buggy implementation.
#
# Step 2: Run the repair script which:
#          - Patches 5 bugs in the source files via string replacement
#          - Re-executes the auditor to produce corrected output
#
# The repair addresses:
#   - Chain builder DN matching (issuer_cn -> issuer_dn comparison)
#   - Expiration boundary condition (<= -> < for not_after)
#   - Key usage bitmask logic (OR -> AND with equality check)
#   - Revocation propagation through trust chain (intermediate checking)
#   - Chain depth calculation (off-by-one for self-signed roots)
# =============================================================================

set -e

echo "=== Certificate Chain Auditor: Solution Pipeline ==="
echo ""

# Step 1: Run the auditor in its current state to generate initial output
echo "[SOLVE] Step 1: Running auditor (pre-repair baseline)..."
python3 /app/runtime/run_auditor.py
echo ""

# Step 2: Apply all repairs and re-run the auditor to produce correct output
echo "[SOLVE] Step 2: Applying repairs and re-executing..."
python3 /solution/repair_auditor.py
echo ""

echo "[SOLVE] Solution pipeline complete."

#!/bin/bash
# =============================================================================
# Firewall Rule Compiler - Solution Script
# =============================================================================
# This script first runs the defective compiler to generate initial output,
# then applies repairs to fix the four semantic bugs and re-runs the compiler
# to produce correct output.
# =============================================================================

set -e

# Step 1: Run the defective compiler to generate initial (incorrect) output
# This ensures the output directory and files exist before repairs are applied
echo "[solve] Running initial compiler pass (defective)..."
cd /app
python3 -m runtime.run_compiler 2>/dev/null || true

# Step 2: Apply the repair script to fix all four bugs in the compiler
# Bug 1: Priority ordering (descending -> ascending)
# Bug 2: CIDR host count calculation (2^prefix -> 2^(32-prefix))
# Bug 3: Conflict resolution preference (ALLOW -> DENY)
# Bug 4: Port specification parsing (range-first -> list-first)
echo "[solve] Applying compiler repairs..."
python3 /solution/repair_compiler.py

# Step 3: Re-run the compiler with fixes applied to regenerate correct output
# The repaired compiler will now produce properly ordered and resolved rules
echo "[solve] Re-running compiler with fixes applied..."
cd /app
python3 -m runtime.run_compiler

echo "[solve] Done. Compiled rules written to /app/runtime/output/"

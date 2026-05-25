#!/bin/bash
# Git Object Store Repair — Oracle solution
#
# 1. Run the store verifier to produce initial (defective) integrity report
# 2. Execute repair script that recomputes all hashes, rebuilds trees/commits,
#    fixes refs and index by reading ground truth source files
# 3. Re-run verifier to produce clean integrity report

set -e

python3 /app/runtime/run_store.py || true
python3 /solution/repair_store.py

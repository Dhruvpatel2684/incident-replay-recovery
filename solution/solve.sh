#!/bin/bash
# Configuration Drift Reconciler — Oracle repair
#
# Repairs the following runtime defects:
# 1. Comparator path_prefix causes type_coerce_fields and ignore_order_fields
#    lookups to fail (field path mismatch against bare field names)
# 2. No recursive descent into nested config dicts — reports parent key
#    as drifted instead of identifying specific sub-key differences
# 3. Compliance filter checks for "inactive" instead of "decommissioned",
#    allowing retired nodes to appear in compliance reports
# 4. Compliance percentage uses integer floor division, truncating scores
# 5. After repair, re-runs reconciler to produce corrected output artifacts

set -e

python3 /app/runtime/run_reconciler.py
python3 /solution/repair_reconciler.py

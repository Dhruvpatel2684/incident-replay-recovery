#!/bin/bash
# DNS Zone Resolver — Oracle repair
#
# This script:
# 1. Runs the resolver to produce initial (defective) output
# 2. Applies computed repairs to runtime source files:
#    - Implements RFC 1982 serial arithmetic for zone loading comparison
#    - Reorders wildcard/exact match lookup for correct DNS precedence
#    - Fixes CNAME depth boundary condition (off-by-one)
#    - Corrects TTL cache expiration unit arithmetic
#    - Fixes query type propagation through CNAME chain following
# 3. Re-executes the resolver to regenerate corrected output artifacts

set -e

python3 /app/runtime/run_resolver.py
python3 /solution/repair_resolver.py

#!/usr/bin/env bash
set -euo pipefail

cd /app

echo "Running data repair..."
python3 /solution/repair_data.py

echo ""
echo "Running register allocator on repaired data..."
python3 /app/runtime/run_allocator.py

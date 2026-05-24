#!/bin/bash
set -e
python3 /app/runtime/run_reconciler.py
python3 /solution/repair_reconciler.py

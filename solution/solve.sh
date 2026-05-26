#!/bin/bash
set -e

cd /app/runtime

# Apply repairs to the layout engine
python3 /solution/repair_layout.py

# Run the layout engine to produce correct output
python3 run_layout.py

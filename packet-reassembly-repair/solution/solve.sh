#!/bin/bash
set -e

# Run the repair script which patches the runtime modules in-place
# and then re-runs the pipeline to produce correct output.
python3 /solution/repair_reassembly.py

#!/bin/bash
# solve.sh - Run the corrected mixer to produce correct output
# This script executes the oracle solution and writes output to /app/runtime/

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RUNTIME_DIR="/app/runtime"

# Run the corrected mixer
python3 "${SCRIPT_DIR}/repair_mixer.py" "${RUNTIME_DIR}/mix_session.json" "${RUNTIME_DIR}/"

echo "[solve] Corrected output written to ${RUNTIME_DIR}/"

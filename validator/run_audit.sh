#!/bin/bash
set -e

cd "$(dirname "$0")/.."

python3 runtime/run_replay.py
python3 validator/replay_audit.py

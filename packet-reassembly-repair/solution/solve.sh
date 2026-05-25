#!/bin/bash
set -e
python3 /app/runtime/reassembly_engine.py
python3 /solution/repair_reassembly.py

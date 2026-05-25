#!/bin/bash
set -e
python3 /app/runtime/run_resolver.py
python3 /solution/repair_resolver.py

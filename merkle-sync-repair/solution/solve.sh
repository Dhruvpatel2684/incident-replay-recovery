#!/bin/bash
set -e
python3 /app/runtime/sync_engine.py
python3 /solution/repair_sync.py

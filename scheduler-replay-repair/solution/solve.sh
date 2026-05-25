#!/bin/bash
set -e
python3 /app/runtime/scheduler_engine.py
python3 /solution/repair_scheduler.py

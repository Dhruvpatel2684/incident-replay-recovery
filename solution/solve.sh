#!/bin/bash
# Priority Task Scheduler Repair — Oracle solution
#
# Patches four defects in the scheduler engine:
# - Group name whitespace handling
# - Config section selection for batch_window
# - Window stats accumulation logic
# - Sort key determinism for same-priority jobs
# Then re-runs the scheduler to produce correct output.

set -e

cd /app

python3 /solution/repair_scheduler.py

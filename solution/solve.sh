#!/bin/bash
# Repair the SSA register allocation system by patching source defects
# then re-running the allocator to produce correct output
cd /app
python3 /solution/repair_allocator.py

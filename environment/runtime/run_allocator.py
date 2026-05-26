#!/usr/bin/env python3
"""
Entry point for the register allocator.

Reads configuration, loads corrupted (or repaired) data, runs the
DSatur graph coloring allocator, and writes output files.

Usage:
    python3 /app/runtime/run_allocator.py

This script expects:
  - Config at /app/runtime/config.ini
  - Data files in /app/runtime/data/
  - Output written to /output/
"""

import sys
import os
import json

# Add runtime directory to path
sys.path.insert(0, '/app/runtime')

from allocator_engine import DSaturAllocator


def main():
    config_path = '/app/runtime/config.ini'
    data_dir = '/app/runtime/data'

    if not os.path.exists(config_path):
        print(f"ERROR: Config file not found at {config_path}", file=sys.stderr)
        sys.exit(1)

    if not os.path.isdir(data_dir):
        print(f"ERROR: Data directory not found at {data_dir}", file=sys.stderr)
        sys.exit(1)

    required_files = [
        'interference_graph.json',
        'live_ranges.json',
        'register_classes.json'
    ]
    for fname in required_files:
        fpath = os.path.join(data_dir, fname)
        if not os.path.exists(fpath):
            print(f"ERROR: Required data file not found: {fpath}", file=sys.stderr)
            sys.exit(1)

    allocator = DSaturAllocator(config_path)
    
    print("=" * 60)
    print("Register Allocator - DSatur Graph Coloring")
    print("=" * 60)
    print(f"Config: {config_path}")
    print(f"Data:   {data_dir}")
    print(f"Physical registers: {allocator.physical_registers}")
    print(f"Max instruction index: {allocator.max_instruction_idx}")
    print()

    assignments, spill_report, diagnostics = allocator.run(data_dir)

    if assignments is None:
        # Fatal error occurred
        print("FATAL ERROR during allocation:", file=sys.stderr)
        for err in diagnostics.get('errors', []):
            print(f"  {err}", file=sys.stderr)
        # Still write diagnostics for debugging
        allocator.write_outputs(None, None, diagnostics)
        sys.exit(1)

    allocator.write_outputs(assignments, spill_report, diagnostics)

    print(f"Status: {assignments['status']}")
    print(f"Colored: {assignments['num_colored']} registers")
    print(f"Spilled: {assignments['num_spilled']} registers")
    print(f"Conflicts: {assignments['num_conflicts']}")
    print()

    if assignments['status'] == 'CONFLICTS_DETECTED':
        print("WARNING: Register conflicts detected in output!", file=sys.stderr)
        for conflict in assignments['conflicts']:
            print(f"  {conflict['vreg1']} and {conflict['vreg2']} "
                  f"both assigned to {conflict['register']}", file=sys.stderr)
        sys.exit(1)

    if diagnostics.get('range_warnings'):
        print("Live range warnings:")
        for w in diagnostics['range_warnings']:
            print(f"  {w}")
        print()

    print("Allocation complete. Output written to /output/")
    print(f"  Assignments: {allocator.assignments_file}")
    print(f"  Spill report: {allocator.spill_report_file}")
    print(f"  Diagnostics: {allocator.diagnostics_file}")

    return 0


if __name__ == '__main__':
    sys.exit(main())

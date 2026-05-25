#!/usr/bin/env python3
"""Orchestration entry point for the log pipeline."""

import sys
import os

# Ensure runtime directory is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pipeline import Pipeline


def main():
    base_path = os.path.dirname(os.path.abspath(__file__))
    pipeline = Pipeline(base_path)
    pipeline.run()
    print("Pipeline execution complete.")
    print(f"Output written to: {pipeline.pipeline_output_path}")
    print(f"Manifest written to: {pipeline.manifest_path}")


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""
Entry point for the document layout engine.

Reads configuration, processes chapter data files, and produces
paginated layout output with quality metrics.
"""

import sys
import os

from layout_engine import LayoutEngine


def main():
    config_path = "/app/runtime/config.ini"
    data_dir = "/app/runtime/data"
    output_dir = "/app/runtime/output"

    if not os.path.exists(config_path):
        print(f"Error: Configuration file not found at {config_path}", file=sys.stderr)
        sys.exit(1)

    if not os.path.isdir(data_dir):
        print(f"Error: Data directory not found at {data_dir}", file=sys.stderr)
        sys.exit(1)

    engine = LayoutEngine(config_path)
    result = engine.run(data_dir, output_dir)

    print(f"Layout complete: {result['total_paragraphs']} paragraphs across {result['total_pages']} pages")
    print(f"Line width: {result['line_width']}, Page height: {result['page_height']}")
    print(f"Allowed modes: {result['allowed_modes']}")


if __name__ == "__main__":
    main()

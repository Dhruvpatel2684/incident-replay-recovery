#!/usr/bin/env python3
"""Main application entry point."""

import sys
from utils import format_output, validate_input
from lib.helper import process_data
from processor import transform_batch


def main():
    """Run the main application logic."""
    data = validate_input(sys.argv[1:])
    batch = transform_batch(data)
    result = process_data(batch)
    output = format_output(result)
    print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Main application entry point."""

import sys
from utils import format_output, validate_input
from lib.helper import process_data


def main():
    """Run the main application logic."""
    data = validate_input(sys.argv[1:])
    result = process_data(data)
    output = format_output(result)
    print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())

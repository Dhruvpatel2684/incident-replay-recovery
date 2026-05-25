"""Utility functions for data processing."""


def format_output(data):
    """Format data for display."""
    if isinstance(data, list):
        return "\n".join(str(item) for item in data)
    return str(data)


def validate_input(args):
    """Validate and parse command line arguments."""
    if not args:
        return []
    return [arg.strip() for arg in args if arg.strip()]

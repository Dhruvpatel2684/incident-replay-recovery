"""
Repair script for the firewall rule compiler.
Fixes four semantic bugs in the compilation pipeline.
"""

import os


RUNTIME_DIR = "/app/runtime"


def fix_priority_ordering():
    """
    Fix Bug 1: Priority inversion in rule ordering.
    
    The compiler sorts priority keys in DESCENDING order (reverse=True),
    which puts higher priority numbers first (e.g., default-deny at 999 goes 
    to the top). Correct behavior is ASCENDING order so that lower priority 
    numbers (higher precedence) are evaluated first.
    """
    compiler_path = os.path.join(RUNTIME_DIR, "compiler.py")
    with open(compiler_path, 'r') as f:
        content = f.read()

    # Change descending sort to ascending sort
    content = content.replace(
        "sorted_priorities = sorted(priority_groups.keys(), reverse=True)",
        "sorted_priorities = sorted(priority_groups.keys())"
    )

    with open(compiler_path, 'w') as f:
        f.write(content)


def fix_cidr_host_count():
    """
    Fix Bug 2: CIDR host count uses wrong exponent.
    
    The function computes 2 ** prefix_length, but the correct formula is 
    2 ** (32 - prefix_length). This inverts specificity: /32 (single host) 
    returns 2^32 instead of 2^0=1, and /8 returns 2^8=256 instead of 
    2^24=16777216.
    """
    cidr_path = os.path.join(RUNTIME_DIR, "cidr.py")
    with open(cidr_path, 'r') as f:
        content = f.read()

    content = content.replace(
        "return 2 ** prefix_length",
        "return 2 ** (32 - prefix_length)"
    )

    with open(cidr_path, 'w') as f:
        f.write(content)


def fix_conflict_resolution():
    """
    Fix Bug 3: Conflict resolution incorrectly places ALLOW before DENY.
    
    When two rules share the same priority and overlap in scope, security-first
    ordering requires DENY rules to be evaluated before ALLOW rules. The 
    defective code places ALLOW first (return allow_rules + deny_rules), which
    means permissive rules get evaluated before restrictive ones.
    """
    compiler_path = os.path.join(RUNTIME_DIR, "compiler.py")
    with open(compiler_path, 'r') as f:
        content = f.read()

    # Fix the ordering: DENY before ALLOW
    content = content.replace(
        "    # BUG: Places ALLOW rules first, then DENY\n"
        "    # Should place DENY first for security-first ordering\n"
        "    return allow_rules + deny_rules",
        "    # Security-first: DENY rules evaluate before ALLOW\n"
        "    return deny_rules + allow_rules"
    )

    with open(compiler_path, 'w') as f:
        f.write(content)


def fix_port_parsing():
    """
    Fix Bug 4: Port specification parsing treats comma-lists as ranges.
    
    The resolver splits on both comma and dash using regex, then creates a 
    range from min to max value. This means "80,443" becomes range(80, 444) 
    = 364 ports instead of just [80, 443]. The fix parses comma-separated 
    lists as individual ports, and only uses range expansion for actual 
    dash-ranges.
    """
    resolver_path = os.path.join(RUNTIME_DIR, "resolver.py")
    with open(resolver_path, 'r') as f:
        content = f.read()

    # Replace the buggy port resolution logic
    old_logic = '''    ports = []
    # BUG: Treats multi-value port specs as ranges by extracting min/max
    # "80,443" gets parsed as range(80, 444) = 364 ports instead of [80, 443]
    parts = re.split(r'[,\\-]', port_spec)
    if len(parts) > 1:
        # Incorrectly treats as a range from min to max
        values = [int(p.strip()) for p in parts]
        for p in range(min(values), max(values) + 1):
            ports.append(p)
    else:
        ports.append(int(port_spec))'''

    new_logic = '''    ports = []
    # Fixed: Handle comma-separated lists and dash-ranges correctly
    if "," in port_spec:
        for part in port_spec.split(","):
            part = part.strip()
            if "-" in part:
                start, end = part.split("-")
                for p in range(int(start), int(end) + 1):
                    ports.append(p)
            else:
                ports.append(int(part))
    elif "-" in port_spec:
        start, end = port_spec.split("-")
        for p in range(int(start), int(end) + 1):
            ports.append(p)
    else:
        ports.append(int(port_spec))'''

    content = content.replace(old_logic, new_logic)

    with open(resolver_path, 'w') as f:
        f.write(content)


def main():
    """Apply all four fixes."""
    print("[repair] Fixing priority ordering (Bug 1)...")
    fix_priority_ordering()

    print("[repair] Fixing CIDR host count calculation (Bug 2)...")
    fix_cidr_host_count()

    print("[repair] Fixing conflict resolution preference (Bug 3)...")
    fix_conflict_resolution()

    print("[repair] Fixing port specification parsing (Bug 4)...")
    fix_port_parsing()

    print("[repair] All fixes applied.")


if __name__ == "__main__":
    main()

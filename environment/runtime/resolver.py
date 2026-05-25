"""
Group resolver module.
Resolves named service groups to their constituent IP addresses and ports.
"""

import json
import os
import re


def load_groups(groups_path):
    """Load service group definitions from JSON."""
    if not os.path.exists(groups_path):
        raise FileNotFoundError(f"Groups file not found: {groups_path}")

    with open(groups_path, 'r') as f:
        return json.load(f)


def resolve_group(name, groups):
    """Resolve a group name to its IP list, or return the raw value if not a group."""
    if name in groups:
        return groups[name]
    # If not a group name, treat as a literal CIDR/IP
    return [name]


def resolve_ports(port_spec):
    """
    Resolve a port specification to a list of individual ports.
    Handles:
      - "any" -> ["any"]
      - "80" -> [80]
      - "80,443" -> [80, 443]
      - "8000-8010" -> [8000, 8001, ..., 8010]
    """
    if port_spec == "any":
        return ["any"]

    ports = []
    parts = re.split(r'[,\-]', port_spec)
    if len(parts) > 1:
        values = [int(p.strip()) for p in parts]
        for p in range(min(values), max(values) + 1):
            ports.append(p)
    else:
        ports.append(int(port_spec))

    return ports


def get_port_count(port_spec):
    """Get the number of ports matched by a port specification."""
    resolved = resolve_ports(port_spec)
    if resolved == ["any"]:
        return 65535
    return len(resolved)


def resolve_policy(policy, groups):
    """Resolve all group references in a policy to concrete values."""
    resolved = dict(policy)
    resolved['source_ips'] = resolve_group(policy['source'], groups)
    resolved['destination_ips'] = resolve_group(policy['destination'], groups)
    resolved['resolved_ports'] = resolve_ports(policy['ports'])
    resolved['port_count'] = get_port_count(policy['ports'])
    return resolved

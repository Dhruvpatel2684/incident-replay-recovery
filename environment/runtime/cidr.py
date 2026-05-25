"""
CIDR and subnet utility functions.
Provides host count calculation and subnet containment checks.
"""


def parse_cidr(cidr_str):
    """Parse a CIDR notation string into (network_address, prefix_length)."""
    if '/' not in cidr_str:
        # Treat bare IP as /32
        return cidr_str, 32

    parts = cidr_str.split('/')
    ip = parts[0]
    prefix_length = int(parts[1])
    return ip, prefix_length


def get_host_count(cidr_str):
    """
    Calculate the number of host addresses in a CIDR block.
    For example:
      /32 = 1 host
      /24 = 256 hosts
      /16 = 65536 hosts
      /8 = 16777216 hosts
    """
    _, prefix_length = parse_cidr(cidr_str)
    # BUG: Uses prefix_length instead of (32 - prefix_length)
    return 2 ** prefix_length


def ip_to_int(ip_str):
    """Convert dotted-quad IP to integer."""
    octets = ip_str.split('.')
    return (int(octets[0]) << 24) + (int(octets[1]) << 16) + \
           (int(octets[2]) << 8) + int(octets[3])


def cidr_contains(outer_cidr, inner_cidr):
    """Check if outer CIDR block contains the inner CIDR block."""
    outer_ip, outer_prefix = parse_cidr(outer_cidr)
    inner_ip, inner_prefix = parse_cidr(inner_cidr)

    # Inner prefix must be longer (more specific) or equal
    if inner_prefix < outer_prefix:
        return False

    outer_int = ip_to_int(outer_ip)
    inner_int = ip_to_int(inner_ip)

    # Mask to outer's prefix length
    mask = ((1 << 32) - 1) << (32 - outer_prefix)
    return (outer_int & mask) == (inner_int & mask)


def get_specificity(cidr_str):
    """
    Return specificity score for a CIDR range.
    More specific (smaller subnet) = higher specificity.
    Uses host count inversely - fewer hosts means more specific.
    """
    host_count = get_host_count(cidr_str)
    # Higher specificity for fewer hosts
    if host_count == 0:
        return float('inf')
    return 1.0 / host_count

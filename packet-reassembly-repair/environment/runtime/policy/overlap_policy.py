"""
Fragment overlap resolution policy.

When two fragments claim different data for the same byte position,
the overlap policy determines which value wins.

Policies:
- "first": The FIRST fragment to arrive (already written) wins.
  The existing byte in the buffer is kept, incoming is discarded.
- "last": The LAST fragment to arrive wins. The incoming byte
  overwrites the existing byte in the buffer.

For security-sensitive reassembly (IDS/IPS), "first" policy is
standard because it matches how most OS TCP/IP stacks behave,
making the IDS see the same data as the end host.
"""


def resolve_overlap(existing, incoming, policy):
    """Resolve conflicting byte values at an overlap position.

    Args:
        existing: byte value already in the reassembly buffer
        incoming: byte value from the new fragment
        policy: "first" or "last"

    Returns:
        The byte value that should be in the final datagram.
    """
    if policy == "first":
        # First-arriving data wins: keep incoming (new fragment)
        return incoming
    elif policy == "last":
        # Last-arriving data wins: overwrite with incoming
        return incoming
    else:
        return existing

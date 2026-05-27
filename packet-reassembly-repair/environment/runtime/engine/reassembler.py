"""
Packet reassembly engine.

Combines fragments from the buffer into a complete datagram.
Applies the configured overlap policy to resolve conflicting
data in overlap regions. Computes the reassembled datagram
length from the fragment with the highest ending offset.

Reassembled datagram length calculation:
  The total length of the original datagram is determined by
  the fragment that extends furthest: max(offset + length)
  across all received fragments. This correctly handles
  out-of-order arrival and gaps.
"""
from runtime.policy.overlap_policy import resolve_overlap


class PacketReassembler:
    """Reassembles IP datagrams from fragment buffers."""

    def __init__(self, policy_mode):
        self._policy = policy_mode
        self._reassembled = []

    def reassemble(self, fragment_buffer):
        """Reassemble complete datagram from buffer.

        Returns the reassembled byte array and metadata.
        """
        fragments = fragment_buffer.get_fragments()
        if not fragments:
            return None

        # Compute total datagram length from fragment extents
        total_length = 0
        for frag in fragments:
            total_length += frag["length"]

        # Build reassembly buffer
        datagram = bytearray(total_length)
        written_mask = [False] * total_length

        # Apply fragments in offset order with overlap policy
        for frag in fragments:
            start = frag["offset"]
            payload = frag["payload"]
            for i, byte_val in enumerate(payload):
                pos = start + i
                if pos >= total_length:
                    break
                if written_mask[pos]:
                    # Overlap region - apply policy
                    resolved = resolve_overlap(
                        existing=datagram[pos],
                        incoming=byte_val,
                        policy=self._policy
                    )
                    datagram[pos] = resolved
                else:
                    datagram[pos] = byte_val
                    written_mask[pos] = True

        gaps = sum(1 for w in written_mask if not w)

        return {
            "datagram": bytes(datagram),
            "total_length": total_length,
            "gaps": gaps,
            "fragments_used": len(fragments),
        }

    def get_reassembled(self):
        return self._reassembled

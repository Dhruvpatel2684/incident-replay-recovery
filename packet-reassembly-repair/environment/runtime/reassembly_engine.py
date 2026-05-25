"""
Reassembly Engine Module
Processes structured fragments and reconstructs sessions.
Handles deduplication, retransmission detection, and byte-range assembly.
"""


class SessionBuffer:
    """Represents the reassembly state for a single session."""

    def __init__(self, session_id):
        self.session_id = session_id
        self.fragments = {}  # offset -> (payload_len, timestamp, payload_hash)
        self.total_payload_bytes = 0
        self.is_complete = False
        self.fin_received = False
        self.fin_offset = 0

    def to_dict(self):
        """Serialize session state."""
        offsets = sorted(self.fragments.keys())
        return {
            "session_id": self.session_id,
            "total_fragments": len(self.fragments),
            "payload_bytes": self.total_payload_bytes,
            "is_complete": self.is_complete,
            "fragment_offsets": offsets,
        }


class ReassemblyEngine:
    """Manages reassembly of all sessions from fragments."""

    def __init__(self):
        self.sessions = {}
        self.retransmission_count = 0
        self.rtt_samples = []  # list of RTT measurements in ms

    def process_fragment(self, fragment):
        """Route fragment to appropriate handler."""
        frag_type = fragment["fragment_type"]
        session_id = fragment["session_id"]

        # Get or create session buffer
        if session_id not in self.sessions:
            self.sessions[session_id] = SessionBuffer(session_id)

        session = self.sessions[session_id]

        if frag_type == "SYN":
            self._handle_syn(session, fragment)
        elif frag_type == "DATA":
            self._handle_data(session, fragment)
        elif frag_type == "FIN":
            self._handle_fin(session, fragment)

    def _handle_syn(self, session, fragment):
        """SYN establishes the session start."""
        pass  # Session already created above

    def _handle_data(self, session, fragment):
        """
        Process a DATA fragment. Handles deduplication for retransmissions.
        """
        offset = fragment["seq_offset"]
        payload_len = fragment["payload_len"]
        timestamp = fragment["timestamp"]
        payload_hash = fragment["payload_hash"]
        flags = fragment["flags"]

        # Bug 3: Track ALL bytes (including retransmissions) before dedup.
        # This should only count bytes for new fragments, not retransmissions.
        # The byte counting happens unconditionally before the dedup check.
        session.total_payload_bytes += payload_len

        # Check for retransmission (same offset already seen)
        if offset in session.fragments:
            if flags == "DUPLICATE":
                self.retransmission_count += 1
                # Bug 4: RTT calculation has swapped operands.
                # Should be (retransmit_time - original_time) but computes
                # (original_time - retransmit_time), yielding negative RTT.
                existing_ts = session.fragments[offset][1]
                rtt = (existing_ts - timestamp) * 1000  # ms (BUG: reversed!)
                self.rtt_samples.append(rtt)
            return

        # New fragment — add to buffer
        session.fragments[offset] = (payload_len, timestamp, payload_hash)

    def _handle_fin(self, session, fragment):
        """
        FIN marks the end of the session stream.
        The FIN offset indicates total payload bytes transferred,
        so we add it to the byte counter for accounting purposes.
        """
        session.fin_received = True
        session.fin_offset = fragment["seq_offset"]
        # Bug 5: Adds fin_offset to total_payload_bytes.
        # FIN is a control message — its offset is just a position marker,
        # not additional data. This inflates the byte count significantly.
        session.total_payload_bytes += fragment["seq_offset"]

    def finalize(self):
        """
        Finalize all sessions: check completeness (no gaps in byte range).
        A session is complete if all byte offsets form a contiguous range
        from 0 to FIN offset with no gaps.
        """
        for session_id, session in self.sessions.items():
            if not session.fin_received:
                continue

            # Check contiguity: walk offsets and verify no gaps
            offsets = sorted(session.fragments.keys())
            if not offsets:
                continue

            is_contiguous = True
            expected_next = 0
            for offset in offsets:
                if offset != expected_next:
                    is_contiguous = False
                    break
                payload_len = session.fragments[offset][0]
                expected_next = offset + payload_len

            # Session is complete if contiguous and FIN offset matches end
            if is_contiguous and expected_next == session.fin_offset:
                session.is_complete = True

    def get_sessions(self):
        """Return all session states."""
        return {sid: session.to_dict() for sid, session in self.sessions.items()}

    def get_retransmission_count(self):
        """Return total retransmissions detected."""
        return self.retransmission_count

    def get_rtt_samples(self):
        """Return RTT samples from retransmission pairs."""
        return self.rtt_samples

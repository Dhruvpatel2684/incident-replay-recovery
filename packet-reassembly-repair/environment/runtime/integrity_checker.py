"""
Integrity Checker Module
Cross-flow validation, consistency verification, and statistics computation.

Post-reassembly checks:
1. Validates session consistency
2. Computes aggregate statistics
3. Generates deterministic integrity checksum
4. Estimates network quality metrics (RTT, jitter, loss rate)

The integrity checksum must be deterministic: same input → same hash.
"""

import hashlib
import statistics


class IntegrityChecker:
    """
    Validates reassembled sessions and computes aggregate metrics.
    """

    def __init__(self, sessions, retransmit_info):
        """
        Args:
            sessions: dict of flow_id → ReassembledSession
            retransmit_info: dict from FlowTracker with retransmit statistics
        """
        self._sessions = sessions
        self._retransmit_info = retransmit_info
        self._validated_sessions = {}
        self._stats = {}

    def validate(self):
        """Run validation and compute statistics."""
        self._validate_sessions()
        self._compute_aggregate_stats()

    def _validate_sessions(self):
        """Validate sessions and produce output dicts."""
        for flow_id, session in self._sessions.items():
            session_dict = session.to_dict()
            session_dict["_validated"] = True
            session_dict["_quality_grade"] = self._compute_quality_grade(session)
            self._validated_sessions[flow_id] = session_dict

    def _compute_quality_grade(self, session):
        """Assign quality grade A/B/C/D/F based on session health."""
        if session.fragment_count == 0:
            return "F"
        if session.is_complete:
            if (session.ttl_max - session.ttl_min) <= 5:
                return "A"
            return "B"
        if session.gap_count <= 1:
            return "C"
        if session.gap_count <= 3:
            return "D"
        return "F"

    def _compute_aggregate_stats(self):
        """Compute aggregate statistics across all validated sessions."""
        total_flows = len(self._validated_sessions)

        complete_flows = sum(
            1 for s in self._validated_sessions.values()
            if s["is_complete"]
        )
        total_bytes = sum(
            s["total_payload_bytes"]
            for s in self._validated_sessions.values()
        )
        total_frags = sum(
            s["fragment_count"]
            for s in self._validated_sessions.values()
        )
        max_flow_bytes = max(
            (s["total_payload_bytes"] for s in self._validated_sessions.values()),
            default=0
        )

        # RTT from retransmit timestamp pairs
        rtt_samples = self._retransmit_info.get("rtt_samples", [])
        rtt_ms_values = []
        for orig_ts, retransmit_ts in rtt_samples:
            rtt_ms = (retransmit_ts - orig_ts) * 1000.0
            rtt_ms_values.append(rtt_ms)

        avg_rtt = statistics.mean(rtt_ms_values) if rtt_ms_values else 0.0
        rtt_jitter = statistics.stdev(rtt_ms_values) if len(rtt_ms_values) > 1 else 0.0

        # Packet loss estimation
        # Formula: observed_retransmits / total_observed_packets
        # where total_observed = unique_fragments + retransmits
        total_retransmits = self._retransmit_info.get("total_retransmits", 0)
        loss_rate = (
            total_retransmits / total_frags
            if total_frags > 0 else 0.0
        )

        # Integrity checksum — deterministic hash over canonical output
        checksum = self._compute_integrity_checksum()

        self._stats = {
            "total_flows": total_flows,
            "complete_flows": complete_flows,
            "total_payload_bytes": total_bytes,
            "total_retransmits": total_retransmits,
            "avg_rtt_ms": round(avg_rtt, 3),
            "rtt_jitter_ms": round(rtt_jitter, 3),
            "integrity_checksum": checksum,
            "avg_fragments_per_flow": round(total_frags / total_flows, 2) if total_flows else 0,
            "max_single_flow_bytes": max_flow_bytes,
            "packet_loss_estimate": round(loss_rate, 6),
        }

    def _compute_integrity_checksum(self):
        """
        Generate deterministic integrity hash over session records.

        Processes sessions in canonical order (sorted by flow_id) and
        hashes a fixed set of fields per session. The first 16 hex chars
        of the SHA-256 digest form the checksum.
        """
        hasher = hashlib.sha256()

        # Process in consistent order for determinism
        for flow_id in self._validated_sessions.keys():
            session = self._validated_sessions[flow_id]
            record = (
                f"{flow_id}:"
                f"{session['fragment_count']}:"
                f"{session['total_payload_bytes']}:"
                f"{session['is_complete']}:"
                f"{session['gap_count']};"
            )
            hasher.update(record.encode("utf-8"))

        return hasher.hexdigest()[:16]

    def get_validated_sessions(self):
        """Return validated session dicts."""
        return self._validated_sessions

    def get_integrity_stats(self):
        """Return aggregate statistics."""
        return self._stats

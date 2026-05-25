"""
Repair script for packet-reassembly-repair task.
Re-processes the raw fragment capture with correct logic and overwrites
the broken output files with correct results.

Fixes applied:
1. fragment_parser.py Bug 1: FIN offset — remove erroneous +1 adjustment
2. fragment_parser.py Bug 2: LAST_FRAGMENT payload_len — don't subtract 1
3. reassembly_engine.py Bug 3: Only count bytes for NEW fragments (not retransmits)
4. reassembly_engine.py Bug 4: RTT = (retransmit_time - original_time), not reversed
5. reassembly_engine.py Bug 5: FIN handler should NOT add fin_offset to byte count
6. session_writer.py Bug 6: Sort sessions by session_id before computing checksum
7. session_writer.py Bug 7: Bloom FPR formula = sessions / (sessions + fragments)

Bug Interactions (difficulty design):
- Fixing Bug 1 (FIN +1) alone still leaves is_complete=False because Bug 2 makes
  the last fragment 1 byte short, so expected_next != fin_offset
- Fixing Bug 3 (retransmit bytes) alone still shows wrong total_bytes because
  Bug 5 (FIN bytes) also inflates the count
- The checksum (Bug 6) depends on ALL other values being correct first —
  fixing sort order alone gives wrong hash if payload_bytes are still inflated
"""

import json
import hashlib
import os

RUNTIME_DIR = "/app/runtime"
CAPTURE_FILE = os.path.join(RUNTIME_DIR, "capture.fragments")


# ============================================================
# FIXED Fragment Parser
# ============================================================

def parse_fragment_line(line):
    """Parse a single capture line into a structured fragment dict."""
    line = line.strip()
    if not line or line.startswith("#"):
        return None

    parts = line.split("|")
    if len(parts) != 7:
        return None

    timestamp_str, session_id, frag_type, seq_offset_str, payload_len_str, flags, payload_hash = parts
    timestamp = float(timestamp_str)

    fragment = {
        "timestamp": timestamp,
        "session_id": session_id,
        "fragment_type": frag_type,
        "flags": flags,
        "payload_hash": payload_hash,
    }

    # FIX for Bug 1: FIN offset is just the value in the field, no +1.
    # The offset already represents the correct end-of-stream position.
    fragment["seq_offset"] = int(seq_offset_str)

    # FIX for Bug 2: payload_len is always the raw value from the capture.
    # LAST_FRAGMENT does NOT have an extra delimiter byte — the field
    # already contains the exact payload data length.
    fragment["payload_len"] = int(payload_len_str)

    return fragment


def load_fragments():
    """Load all fragments from the capture file, sorted by timestamp."""
    fragments = []
    with open(CAPTURE_FILE, "r") as f:
        for line in f:
            fragment = parse_fragment_line(line)
            if fragment is not None:
                fragments.append(fragment)

    fragments.sort(key=lambda f: f["timestamp"])
    return fragments


# ============================================================
# FIXED Reassembly Engine
# ============================================================

class SessionBuffer:
    def __init__(self, session_id):
        self.session_id = session_id
        self.fragments = {}
        self.total_payload_bytes = 0
        self.is_complete = False
        self.fin_received = False
        self.fin_offset = 0

    def to_dict(self):
        offsets = sorted(self.fragments.keys())
        return {
            "session_id": self.session_id,
            "total_fragments": len(self.fragments),
            "payload_bytes": self.total_payload_bytes,
            "is_complete": self.is_complete,
            "fragment_offsets": offsets,
        }


class ReassemblyEngine:
    def __init__(self):
        self.sessions = {}
        self.retransmission_count = 0
        self.rtt_samples = []

    def process_fragment(self, fragment):
        frag_type = fragment["fragment_type"]
        session_id = fragment["session_id"]

        if session_id not in self.sessions:
            self.sessions[session_id] = SessionBuffer(session_id)

        session = self.sessions[session_id]

        if frag_type == "SYN":
            pass
        elif frag_type == "DATA":
            self._handle_data(session, fragment)
        elif frag_type == "FIN":
            self._handle_fin(session, fragment)

    def _handle_data(self, session, fragment):
        offset = fragment["seq_offset"]
        payload_len = fragment["payload_len"]
        timestamp = fragment["timestamp"]
        payload_hash = fragment["payload_hash"]
        flags = fragment["flags"]

        # Check for retransmission (same offset already seen)
        if offset in session.fragments:
            if flags == "DUPLICATE":
                self.retransmission_count += 1
                # FIX for Bug 4: RTT = retransmit_time - original_time (positive)
                existing_ts = session.fragments[offset][1]
                rtt = (timestamp - existing_ts) * 1000  # ms
                self.rtt_samples.append(rtt)
                # Keep original — don't replace
            return

        # FIX for Bug 3: Only count bytes for NEW (non-duplicate) fragments.
        # This line is AFTER the dedup return, so retransmit bytes aren't counted.
        session.fragments[offset] = (payload_len, timestamp, payload_hash)
        session.total_payload_bytes += payload_len

    def _handle_fin(self, session, fragment):
        """FIX for Bug 5: FIN only sets control state, does NOT add to bytes."""
        session.fin_received = True
        session.fin_offset = fragment["seq_offset"]
        # NO byte counting for FIN — it's a control message, not data

    def finalize(self):
        for session_id, session in self.sessions.items():
            if not session.fin_received:
                continue

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

            if is_contiguous and expected_next == session.fin_offset:
                session.is_complete = True

    def get_sessions(self):
        return {sid: session.to_dict() for sid, session in self.sessions.items()}

    def get_retransmission_count(self):
        return self.retransmission_count

    def get_rtt_samples(self):
        return self.rtt_samples


# ============================================================
# FIXED Session Writer
# ============================================================

def compute_reassembly_checksum(sessions):
    """FIX for Bug 6: Sort sessions by session_id for deterministic hash."""
    hash_input = ""
    for session_id in sorted(sessions.keys()):  # FIX: sorted iteration
        state = sessions[session_id]
        hash_input += f"{session_id}:{state['total_fragments']}:{state['payload_bytes']}:"
        hash_input += f"{state['is_complete']}:{len(state['fragment_offsets'])}|"

    return hashlib.sha256(hash_input.encode()).hexdigest()[:16]


def compute_bloom_fpr(total_sessions, total_fragments):
    """FIX for Bug 7: Correct formula is sessions / (sessions + fragments)."""
    return total_sessions / (total_sessions + total_fragments)


def format_output(sessions, retransmissions, rtt_samples):
    """Write corrected output files."""
    output_dir = RUNTIME_DIR

    # Write sessions.jsonl
    jsonl_path = os.path.join(output_dir, "sessions.jsonl")
    with open(jsonl_path, "w") as f:
        for session_id in sorted(sessions.keys()):
            state = sessions[session_id]
            record = {
                "session_id": state["session_id"],
                "total_fragments": state["total_fragments"],
                "payload_bytes": state["payload_bytes"],
                "is_complete": state["is_complete"],
                "fragment_offsets": state["fragment_offsets"],
            }
            f.write(json.dumps(record) + "\n")

    # Compute stats
    total_sessions = len(sessions)
    total_bytes = sum(s["payload_bytes"] for s in sessions.values())
    complete_count = sum(1 for s in sessions.values() if s["is_complete"])
    total_fragments = sum(s["total_fragments"] for s in sessions.values())
    avg_frags = total_fragments / total_sessions if total_sessions > 0 else 0

    avg_rtt = sum(rtt_samples) / len(rtt_samples) if rtt_samples else 0.0

    max_offset = 0
    for s in sessions.values():
        if s["fragment_offsets"]:
            local_max = max(s["fragment_offsets"])
            if local_max > max_offset:
                max_offset = local_max

    checksum = compute_reassembly_checksum(sessions)
    bloom_fpr = compute_bloom_fpr(total_sessions, total_fragments)

    stats = {
        "total_sessions": total_sessions,
        "total_bytes_reassembled": total_bytes,
        "retransmissions_detected": retransmissions,
        "complete_sessions": complete_count,
        "reassembly_checksum": checksum,
        "avg_fragments_per_session": round(avg_frags, 2),
        "estimated_avg_rtt_ms": round(avg_rtt, 2),
        "max_fragment_offset": max_offset,
        "bloom_filter_fpr": round(bloom_fpr, 6),
    }

    stats_path = os.path.join(output_dir, "reassembly_stats.json")
    with open(stats_path, "w") as f:
        json.dump(stats, f, indent=2)

    return jsonl_path, stats_path


# ============================================================
# Main execution
# ============================================================

def main():
    # Load events with fixed parser
    fragments = load_fragments()

    # Process with fixed engine
    engine = ReassemblyEngine()
    for fragment in fragments:
        engine.process_fragment(fragment)
    engine.finalize()

    # Get results
    sessions = engine.get_sessions()
    retransmissions = engine.get_retransmission_count()
    rtt_samples = engine.get_rtt_samples()

    # Write output with fixed writer
    format_output(
        sessions=sessions,
        retransmissions=retransmissions,
        rtt_samples=rtt_samples,
    )

    print(f"Repair complete. Processed {len(fragments)} fragments.")
    print(f"Sessions: {len(sessions)}")
    print(f"Retransmissions: {retransmissions}")


if __name__ == "__main__":
    main()

"""
Session Writer Module
Generates sessions.jsonl and reassembly_stats.json from reconstructed sessions.
"""

import json
import hashlib


def compute_reassembly_checksum(sessions):
    """
    Compute a deterministic hash of the reassembly output for integrity verification.
    Encodes per-session fields into a canonical string representation.
    """
    # Bug 6: Iterates over sessions dict without sorting by session_id.
    # Dict iteration order depends on insertion order (Python 3.7+), which
    # follows the order sessions first appeared in the capture file.
    # Since sessions arrive interleaved (not in lexicographic order),
    # this produces a non-deterministic hash relative to the expected
    # canonical (sorted) output.
    hash_input = ""
    for session_id, state in sessions.items():
        hash_input += f"{session_id}:{state['total_fragments']}:{state['payload_bytes']}:"
        hash_input += f"{state['is_complete']}:{len(state['fragment_offsets'])}|"

    return hashlib.sha256(hash_input.encode()).hexdigest()[:16]


def compute_bloom_fpr(total_sessions, total_fragments):
    """
    Estimate bloom filter false-positive rate for the session index.
    Formula: num_sessions / (num_sessions + total_fragment_slots)
    """
    # Bug 7: Wrong denominator. Uses (sessions * fragments) instead of
    # (sessions + fragments). This produces a much smaller FPR value.
    return total_sessions / (total_sessions * total_fragments)


def format_output(sessions, retransmissions, rtt_samples, output_dir):
    """
    Write final output files:
    - sessions.jsonl: one JSON line per session (sorted by session_id)
    - reassembly_stats.json: summary statistics
    """
    import os

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

    # RTT estimation
    avg_rtt = sum(rtt_samples) / len(rtt_samples) if rtt_samples else 0.0

    # Max offset across all sessions
    max_offset = 0
    for s in sessions.values():
        if s["fragment_offsets"]:
            local_max = max(s["fragment_offsets"])
            if local_max > max_offset:
                max_offset = local_max

    # Checksum
    checksum = compute_reassembly_checksum(sessions)

    # Bloom filter FPR
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

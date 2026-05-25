"""
Oracle repair script for packet-reassembly-repair task.

Patches the buggy runtime modules and re-runs the pipeline to produce
correct output. Fixes 7 bugs across 3 modules:

Bug 1 (flow_tracker.py): Implicit duplicates incorrectly counted as retransmissions.
  - Fix: In FlowState.ingest_data(), when is_dup is True for a regular DATA
    fragment, increment duplicate_count (not retransmit_count) and do NOT
    append to retransmit_pairs.

Bug 2 (flow_tracker.py): Consequence of Bug 1 — RTT samples polluted with
  implicit duplicate timestamps. Fix is same as Bug 1 (no separate code change).

Bug 3 (reassembly_engine.py): _compute_payload_total() subtracts 1 byte from
  the last fragment of flows with ≤3 fragments ("TLS correction").
  - Fix: Remove the special case — always use frag["data_len"] directly.

Bug 4 (reassembly_engine.py): Completeness check uses >= instead of ==.
  - Fix: Change `expected_next_byte >= session.fin_offset` to
    `expected_next_byte == session.fin_offset`.

Bug 5 (integrity_checker.py): packet_loss_estimate uses wrong denominator.
  - Fix: Change `total_retransmits / total_frags` to
    `total_retransmits / (total_frags + total_retransmits)`.

Bug 6 (integrity_checker.py): Checksum iterates dict keys without sorting.
  - Fix: Change `self._validated_sessions.keys()` to
    `sorted(self._validated_sessions.keys())`.

Bug 7 (session_writer.py): Per-flow retransmit counts include implicit dups.
  - Fix: This is automatically fixed when Bug 1 is fixed, because
    per_flow_retransmits will no longer include implicit duplicates.

Bug Interactions:
  - Bug 4 (>=) masks Bug 3's effect on is_complete. Fixing Bug 4 alone makes
    6 flows incomplete. Must fix BOTH 3 and 4 together.
  - Bug 7 is downstream of Bug 1. Fixing Bug 1 automatically fixes Bug 7.
  - Bug 6 (checksum) depends on ALL other values being correct. It's the
    "final boss" test — only passes when everything else is fixed.
"""

import os
import sys

# Paths
RUNTIME_DIR = "/app/runtime"
CAPTURE_FILE = os.path.join(RUNTIME_DIR, "capture.fragments")

sys.path.insert(0, RUNTIME_DIR)

# Import the parser (it's correct — no bugs there)
from fragment_parser import parse_capture_file

# We'll reimplement the buggy modules inline with corrections

from collections import OrderedDict
import hashlib
import statistics
import json


# ============================================================
# FIXED FlowTracker (Bugs 1, 2 fixed)
# ============================================================

class FixedFlowState:
    def __init__(self, flow_id, syn_fragment):
        self.flow_id = flow_id
        self.fragments = []
        self.syn_timestamp = syn_fragment["timestamp"]
        self.fin_timestamp = None
        self.fin_byte_offset = None
        self.retransmit_pairs = []
        self.retransmit_count = 0
        self.duplicate_count = 0
        self._dedup_cache = OrderedDict()

    def ingest_data(self, fragment):
        is_explicit_retransmit = (fragment["proto_type"] == "RETRANSMIT")

        if is_explicit_retransmit:
            key = (fragment["byte_offset"], fragment["data_len"])
            if key in self._dedup_cache:
                original_ts = self._dedup_cache[key]
                self.retransmit_pairs.append((original_ts, fragment["timestamp"]))
            self.retransmit_count += 1
            return False

        # Regular DATA — check dedup
        key = (fragment["byte_offset"], fragment["data_len"])
        if key in self._dedup_cache:
            # FIX: Only increment duplicate_count, NO RTT sample
            self.duplicate_count += 1
            return False

        # New fragment
        self._dedup_cache[key] = fragment["timestamp"]
        self.fragments.append(fragment)
        return True

    def receive_fin(self, fragment):
        self.fin_timestamp = fragment["timestamp"]
        self.fin_byte_offset = fragment["byte_offset"]

    def finalize(self):
        self.fragments.sort(key=lambda f: f["byte_offset"])


def run_fixed_tracker(fragments):
    flows = {}
    for frag in fragments:
        flow_id = frag["flow_id"]
        proto = frag["proto_type"]

        if proto == "SYN":
            if flow_id not in flows:
                flows[flow_id] = FixedFlowState(flow_id, frag)
            continue

        if flow_id not in flows:
            continue

        flow = flows[flow_id]
        if proto == "FIN":
            flow.receive_fin(frag)
        elif proto in ("DATA", "RETRANSMIT"):
            flow.ingest_data(frag)

    for flow in flows.values():
        flow.finalize()

    # Aggregate retransmit info
    total_retransmits = 0
    all_rtt_pairs = []
    per_flow = {}
    for flow_id, flow in flows.items():
        total_retransmits += flow.retransmit_count
        all_rtt_pairs.extend(flow.retransmit_pairs)
        if flow.retransmit_count > 0:
            per_flow[flow_id] = flow.retransmit_count

    retransmit_info = {
        "total_retransmits": total_retransmits,
        "total_duplicates": sum(f.duplicate_count for f in flows.values()),
        "rtt_samples": all_rtt_pairs,
        "per_flow_retransmits": per_flow,
    }

    return flows, retransmit_info


# ============================================================
# FIXED ReassemblyEngine (Bugs 3, 4 fixed)
# ============================================================

def reassemble_flow(flow_state):
    fragments = flow_state.fragments
    if not fragments:
        return {
            "flow_id": flow_state.flow_id,
            "total_payload_bytes": 0,
            "fragment_count": 0,
            "is_complete": False,
            "gap_count": 0,
            "byte_offsets": [],
            "max_byte_offset": 0,
            "ttl_spread": 0,
            "duration_ms": 0.0,
        }

    fragment_count = len(fragments)
    fin_offset = flow_state.fin_byte_offset

    first_ts = fragments[0]["timestamp"]
    last_ts = flow_state.fin_timestamp or fragments[-1]["timestamp"]
    duration_ms = (last_ts - first_ts) * 1000.0

    expected_next_byte = 0
    total_bytes = 0
    gap_count = 0
    byte_offsets = []
    ttl_min = 255
    ttl_max = 0

    for frag in fragments:
        offset = frag["byte_offset"]
        length = frag["data_len"]

        if frag["ttl"] < ttl_min:
            ttl_min = frag["ttl"]
        if frag["ttl"] > ttl_max:
            ttl_max = frag["ttl"]

        byte_offsets.append(offset)

        if offset > expected_next_byte:
            gap_count += 1

        expected_next_byte = offset + length
        # FIX Bug 3: Always use full data_len (no -1 correction)
        total_bytes += length

    max_offset = fragments[-1]["byte_offset"]

    # FIX Bug 4: Use == not >=
    is_complete = False
    if fin_offset is not None:
        if gap_count == 0 and expected_next_byte == fin_offset:
            is_complete = True

    return {
        "flow_id": flow_state.flow_id,
        "total_payload_bytes": total_bytes,
        "fragment_count": fragment_count,
        "is_complete": is_complete,
        "gap_count": gap_count,
        "byte_offsets": byte_offsets,
        "max_byte_offset": max_offset,
        "ttl_spread": ttl_max - ttl_min,
        "duration_ms": round(duration_ms, 3),
    }


# ============================================================
# FIXED IntegrityChecker (Bugs 5, 6 fixed)
# ============================================================

def compute_stats(sessions, retransmit_info):
    total_flows = len(sessions)
    complete_flows = sum(1 for s in sessions.values() if s["is_complete"])
    total_bytes = sum(s["total_payload_bytes"] for s in sessions.values())
    total_frags = sum(s["fragment_count"] for s in sessions.values())
    max_flow_bytes = max(s["total_payload_bytes"] for s in sessions.values())

    rtt_samples = retransmit_info.get("rtt_samples", [])
    rtt_ms_values = [(r - o) * 1000.0 for o, r in rtt_samples]
    avg_rtt = statistics.mean(rtt_ms_values) if rtt_ms_values else 0.0
    rtt_jitter = statistics.stdev(rtt_ms_values) if len(rtt_ms_values) > 1 else 0.0

    total_retransmits = retransmit_info["total_retransmits"]

    # FIX Bug 5: Correct denominator
    loss_rate = total_retransmits / (total_frags + total_retransmits) if (total_frags + total_retransmits) > 0 else 0.0

    # FIX Bug 6: Sort by flow_id for deterministic checksum
    hasher = hashlib.sha256()
    for flow_id in sorted(sessions.keys()):
        s = sessions[flow_id]
        record = f"{flow_id}:{s['fragment_count']}:{s['total_payload_bytes']}:{s['is_complete']}:{s['gap_count']};"
        hasher.update(record.encode("utf-8"))
    checksum = hasher.hexdigest()[:16]

    return {
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


# ============================================================
# FIXED SessionWriter (Bug 7 auto-fixed by Bug 1 fix)
# ============================================================

def write_output(sessions, retransmit_info, stats, output_dir):
    per_flow_retransmits = retransmit_info.get("per_flow_retransmits", {})

    # Enrich with per-flow retransmit counts (now correct due to Bug 1 fix)
    enriched = {}
    for flow_id, session in sessions.items():
        s = dict(session)
        s["retransmit_count"] = per_flow_retransmits.get(flow_id, 0)
        enriched[flow_id] = s

    # Write sessions.jsonl
    jsonl_path = os.path.join(output_dir, "sessions.jsonl")
    with open(jsonl_path, "w") as f:
        for flow_id in sorted(enriched.keys()):
            record = {k: v for k, v in enriched[flow_id].items() if not k.startswith("_")}
            # Add fingerprint
            raw = f"{record['flow_id']}:{record['total_payload_bytes']}:{record['fragment_count']}"
            record["fingerprint"] = hashlib.md5(raw.encode()).hexdigest()[:8]
            f.write(json.dumps(record, sort_keys=True) + "\n")

    # Write stats
    stats_path = os.path.join(output_dir, "reassembly_stats.json")
    with open(stats_path, "w") as f:
        json.dump(stats, f, indent=2, sort_keys=True)
        f.write("\n")


# ============================================================
# Main
# ============================================================

def main():
    # Parse capture (parser is correct)
    fragments = parse_capture_file(CAPTURE_FILE)
    print(f"[repair] Parsed {len(fragments)} fragments")

    # Fixed tracking
    flows, retransmit_info = run_fixed_tracker(fragments)
    print(f"[repair] Tracked {len(flows)} flows, {retransmit_info['total_retransmits']} retransmits")

    # Fixed reassembly
    sessions = {}
    for flow_id, flow_state in flows.items():
        sessions[flow_id] = reassemble_flow(flow_state)

    # Fixed stats
    stats = compute_stats(sessions, retransmit_info)
    print(f"[repair] Stats: {stats['total_payload_bytes']} bytes, "
          f"{stats['complete_flows']} complete, checksum={stats['integrity_checksum']}")

    # Write output
    write_output(sessions, retransmit_info, stats, RUNTIME_DIR)
    print("[repair] Output written successfully")


if __name__ == "__main__":
    main()

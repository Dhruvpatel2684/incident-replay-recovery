"""
Session Writer Module
Serializes validated session records and statistics to output files.

Output files:
  sessions.jsonl — One JSON record per flow (sorted by flow_id)
  reassembly_stats.json — Aggregate statistics and integrity checksum

The writer applies final transformations:
  - Filters internal metadata fields (prefixed with _)
  - Rounds floating-point values for deterministic output
  - Ensures consistent JSON serialization (sorted keys within each record)
"""

import json
import os
import hashlib


def _filter_internal_fields(session_dict):
    """
    Remove internal metadata fields (prefixed with '_') from a session dict.
    These are used for intermediate processing but shouldn't appear in output.
    """
    return {k: v for k, v in session_dict.items() if not k.startswith("_")}


def _compute_flow_fingerprint(session):
    """
    Generate a short fingerprint for each flow record.
    Used for quick visual verification during debugging.

    Fingerprint = md5(flow_id + total_bytes + fragment_count)[:8]
    This is NOT the integrity checksum — it's a per-record helper.
    """
    raw = f"{session['flow_id']}:{session['total_payload_bytes']}:{session['fragment_count']}"
    return hashlib.md5(raw.encode()).hexdigest()[:8]


def write_sessions_jsonl(sessions, output_path):
    """
    Write sessions.jsonl — one JSON record per flow.

    Records are written in sorted order by flow_id for deterministic output.
    Each record is self-contained JSON with sorted keys.
    """
    with open(output_path, "w") as f:
        for flow_id in sorted(sessions.keys()):
            session = sessions[flow_id]
            record = _filter_internal_fields(session)
            record["fingerprint"] = _compute_flow_fingerprint(record)
            f.write(json.dumps(record, sort_keys=True) + "\n")


def write_stats_json(stats, output_path):
    """Write reassembly_stats.json with sorted keys."""
    with open(output_path, "w") as f:
        json.dump(stats, f, indent=2, sort_keys=True)
        f.write("\n")


def write_output(validated_sessions, retransmit_info, stats_extra, output_dir):
    """
    Main output function — writes both output files.

    Also enriches sessions with per-flow retransmit counts before writing.
    The retransmit_count per flow comes from the per_flow_retransmits dict
    in retransmit_info.
    """
    per_flow_retransmits = retransmit_info.get("per_flow_retransmits", {})
    enriched_sessions = {}

    for flow_id, session in validated_sessions.items():
        enriched = dict(session)
        # *** BUG 7: Per-flow retransmit count includes implicit duplicates ***
        # The per_flow_retransmits dict already has inflated counts due to
        # Bug 1 (implicit duplicates counted as retransmits). Additionally,
        # this code falls back to 0 for flows not in the dict, which is
        # correct — but the dict itself has wrong values for flows that
        # received out-of-order duplicates (like flow-alpha, flow-gamma,
        # flow-zeta, flow-theta, flow-lambda which each have 1 implicit dup).
        #
        # The visible effect: flows like flow-alpha show retransmit_count=2
        # (1 real + 1 implicit) instead of 1 (real only).
        enriched["retransmit_count"] = per_flow_retransmits.get(flow_id, 0)
        enriched_sessions[flow_id] = enriched

    jsonl_path = os.path.join(output_dir, "sessions.jsonl")
    stats_path = os.path.join(output_dir, "reassembly_stats.json")

    write_sessions_jsonl(enriched_sessions, jsonl_path)
    write_stats_json(stats_extra, stats_path)

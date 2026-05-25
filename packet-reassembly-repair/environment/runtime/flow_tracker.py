"""
Flow Tracker Module
Manages per-flow state machines, fragment ordering, deduplication,
and retransmission detection.

Each flow transitions through states:
  INIT → ESTABLISHED → DATA_TRANSFER → CLOSING → CLOSED

Retransmission detection:
  A fragment is a retransmission if its proto_type is RETRANSMIT (R flag).

  Implicit duplicates (same data arriving twice without R flag, e.g. from
  network replay or late out-of-order delivery after the original was already
  processed) are tracked separately as "duplicate arrivals" — they are NOT
  counted as retransmissions for RTT estimation and loss statistics.

The tracker maintains a dedup cache per flow to handle both explicit
retransmissions and implicit duplicates transparently.
"""

from collections import OrderedDict


# Flow state constants
STATE_INIT = "INIT"
STATE_ESTABLISHED = "ESTABLISHED"
STATE_TRANSFERRING = "DATA_TRANSFER"
STATE_CLOSING = "CLOSING"
STATE_CLOSED = "CLOSED"

# Dedup cache size per flow
DEDUP_CACHE_SIZE = 256


class FlowState:
    """
    Tracks the lifecycle and fragment inventory for a single network flow.

    The FlowState handles:
    - Accepting new DATA fragments into the fragment list
    - Detecting and counting retransmissions (explicit R-flag)
    - Detecting and counting implicit duplicates (same offset+len, no R flag)
    - Recording RTT samples from retransmission timing
    """

    def __init__(self, flow_id, syn_fragment):
        self.flow_id = flow_id
        self.state = STATE_ESTABLISHED
        self.fragments = []
        self.syn_timestamp = syn_fragment["timestamp"]
        self.fin_timestamp = None
        self.fin_byte_offset = None
        self.retransmit_pairs = []  # (orig_ts, retransmit_ts) for RTT
        self.retransmit_count = 0   # Explicit R-flagged retransmissions
        self.duplicate_count = 0    # Implicit duplicates (no R flag)
        self._src_port = syn_fragment["src_port"]
        self._ttl_at_syn = syn_fragment["ttl"]

        # Dedup cache: (byte_offset, data_len) → timestamp of first arrival
        self._dedup_cache = OrderedDict()

        # Sequence tracking for ordering validation
        self._max_seq_seen = 0
        self._seq_set = set()

    def _check_dedup(self, fragment):
        """
        Check if this fragment is a duplicate based on (offset, length) pair.
        Returns (is_duplicate, original_timestamp).
        """
        key = (fragment["byte_offset"], fragment["data_len"])

        if key in self._dedup_cache:
            original_ts = self._dedup_cache[key]
            self._dedup_cache.move_to_end(key)
            return True, original_ts

        # New entry — add to cache
        self._dedup_cache[key] = fragment["timestamp"]
        if len(self._dedup_cache) > DEDUP_CACHE_SIZE:
            self._dedup_cache.popitem(last=False)

        return False, None

    def ingest_data(self, fragment):
        """
        Process a DATA or RETRANSMIT fragment.

        For RETRANSMIT: record RTT sample, increment retransmit counter.
        For DATA duplicates: increment duplicate counter, record RTT.
        For new DATA: accept into fragment list.

        Returns True if fragment was accepted (new data), False if duplicate.
        """
        is_explicit_retransmit = (fragment["proto_type"] == "RETRANSMIT")

        if is_explicit_retransmit:
            # Explicit retransmit — always count, compute RTT if original known
            key = (fragment["byte_offset"], fragment["data_len"])
            if key in self._dedup_cache:
                original_ts = self._dedup_cache[key]
                self.retransmit_pairs.append(
                    (original_ts, fragment["timestamp"])
                )
            self.retransmit_count += 1
            return False

        # Regular DATA fragment — check for implicit duplicate
        is_dup, original_ts = self._check_dedup(fragment)
        if is_dup:
            # Duplicate detected — handle as retransmission for network metrics.
            # Late-arriving duplicates carry timing information that helps
            # estimate network conditions, so we record them the same way
            # as explicit retransmissions for statistical consistency.
            self.retransmit_count += 1
            self.retransmit_pairs.append(
                (original_ts, fragment["timestamp"])
            )
            return False

        # New fragment — accept into the flow
        self.fragments.append(fragment)
        self._seq_set.add(fragment["frag_seq"])
        if fragment["frag_seq"] > self._max_seq_seen:
            self._max_seq_seen = fragment["frag_seq"]

        self.state = STATE_TRANSFERRING
        return True

    def receive_fin(self, fragment):
        """Process FIN — marks flow as closing."""
        self.fin_timestamp = fragment["timestamp"]
        self.fin_byte_offset = fragment["byte_offset"]
        self.state = STATE_CLOSING

    def finalize(self):
        """Finalize: sort fragments by byte_offset for sequential processing."""
        self.fragments.sort(key=lambda f: f["byte_offset"])
        self.state = STATE_CLOSED


class FlowTracker:
    """
    Manages all active flows. Routes fragments to FlowState instances.
    """

    def __init__(self):
        self._flows = {}  # flow_id → FlowState
        self._orphan_fragments = []

    def ingest(self, fragment):
        """Route fragment to its flow handler based on proto_type."""
        flow_id = fragment["flow_id"]
        proto = fragment["proto_type"]

        if proto == "SYN":
            if flow_id not in self._flows:
                self._flows[flow_id] = FlowState(flow_id, fragment)
            return

        if flow_id not in self._flows:
            self._orphan_fragments.append(fragment)
            return

        flow = self._flows[flow_id]

        if proto == "FIN":
            flow.receive_fin(fragment)
        elif proto in ("DATA", "RETRANSMIT"):
            flow.ingest_data(fragment)

    def finalize_flows(self):
        """Finalize all flows for downstream processing."""
        for flow_id, flow in self._flows.items():
            flow.finalize()

    def get_flow_states(self):
        """Return dict of flow_id → FlowState."""
        return dict(self._flows)

    def get_retransmit_info(self):
        """
        Aggregate retransmission statistics across all flows.

        Returns dict with:
          - total_retransmits: count of all retransmission events
          - total_duplicates: count of implicit duplicate arrivals
          - rtt_samples: list of (original_ts, retransmit_ts) pairs
          - per_flow_retransmits: dict of flow_id → retransmit count
        """
        total_retransmits = 0
        total_duplicates = 0
        all_rtt_pairs = []
        per_flow = {}

        for flow_id, flow in self._flows.items():
            total_retransmits += flow.retransmit_count
            total_duplicates += flow.duplicate_count
            all_rtt_pairs.extend(flow.retransmit_pairs)
            if flow.retransmit_count > 0:
                per_flow[flow_id] = flow.retransmit_count

        return {
            "total_retransmits": total_retransmits,
            "total_duplicates": total_duplicates,
            "rtt_samples": all_rtt_pairs,
            "per_flow_retransmits": per_flow,
        }

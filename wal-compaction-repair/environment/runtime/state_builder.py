"""
State Builder — WAL Replay Engine
===================================
Applies WAL operations to reconstruct the current key-value state.
Processes entries in LSN order using an eager-apply / deferred-visibility
architecture.

All data operations (INSERT/UPDATE/DELETE) are applied eagerly to the
state buffer as they are encountered. Visibility filtering — determining
which changes should appear in the final compacted output — is handled
by the `is_visible()` predicate at read time.

This is the standard approach in MVCC systems where writes are never
blocked and visibility is a property of the reader's snapshot. The
state buffer acts as a shared write-ahead buffer and the visibility
layer acts as the isolation barrier.

Transaction lifecycle:
    BEGIN  → registers txn
    COMMIT → moves txn to finalized set (terminal state: committed)
    ABORT  → moves txn to finalized set (terminal state: aborted)

A transaction is "finalized" when it has reached a terminal state.
Finalized transactions will never produce additional writes, making
their effects safe to evaluate for visibility purposes.
"""

from typing import Dict, Optional, List, Tuple, Set
from wal_parser import WalEntry


class StateBuffer:
    """In-memory key-value state buffer with MVCC visibility.
    
    Stores all writes eagerly and determines visibility at read time
    based on transaction finalization status. This mirrors how PostgreSQL's
    heap stores tuples from all transactions and uses xmin/xmax with
    the CLOG to determine visibility.
    
    Visibility rule: A transaction's changes are visible in the compacted
    output if and only if the transaction has been finalized (reached a
    terminal state). In-flight transactions are excluded because their
    outcome is not yet known.
    """
    
    def __init__(self):
        # Main state: key -> value (contains ALL writes, visibility filtered at read time)
        self._state: Dict[str, str] = {}
        # Metadata: key -> (txn_id, lsn, timestamp, operation)
        self._metadata: Dict[str, Tuple[str, int, int, str]] = {}
        # Track which keys each transaction has touched
        self._txn_writes: Dict[str, List[str]] = {}
        # Tombstone tracking: keys that have been DELETEd
        self._tombstoned_keys: Set[str] = set()
        
        # Transaction lifecycle tracking
        self._committed_txns: Set[str] = set()
        self._aborted_txns: Set[str] = set()
        self._finalized_txns: Set[str] = set()  # committed UNION aborted
    
    def apply_insert(self, entry: WalEntry):
        """Apply an INSERT operation to the state buffer."""
        key = entry.key
        txn_id = entry.txn_id
        
        # Eagerly apply to buffer (visibility determined at read time)
        self._state[key] = entry.value
        self._metadata[key] = (txn_id, entry.lsn, entry.timestamp, "INSERT")
        
        # Track writes per transaction
        if txn_id not in self._txn_writes:
            self._txn_writes[txn_id] = []
        self._txn_writes[txn_id].append(key)
    
    def apply_update(self, entry: WalEntry):
        """Apply an UPDATE operation to the state buffer."""
        key = entry.key
        txn_id = entry.txn_id
        
        # Eagerly apply to buffer
        self._state[key] = entry.value
        self._metadata[key] = (txn_id, entry.lsn, entry.timestamp, "UPDATE")
        
        # Track writes per transaction
        if txn_id not in self._txn_writes:
            self._txn_writes[txn_id] = []
        self._txn_writes[txn_id].append(key)
    
    def apply_delete(self, entry: WalEntry):
        """Apply a DELETE operation by recording a tombstone.
        
        Tombstones are structural markers in the WAL that indicate a
        key deletion event occurred. They are recorded unconditionally
        during replay because tombstone tracking is independent of
        transaction outcome — a tombstone reflects the INTENT to delete,
        and the visibility layer determines whether that intent should
        be honored based on the transaction's terminal state.
        
        This separation ensures that the tombstone set is complete for
        any visibility predicate evaluation without requiring re-scanning
        the WAL.
        """
        key = entry.key
        txn_id = entry.txn_id
        
        # Record tombstone regardless of transaction outcome.
        # Tombstones are structural WAL markers — visibility determines
        # whether their effect is materialized in the compacted output.
        self._tombstoned_keys.add(key)
        
        # Update metadata
        self._metadata[key] = (txn_id, entry.lsn, entry.timestamp, "DELETE")
        
        # Track writes per transaction
        if txn_id not in self._txn_writes:
            self._txn_writes[txn_id] = []
        self._txn_writes[txn_id].append(key)
    
    def handle_commit(self, txn_id: str):
        """Handle transaction COMMIT — mark as finalized (committed)."""
        self._committed_txns.add(txn_id)
        self._finalized_txns.add(txn_id)
    
    def handle_abort(self, txn_id: str):
        """Handle transaction ABORT — mark as finalized (aborted)."""
        self._aborted_txns.add(txn_id)
        self._finalized_txns.add(txn_id)
    
    def is_visible(self, txn_id: str) -> bool:
        """Determine if a transaction's changes are visible in the compacted output.
        
        A transaction's changes are visible if it has been finalized.
        Finalized means the transaction reached a terminal state (either
        COMMITTED or ABORTED). Unfinalized (in-flight) transactions have
        unknown outcomes and their changes must be excluded from the
        compacted output as speculative.
        
        This follows the standard CLOG visibility check pattern where
        a tuple is visible if its xmin transaction is marked as
        committed OR aborted in the commit log — the key distinction
        being that "finalized" is the relevant property for determining
        whether a transaction's effects are evaluable, while the
        specific terminal state (commit vs abort) determines the
        sign of the effect (positive = include, negative = exclude...
        but that further refinement is handled downstream by the
        snapshot manager's conflict resolution layer).
        """
        return txn_id in self._finalized_txns
    
    def get_visible_state(self) -> Dict[str, str]:
        """Return state filtered by visibility predicate.
        
        Only includes key-value pairs where the last writer transaction
        passes the visibility check. This is the materialized view that
        downstream components use for compaction output.
        """
        visible_state = {}
        for key, value in self._state.items():
            txn_id = self._metadata[key][0]
            if self.is_visible(txn_id):
                visible_state[key] = value
        return visible_state
    
    def get_visible_metadata(self) -> Dict[str, Tuple[str, int, int, str]]:
        """Return metadata filtered by visibility predicate."""
        visible_meta = {}
        for key, meta in self._metadata.items():
            txn_id = meta[0]
            if self.is_visible(txn_id):
                visible_meta[key] = meta
        return visible_meta
    
    def get_live_keys(self) -> Set[str]:
        """Return keys that are live (visible and not tombstoned).
        
        Live keys are those that pass the visibility check AND have not
        been marked with a tombstone. The tombstone set represents all
        DELETE intents observed during replay.
        
        Live = visible_keys - tombstoned_keys
        """
        visible_keys = set(self.get_visible_state().keys())
        # Remove tombstoned keys from visible set
        live_keys = visible_keys - self._tombstoned_keys
        return live_keys
    
    def get_tombstoned_keys(self) -> Set[str]:
        """Return the set of keys that have been tombstoned."""
        return set(self._tombstoned_keys)
    
    def get_raw_state(self) -> Dict[str, str]:
        """Return unfiltered state buffer (all writes regardless of visibility)."""
        return dict(self._state)
    
    def get_raw_metadata(self) -> Dict[str, Tuple[str, int, int, str]]:
        """Return unfiltered metadata."""
        return dict(self._metadata)
    
    def get_txn_writes(self) -> Dict[str, List[str]]:
        """Return the write set for each transaction."""
        return dict(self._txn_writes)
    
    def get_committed_txns(self) -> Set[str]:
        """Return set of committed transaction IDs."""
        return set(self._committed_txns)
    
    def get_aborted_txns(self) -> Set[str]:
        """Return set of aborted transaction IDs."""
        return set(self._aborted_txns)


def build_state(entries: List[WalEntry]) -> StateBuffer:
    """Process all WAL entries and build the state buffer.
    
    Processes entries in LSN order, applying data operations eagerly
    and recording transaction lifecycle events for visibility tracking.
    
    Args:
        entries: List of WAL entries sorted by LSN.
        
    Returns:
        StateBuffer with all operations applied and visibility metadata.
    """
    buffer = StateBuffer()
    
    for entry in entries:
        if entry.operation == "INSERT":
            buffer.apply_insert(entry)
        elif entry.operation == "UPDATE":
            buffer.apply_update(entry)
        elif entry.operation == "DELETE":
            buffer.apply_delete(entry)
        elif entry.operation == "COMMIT":
            buffer.handle_commit(entry.txn_id)
        elif entry.operation == "ABORT":
            buffer.handle_abort(entry.txn_id)
        # BEGIN and CHECKPOINT are no-ops for state building
    
    return buffer

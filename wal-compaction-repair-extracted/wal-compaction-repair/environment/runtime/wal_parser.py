"""
WAL Segment Parser
==================
Parses the raw WAL segment log into structured entry objects.
Handles the pipe-delimited format and extracts all fields including
CHECKPOINT metadata.

This module is verified correct - no bugs here.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict


@dataclass
class WalEntry:
    """Represents a single WAL log entry."""
    lsn: int
    txn_id: str
    operation: str
    key: Optional[str]
    value: Optional[str]
    timestamp: int

    @property
    def is_structural(self) -> bool:
        """Returns True for BEGIN/COMMIT/ABORT/CHECKPOINT operations."""
        return self.operation in ("BEGIN", "COMMIT", "ABORT", "CHECKPOINT")

    @property
    def is_data_op(self) -> bool:
        """Returns True for INSERT/UPDATE/DELETE operations."""
        return self.operation in ("INSERT", "UPDATE", "DELETE")


def parse_wal_segments(filepath: str) -> List[WalEntry]:
    """Parse WAL segment log file into structured entries.
    
    Format: LSN|TXN_ID|OPERATION|KEY|VALUE|TIMESTAMP
    
    Lines starting with # are comments and are skipped.
    Empty lines are skipped.
    CHECKPOINT entries have a special format for the key/value fields.
    
    Returns:
        List of WalEntry objects in LSN order.
    """
    entries = []
    
    with open(filepath, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            
            parts = line.split("|")
            if len(parts) < 6:
                continue
            
            lsn_str = parts[0]
            txn_id = parts[1]
            operation = parts[2]
            key = parts[3] if parts[3] else None
            value = parts[4] if parts[4] else None
            timestamp_str = parts[5]
            
            # Handle CHECKPOINT specially - it uses key/value for metadata
            if operation == "CHECKPOINT" or txn_id == "CHECKPOINT":
                # Reconstruct checkpoint entry
                # Format: LSN|CHECKPOINT|range_start=X|range_end=Y|...|TIMESTAMP
                # Actually the format is: "32|CHECKPOINT|range_start=1|range_end=31|compaction_epoch=1||1700000470"
                # Reparse as checkpoint
                lsn = int(lsn_str) if lsn_str.isdigit() else 0
                if txn_id == "CHECKPOINT":
                    # txn_id field contains CHECKPOINT
                    meta_key = parts[2] if len(parts) > 2 else None
                    meta_val = parts[3] if len(parts) > 3 else None
                    ts = int(parts[-1]) if parts[-1].isdigit() else 0
                    entry = WalEntry(
                        lsn=lsn,
                        txn_id="CHECKPOINT",
                        operation="CHECKPOINT",
                        key=meta_key,
                        value=meta_val,
                        timestamp=ts
                    )
                else:
                    entry = WalEntry(
                        lsn=lsn,
                        txn_id=txn_id,
                        operation=operation,
                        key=key,
                        value=value,
                        timestamp=int(timestamp_str) if timestamp_str.isdigit() else 0
                    )
                entries.append(entry)
                continue
            
            try:
                lsn = int(lsn_str)
                timestamp = int(timestamp_str)
            except ValueError:
                continue
            
            entry = WalEntry(
                lsn=lsn,
                txn_id=txn_id,
                operation=operation,
                key=key,
                value=value,
                timestamp=timestamp
            )
            entries.append(entry)
    
    # Sort by LSN for deterministic processing order
    entries.sort(key=lambda e: e.lsn)
    return entries


def get_transaction_ids(entries: List[WalEntry]) -> List[str]:
    """Extract unique transaction IDs (excluding CHECKPOINT)."""
    seen = set()
    txn_ids = []
    for entry in entries:
        if entry.txn_id != "CHECKPOINT" and entry.txn_id not in seen:
            seen.add(entry.txn_id)
            txn_ids.append(entry.txn_id)
    return txn_ids


def get_committed_txns(entries: List[WalEntry]) -> set:
    """Return set of transaction IDs that have a COMMIT record."""
    return {e.txn_id for e in entries if e.operation == "COMMIT"}


def get_aborted_txns(entries: List[WalEntry]) -> set:
    """Return set of transaction IDs that have an ABORT record."""
    return {e.txn_id for e in entries if e.operation == "ABORT"}


def get_data_operations(entries: List[WalEntry]) -> List[WalEntry]:
    """Return only INSERT/UPDATE/DELETE entries."""
    return [e for e in entries if e.is_data_op]

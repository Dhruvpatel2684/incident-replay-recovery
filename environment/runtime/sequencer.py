"""Monotonically increasing sequence number assignment."""

import json
import os


class Sequencer:
    """Assigns sequential numbers to processed events."""

    def __init__(self, state_path):
        self.state_path = state_path
        self.next_sequence = 1
        self._load()

    def _load(self):
        """Load sequence state from disk."""
        if os.path.exists(self.state_path):
            with open(self.state_path, 'r') as f:
                data = json.load(f)
                self.next_sequence = data.get("next_sequence", 1)

    def assign(self):
        """Get the next sequence number and increment the counter."""
        seq = self.next_sequence
        self.next_sequence += 1
        return seq

    def save(self):
        """Persist sequence state to disk."""
        with open(self.state_path, 'w') as f:
            json.dump({"next_sequence": self.next_sequence}, f, indent=2)

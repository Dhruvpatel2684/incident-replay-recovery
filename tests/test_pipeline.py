"""
Verification tests for the log pipeline reconciler.

These tests validate that the pipeline has correctly processed all events,
assigned them to proper shards, maintained sequence integrity, and produced
a valid manifest with correct checksums.
"""

import json
import os
import hashlib
import sys

import pytest

BASE_PATH = "/app/runtime"
PARTITIONS_DIR = os.path.join(BASE_PATH, "partitions")
SHARDS_DIR = os.path.join(BASE_PATH, "shards")
STATE_DIR = os.path.join(BASE_PATH, "state")
OUTPUT_DIR = os.path.join(BASE_PATH, "output")

NUM_SHARDS = 4
EXPECTED_TOTAL_EVENTS = 75


def assign_shard(event_id, num_shards):
    """Deterministic shard assignment — must match hasher.py."""
    h = 0
    for c in event_id:
        h = (h * 31 + ord(c)) & 0xFFFFFFFF
    return h % num_shards


def load_all_partition_events():
    """Load all raw events from partition files."""
    events = {}
    for fname in sorted(os.listdir(PARTITIONS_DIR)):
        if not fname.endswith('.jsonl'):
            continue
        partition_name = fname.replace('.jsonl', '')
        with open(os.path.join(PARTITIONS_DIR, fname), 'r') as f:
            for line in f:
                line = line.strip()
                if line:
                    event = json.loads(line)
                    events[event['event_id']] = {
                        **event,
                        'partition': partition_name
                    }
    return events


def load_all_shard_events():
    """Load all processed events from shard files."""
    events = []
    for i in range(NUM_SHARDS):
        shard_path = os.path.join(SHARDS_DIR, f"shard_{i}.jsonl")
        if os.path.exists(shard_path):
            with open(shard_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        events.append(json.loads(line))
    return events


def load_shard_events_by_shard():
    """Load events grouped by shard file."""
    shards = {}
    for i in range(NUM_SHARDS):
        shard_path = os.path.join(SHARDS_DIR, f"shard_{i}.jsonl")
        shards[i] = []
        if os.path.exists(shard_path):
            with open(shard_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        shards[i].append(json.loads(line))
    return shards


class TestPartitionProcessing:
    """Tests that all partitions are fully processed."""

    def test_all_partitions_processed(self):
        """All 75 events from all partitions should be in shards."""
        raw_events = load_all_partition_events()
        shard_events = load_all_shard_events()
        shard_ids = {e['event_id'] for e in shard_events}

        for event_id in raw_events:
            assert event_id in shard_ids, \
                f"Event {event_id} from partitions is missing from shards"

    def test_total_event_count(self):
        """Total events across all shards should equal 75."""
        shard_events = load_all_shard_events()
        assert len(shard_events) == EXPECTED_TOTAL_EVENTS, \
            f"Expected {EXPECTED_TOTAL_EVENTS} events, got {len(shard_events)}"

    def test_partition_0_events_present(self):
        """All 30 events from partition_0 should be in shards."""
        shard_events = load_all_shard_events()
        shard_ids = {e['event_id'] for e in shard_events}
        for i in range(1, 31):
            event_id = f"evt-{i:04d}"
            assert event_id in shard_ids, \
                f"Partition 0 event {event_id} missing from shards"

    def test_partition_1_events_present(self):
        """All 25 events from partition_1 should be in shards."""
        shard_events = load_all_shard_events()
        shard_ids = {e['event_id'] for e in shard_events}
        for i in range(31, 56):
            event_id = f"evt-{i:04d}"
            assert event_id in shard_ids, \
                f"Partition 1 event {event_id} missing from shards"

    def test_partition_2_events_present(self):
        """All 20 events from partition_2 should be in shards."""
        shard_events = load_all_shard_events()
        shard_ids = {e['event_id'] for e in shard_events}
        for i in range(56, 76):
            event_id = f"evt-{i:04d}"
            assert event_id in shard_ids, \
                f"Partition 2 event {event_id} missing from shards"


class TestShardIntegrity:
    """Tests for shard file correctness."""

    def test_shard_3_exists(self):
        """shard_3.jsonl must exist after repair."""
        shard_path = os.path.join(SHARDS_DIR, "shard_3.jsonl")
        assert os.path.exists(shard_path), "shard_3.jsonl is missing"

    def test_shard_3_has_events(self):
        """shard_3.jsonl must not be empty."""
        shard_path = os.path.join(SHARDS_DIR, "shard_3.jsonl")
        assert os.path.exists(shard_path), "shard_3.jsonl is missing"
        with open(shard_path, 'r') as f:
            events = [line.strip() for line in f if line.strip()]
        assert len(events) > 0, "shard_3.jsonl is empty"

    def test_no_duplicate_events(self):
        """No event_id should appear in multiple shards."""
        shard_events = load_all_shard_events()
        seen_ids = set()
        for event in shard_events:
            eid = event['event_id']
            assert eid not in seen_ids, \
                f"Duplicate event {eid} found in shards"
            seen_ids.add(eid)

    def test_shard_assignment_correct(self):
        """Each event should be in the correct shard based on hash."""
        shards = load_shard_events_by_shard()
        for shard_id, events in shards.items():
            for event in events:
                expected_shard = assign_shard(event['event_id'], NUM_SHARDS)
                assert expected_shard == shard_id, \
                    f"Event {event['event_id']} in shard {shard_id} " \
                    f"but hash assigns to shard {expected_shard}"

    def test_no_phantom_events(self):
        """No events in shards that aren't in raw partition files."""
        raw_events = load_all_partition_events()
        shard_events = load_all_shard_events()
        for event in shard_events:
            assert event['event_id'] in raw_events, \
                f"Phantom event {event['event_id']} found in shards"

    def test_event_format_valid(self):
        """Each shard entry must have all required fields."""
        required_fields = [
            'event_id', 'timestamp', 'source', 'level',
            'payload', 'shard_id', 'sequence', 'partition_source'
        ]
        shard_events = load_all_shard_events()
        for event in shard_events:
            for field in required_fields:
                assert field in event, \
                    f"Event {event.get('event_id', 'unknown')} missing field '{field}'"


class TestStateIntegrity:
    """Tests for state file correctness."""

    def test_checkpoints_match_reality(self):
        """Checkpoint offsets should match actual partition lengths processed."""
        checkpoints_path = os.path.join(STATE_DIR, "checkpoints.json")
        assert os.path.exists(checkpoints_path), "checkpoints.json missing"

        with open(checkpoints_path, 'r') as f:
            checkpoints = json.load(f)

        # After full processing, checkpoints should match partition lengths
        expected = {"partition_0": 30, "partition_1": 25, "partition_2": 20}
        for partition, expected_offset in expected.items():
            actual = checkpoints.get(partition, 0)
            assert actual == expected_offset, \
                f"Checkpoint for {partition}: expected {expected_offset}, got {actual}"

    def test_dedup_registry_clean(self):
        """No phantom entries in dedup registry."""
        registry_path = os.path.join(STATE_DIR, "dedup_registry.json")
        assert os.path.exists(registry_path), "dedup_registry.json missing"

        with open(registry_path, 'r') as f:
            data = json.load(f)

        raw_events = load_all_partition_events()
        for eid in data.get("seen", []):
            assert eid in raw_events, \
                f"Phantom entry '{eid}' in dedup registry"

    def test_sequence_contiguous(self):
        """Sequence numbers should be 1..N with no gaps."""
        shard_events = load_all_shard_events()
        sequences = sorted([e['sequence'] for e in shard_events])

        assert len(sequences) == EXPECTED_TOTAL_EVENTS, \
            f"Expected {EXPECTED_TOTAL_EVENTS} sequences, got {len(sequences)}"

        expected = list(range(1, EXPECTED_TOTAL_EVENTS + 1))
        assert sequences == expected, \
            f"Sequence numbers not contiguous: gaps found"

    def test_sequence_counter_correct(self):
        """next_sequence should be max_sequence + 1."""
        sequence_path = os.path.join(STATE_DIR, "sequence_state.json")
        assert os.path.exists(sequence_path), "sequence_state.json missing"

        with open(sequence_path, 'r') as f:
            state = json.load(f)

        shard_events = load_all_shard_events()
        max_seq = max(e['sequence'] for e in shard_events)
        expected_next = max_seq + 1

        assert state['next_sequence'] == expected_next, \
            f"next_sequence should be {expected_next}, got {state['next_sequence']}"


class TestManifest:
    """Tests for the output manifest."""

    def test_manifest_exists(self):
        """output/manifest.json must exist."""
        manifest_path = os.path.join(OUTPUT_DIR, "manifest.json")
        assert os.path.exists(manifest_path), "manifest.json missing"

    def test_manifest_has_all_shards(self):
        """Manifest must reference all 4 shards."""
        manifest_path = os.path.join(OUTPUT_DIR, "manifest.json")
        with open(manifest_path, 'r') as f:
            manifest = json.load(f)

        for i in range(NUM_SHARDS):
            shard_name = f"shard_{i}.jsonl"
            assert shard_name in manifest['shards'], \
                f"{shard_name} not in manifest"

    def test_manifest_checksums_valid(self):
        """Per-shard checksums in manifest must match actual file hashes."""
        manifest_path = os.path.join(OUTPUT_DIR, "manifest.json")
        with open(manifest_path, 'r') as f:
            manifest = json.load(f)

        for shard_name, info in manifest['shards'].items():
            shard_path = os.path.join(SHARDS_DIR, shard_name)
            assert os.path.exists(shard_path), \
                f"Shard file {shard_name} referenced in manifest but missing"

            with open(shard_path, 'rb') as f:
                content = f.read()
            actual_checksum = hashlib.sha256(content).hexdigest()

            assert info['checksum'] == actual_checksum, \
                f"Checksum mismatch for {shard_name}: " \
                f"manifest={info['checksum'][:16]}... " \
                f"actual={actual_checksum[:16]}..."

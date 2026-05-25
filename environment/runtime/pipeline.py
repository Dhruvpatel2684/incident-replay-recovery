"""Core pipeline logic for processing log events into shards."""

import json
import os
import hashlib
import configparser

from hasher import assign_shard
from dedup import DedupRegistry
from sequencer import Sequencer


class Pipeline:
    """Processes partitioned log events into deduplicated, sharded output."""

    def __init__(self, base_path):
        self.base_path = base_path
        self.config = configparser.ConfigParser()
        self.config.read(os.path.join(base_path, 'config', 'pipeline.ini'))

        self.num_shards = self.config.getint('pipeline', 'num_shards')
        self.partition_files = [
            p.strip() for p in self.config.get('pipeline', 'partitions').split(',')
        ]

        # State paths
        self.checkpoints_path = os.path.join(base_path, self.config.get('state', 'checkpoints_file'))
        self.dedup_path = os.path.join(base_path, self.config.get('state', 'dedup_registry_file'))
        self.sequence_path = os.path.join(base_path, self.config.get('state', 'sequence_state_file'))

        # Output paths
        self.shards_dir = os.path.join(base_path, self.config.get('output', 'shards_dir'))
        self.manifest_path = os.path.join(base_path, self.config.get('output', 'manifest_file'))
        self.pipeline_output_path = os.path.join(base_path, self.config.get('output', 'pipeline_output'))

        # Initialize components
        self.dedup = DedupRegistry(self.dedup_path)
        self.sequencer = Sequencer(self.sequence_path)
        self.checkpoints = self._load_checkpoints()

    def _load_checkpoints(self):
        """Load partition processing checkpoints."""
        if os.path.exists(self.checkpoints_path):
            with open(self.checkpoints_path, 'r') as f:
                return json.load(f)
        return {}

    def _save_checkpoints(self):
        """Save partition processing checkpoints."""
        with open(self.checkpoints_path, 'w') as f:
            json.dump(self.checkpoints, f, indent=2)

    def _read_partition(self, partition_file, offset):
        """Read events from a partition starting at the given offset."""
        path = os.path.join(self.base_path, 'partitions', partition_file)
        events = []
        with open(path, 'r') as f:
            for i, line in enumerate(f):
                if i < offset:
                    continue
                line = line.strip()
                if line:
                    events.append(json.loads(line))
        return events

    def _load_existing_shards(self):
        """Load existing shard data for appending."""
        shards = {}
        for i in range(self.num_shards):
            shard_path = os.path.join(self.shards_dir, f'shard_{i}.jsonl')
            shards[i] = []
            if os.path.exists(shard_path):
                with open(shard_path, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            shards[i].append(json.loads(line))
        return shards

    def run(self):
        """Execute the pipeline: read, dedup, shard, sequence, write."""
        # Load existing shard data
        shards = self._load_existing_shards()

        # Track all output events
        all_output = []

        # Process each partition from its checkpoint
        for partition_file in self.partition_files:
            partition_name = partition_file.replace('.jsonl', '')
            offset = self.checkpoints.get(partition_name, 0)

            events = self._read_partition(partition_file, offset)

            for event in events:
                event_id = event['event_id']

                # Deduplication check
                if self.dedup.is_duplicate(event_id):
                    continue

                # Mark as seen
                self.dedup.mark_seen(event_id)

                # Assign shard
                shard_id = assign_shard(event_id, self.num_shards)

                # Assign sequence number
                seq_num = self.sequencer.assign()

                # Build output record
                output_record = {
                    "event_id": event_id,
                    "timestamp": event['timestamp'],
                    "source": event['source'],
                    "level": event['level'],
                    "payload": event['payload'],
                    "shard_id": shard_id,
                    "sequence": seq_num,
                    "partition_source": partition_name
                }

                shards[shard_id].append(output_record)
                all_output.append(output_record)

            # Update checkpoint to the end of partition
            total_events = offset + len(events)
            self.checkpoints[partition_name] = total_events

        # Write shard files
        os.makedirs(self.shards_dir, exist_ok=True)
        for i in range(self.num_shards):
            shard_path = os.path.join(self.shards_dir, f'shard_{i}.jsonl')
            with open(shard_path, 'w') as f:
                for record in shards[i]:
                    f.write(json.dumps(record) + '\n')

        # Write pipeline output
        os.makedirs(os.path.dirname(self.pipeline_output_path), exist_ok=True)
        with open(self.pipeline_output_path, 'w') as f:
            for record in sorted(all_output, key=lambda x: x['sequence']):
                f.write(json.dumps(record) + '\n')

        # Write manifest with checksums
        self._write_manifest()

        # Save state
        self._save_checkpoints()
        self.dedup.save()
        self.sequencer.save()

    def _write_manifest(self):
        """Write the integrity manifest with per-shard SHA-256 checksums."""
        manifest = {
            "num_shards": self.num_shards,
            "shards": {}
        }
        total_events = 0
        for i in range(self.num_shards):
            shard_path = os.path.join(self.shards_dir, f'shard_{i}.jsonl')
            if os.path.exists(shard_path):
                with open(shard_path, 'rb') as f:
                    content = f.read()
                checksum = hashlib.sha256(content).hexdigest()
                event_count = len([l for l in content.decode().strip().split('\n') if l.strip()])
            else:
                checksum = hashlib.sha256(b'').hexdigest()
                event_count = 0

            manifest["shards"][f"shard_{i}.jsonl"] = {
                "checksum": checksum,
                "event_count": event_count
            }
            total_events += event_count

        manifest["total_events"] = total_events

        os.makedirs(os.path.dirname(self.manifest_path), exist_ok=True)
        with open(self.manifest_path, 'w') as f:
            json.dump(manifest, f, indent=2)

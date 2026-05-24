# Configuration Drift Reconciler — Incident Report

## Situation

The configuration drift reconciler is a runtime system that compares declared infrastructure manifests against live node state to detect configuration drift across a fleet of production nodes. It generates drift reports, remediation plans, and compliance summaries.

The system is producing incorrect output. Drift detection reports contain false positives, miss granular field-level changes, and the compliance scoring is unreliable.

The runtime environment already contains the required system-wide Python tooling and pytest installation.

## Observed Symptoms

1. **False positive drift on numeric fields**: Nodes show drift for `listen_port`, `max_connections`, `timeout_seconds`, and `workers` even when the values are semantically identical (e.g., manifest declares `"8080"` as a string, live state reports `8080` as an integer). The type coercion logic configured in `reconciler.ini` does not appear to activate.

2. **False positive drift on unordered list fields**: Fields like `dns_servers`, `tags`, and `ntp_servers` are flagged as drifted when their elements are the same but in a different order. The configuration specifies these as order-insensitive, but the comparison treats them as ordered.

3. **Coarse-grained nested drift**: When a nested configuration object (like `tls`, `replication`, or `persistence`) has a single differing sub-field, the entire parent key is reported as drifted rather than identifying the specific sub-key. For example, if only `tls.cert_path` differs, the report shows `tls` as the drifted field with the full dict as expected/actual values.

4. **Decommissioned nodes in compliance reports**: The node `legacy-app-01` has status `decommissioned` and the configuration specifies `include_decommissioned = false`, but it still appears in compliance scoring.

5. **Truncated compliance percentages**: Compliance scores appear as whole numbers (e.g., 91%) rather than precise values (e.g., 91.67%). Nodes with small drift counts relative to total fields show lower-than-expected compliance.

## Architecture

The reconciler runs as a single-pass process:

1. Load manifest declarations from `/app/runtime/manifests/`
2. Load live node state from `/app/runtime/live_state/`
3. Compare each node's declared config against live state
4. Generate remediation plans for detected drift
5. Compute compliance scores per node and overall
6. Export drift report and compliance summary to `/app/runtime/output/`

## Key Files

| File | Purpose |
|------|---------|
| `/app/runtime/run_reconciler.py` | Orchestration entrypoint |
| `/app/runtime/comparator.py` | Drift detection — compares manifest vs live config |
| `/app/runtime/compliance.py` | Compliance scoring — computes per-node and overall percentages |
| `/app/runtime/remediation.py` | Remediation plan generation |
| `/app/runtime/exporter.py` | Output writer — drift report JSONL and compliance JSON |
| `/app/runtime/loader.py` | Loads manifest and live state JSON files |
| `/app/runtime/config/reconciler.ini` | Runtime configuration (coercion fields, order-insensitive fields, thresholds) |
| `/app/runtime/manifests/cluster_nodes.json` | Declared desired state for all nodes |
| `/app/runtime/live_state/node_states.json` | Current live configuration for all nodes |
| `/app/runtime/output/drift_report.jsonl` | Output: per-node drift report |
| `/app/runtime/output/compliance_summary.json` | Output: fleet compliance summary |

## Configuration Reference (reconciler.ini)

```ini
[drift]
comparison_mode = strict
ignore_order_fields = dns_servers,tags,ntp_servers
type_coerce_fields = port,listen_port,max_connections,timeout_seconds,workers

[compliance]
include_decommissioned = false
score_precision = 2

[output]
output_path = /app/runtime/output
snapshot_filename = drift_report.jsonl
compliance_filename = compliance_summary.json
```

The `type_coerce_fields` setting lists field names where string-to-integer type differences should be treated as equivalent. The `ignore_order_fields` setting lists field names where list element ordering should not affect comparison.

## Output Schema

### drift_report.jsonl

Each line is a JSON object representing one node:

```json
{
  "node_id": "string — unique node identifier",
  "status": "string — active | decommissioned",
  "region": "string — deployment region",
  "drift_count": "integer — number of drifted fields",
  "drifts": [
    {
      "field": "string — dotted path to drifted field (e.g., 'tls.cert_path')",
      "type": "string — value_mismatch | missing_field | unexpected_field",
      "expected": "any — value from manifest",
      "actual": "any — value from live state"
    }
  ],
  "remediation": [
    {
      "node_id": "string",
      "field": "string — field path",
      "action": "string — update_value | add_field | remove_field",
      "target_value": "any — desired value",
      "current_value": "any — current live value"
    }
  ]
}
```

Field paths should use dotted notation relative to the config root (e.g., `tls.cert_path`, `replication.max_wal_senders`). They should NOT include artificial prefixes.

### compliance_summary.json

```json
{
  "generated_at": "string — ISO-8601 UTC timestamp",
  "report_sha256": "string — SHA-256 hex digest of drift_report.jsonl content",
  "record_count": "integer — number of lines in drift_report.jsonl",
  "nodes_with_drift": "integer — nodes with drift_count > 0",
  "total_drift_entries": "integer — sum of all drift_count values",
  "total_remediation_actions": "integer — sum of all remediation action counts",
  "compliance": {
    "node_scores": [
      {
        "node_id": "string",
        "status": "string",
        "region": "string",
        "total_fields": "integer",
        "drifted_fields": "integer",
        "compliant_fields": "integer",
        "compliance_pct": "float — percentage with up to 2 decimal places"
      }
    ],
    "overall_compliance_pct": "float — fleet-wide percentage",
    "total_nodes": "integer — number of nodes in compliance (excludes decommissioned)",
    "fully_compliant_nodes": "integer — nodes with zero drift"
  }
}
```

## Expected Behavior After Repair

- Type coercion activates for configured fields: `"8080"` (string) equals `8080` (int)
- Order-insensitive comparison activates for configured fields: `["a","b"]` equals `["b","a"]`
- Nested config diffs report specific sub-keys (e.g., `tls.cert_path`) not parent objects
- Field paths use bare config-relative notation without artificial prefixes
- Decommissioned nodes are excluded from compliance scoring
- Compliance percentages use proper float division with up to 2 decimal places
- The compliance `total_nodes` count reflects only active (non-decommissioned) nodes

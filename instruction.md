# Configuration Drift Reconciler — Repair Task

## Overview

You are maintaining a **Configuration Drift Reconciler** system that compares declared infrastructure manifests against live node state to detect configuration drift, generate remediation plans, compute compliance scores, and export integrity-verified reports.

The reconciler is deployed at `/app/runtime/` and consists of:

The runtime environment contains the required system-wide Python tooling and pytest installation.

- `/app/runtime/run_reconciler.py` — orchestration entrypoint
- `/app/runtime/loader.py` — loads manifest declarations and live state from JSON
- `/app/runtime/comparator.py` — recursive comparison engine with type coercion and order-insensitive handling
- `/app/runtime/compliance.py` — per-node and fleet-wide compliance scoring
- `/app/runtime/remediation.py` — generates remediation action plans for drifted nodes
- `/app/runtime/exporter.py` — writes JSONL drift report and JSON compliance summary with integrity hash
- `/app/runtime/config/reconciler.ini` — comparison settings (coerce fields, ignore-order fields, output paths)
- `/app/runtime/manifests/cluster_nodes.json` — declared infrastructure state
- `/app/runtime/live_state/node_states.json` — current observed state from agents

## Observed Symptoms

Operations teams have reported several issues with the reconciler output:

1. **Spurious drift on nested configuration fields** — Certain nodes report drift for numeric fields inside nested configuration blocks (like `replication` or `concurrency` settings) even when the declared and live values are semantically equivalent. However, top-level numeric fields appear to be coerced correctly. The issue seems specific to fields that are children of nested objects.

2. **Inconsistent list comparison** — One or more nodes show unexpected drift for list fields (like `dns_servers`) that should be order-insensitive. The elements appear equivalent but the comparison fails for unclear reasons.

3. **Unexpected remediation gaps** — At least one node with known configuration drift is not receiving a remediation plan despite being in an active declared state. The remediation planner filters based on node status, and something about how status flows through the pipeline appears incorrect.

4. **Compliance score precision issue** — Per-node compliance percentages look reasonable, but the fleet-wide overall compliance number appears to be consistently lower than expected and lacks decimal precision. Teams suspect a rounding issue in the aggregation logic.

5. **Drift totals include retired nodes** — The `total_drift_entries` and `nodes_with_drift` counters in the compliance summary appear to include drift from decommissioned nodes that should be excluded from operational metrics. Active-only dashboards report higher drift counts than expected because retired infrastructure is still being counted.

## Your Task

Diagnose and repair the defects in the runtime code. The fix should be implemented in `/solution/repair_reconciler.py` which will be executed to patch the runtime in-place.

**Constraints:**
- Only modify Python files under `/app/runtime/`
- Do not modify the manifest data or live state files
- Do not modify `reconciler.ini`
- The reconciler must produce correct output after repair

## Output Schema

### `/app/runtime/output/drift_report.jsonl`

Each line is a JSON object:

```json
{
  "node_id": "string — unique node identifier",
  "status": "string — active | decommissioned | maintenance",
  "region": "string — deployment region",
  "drift_count": "integer — number of drifted fields detected",
  "drifts": [
    {
      "field": "string — dotted path e.g. config.tls.cert_path",
      "type": "string — value_mismatch | missing_field | unexpected_field",
      "expected": "any — value from manifest declaration",
      "actual": "any — value from live node state"
    }
  ],
  "remediation": [
    {
      "node_id": "string",
      "field": "string — dotted field path",
      "action": "string — update_value | add_field | remove_field",
      "target_value": "any — desired manifest value",
      "current_value": "any — current live value"
    }
  ]
}
```

### `/app/runtime/output/compliance_summary.json`

```json
{
  "generated_at": "string — ISO-8601 UTC timestamp",
  "report_sha256": "string — SHA-256 hex digest of drift_report.jsonl content",
  "record_count": "integer — number of records in drift report",
  "nodes_with_drift": "integer — count of nodes with drift_count > 0",
  "total_drift_entries": "integer — sum of all drift_count values",
  "total_remediation_actions": "integer — total remediation actions across all nodes",
  "compliance": {
    "node_scores": [
      {
        "node_id": "string",
        "status": "string",
        "region": "string",
        "total_fields": "integer — estimated total config fields",
        "drifted_fields": "integer",
        "compliant_fields": "integer",
        "compliance_pct": "float — percentage (0-100) with up to 2 decimal places"
      }
    ],
    "overall_compliance_pct": "float — fleet-wide compliance percentage",
    "total_nodes": "integer — nodes included in scoring (excludes decommissioned)",
    "fully_compliant_nodes": "integer — nodes with zero drift"
  }
}
```

## Expected Behavior After Repair

- Nested numeric fields configured for type coercion should be compared as strings regardless of nesting depth
- Order-insensitive lists should be compared element-by-element with tolerance for trivial whitespace differences
- Node status in drift results should reflect the **declared** manifest state, not the observed live state
- Fleet-wide compliance percentage should use floating-point division with proper precision
- The integrity hash in the compliance summary should match the actual content written to the report file
- Drift totals (`total_drift_entries`, `nodes_with_drift`) should only count active nodes, excluding decommissioned infrastructure

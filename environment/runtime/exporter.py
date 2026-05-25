"""
Exports DNS resolution results and metadata summary.
"""

import hashlib
import json
import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger("dns.exporter")


def export_results(results, zone_metadata, config):
    """Write resolution results and summary to output directory."""
    output_path = "/app/runtime/output"
    os.makedirs(output_path, exist_ok=True)

    # Write results as JSONL
    results_path = os.path.join(output_path, "resolution_results.jsonl")
    with open(results_path, "w") as f:
        for result in results:
            f.write(json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n")

    # Compute integrity hash
    with open(results_path) as f:
        content = f.read()
    lines = [l for l in content.split("\n") if l.strip()]
    content_hash = hashlib.sha256("\n".join(lines).encode()).hexdigest()

    # Write summary
    summary = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        "results_sha256": content_hash,
        "total_queries": len(results),
        "resolved_count": sum(1 for r in results if r["status"] == "NOERROR"),
        "nxdomain_count": sum(1 for r in results if r["status"] == "NXDOMAIN"),
        "servfail_count": sum(1 for r in results if r["status"] == "SERVFAIL"),
        "zones_loaded": zone_metadata,
    }

    summary_path = os.path.join(output_path, "resolution_summary.json")
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2, sort_keys=True)

    logger.info(f"results: {results_path} ({len(results)} queries)")
    logger.info(f"summary: {summary_path}")
    logger.info(f"integrity: {content_hash}")

    return results_path, summary_path

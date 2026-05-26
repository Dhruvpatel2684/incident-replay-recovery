"""
Main entry point for the rate limiting system.

Orchestrates request processing through classification,
enforcement, and statistics collection:
1. Load request streams from data feeds
2. Classify each request into a rate limiting tier
3. Apply rate limit enforcement for applicable tiers
4. Collect and compute statistics
5. Write results to output files
"""
import json
import os

from runtime.classifier import RequestClassifier
from runtime.enforcer import RateLimitEnforcer
from runtime.stats import StatsTracker


CONFIG_PATH = "/app/runtime/config.ini"
DATA_DIR = "/app/runtime/data"
OUTPUT_DIR = "/app/runtime/output"


def process_stream(stream_path, classifier, enforcer, stats, stream_id):
    """Process all requests in a single traffic stream."""
    with open(stream_path, "r") as f:
        requests = json.load(f)

    decisions = []
    for req in requests:
        tier = classifier.classify(req["path"])
        rate_limited = classifier.is_rate_limited(tier)

        if rate_limited:
            allowed, reason = enforcer.check_request(req["timestamp_ms"])
        else:
            allowed = True
            reason = "exempt"

        stats.record_decision(
            req["req_id"], stream_id, tier, allowed, req["timestamp_ms"]
        )
        decisions.append({
            "req_id": req["req_id"],
            "path": req["path"],
            "tier": tier,
            "allowed": allowed,
            "reason": reason,
            "timestamp_ms": req["timestamp_ms"],
        })

    return decisions


def main():
    """Run the rate limiting system on all traffic streams."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    classifier = RequestClassifier(CONFIG_PATH)
    enforcer = RateLimitEnforcer(CONFIG_PATH)
    stats = StatsTracker()

    stream_files = sorted(f for f in os.listdir(DATA_DIR) if f.endswith(".json"))
    all_decisions = []

    for fname in stream_files:
        fpath = os.path.join(DATA_DIR, fname)
        stream_id = fname.replace("traffic_stream_", "").replace(".json", "")
        decisions = process_stream(fpath, classifier, enforcer, stats, stream_id)
        all_decisions.extend(decisions)

    summary = stats.get_summary()

    with open(os.path.join(OUTPUT_DIR, "decisions.json"), "w") as f:
        json.dump(all_decisions, f, indent=2)

    with open(os.path.join(OUTPUT_DIR, "limiter_summary.json"), "w") as f:
        json.dump(summary, f, indent=2)


if __name__ == "__main__":
    main()

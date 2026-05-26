"""
Test suite for rate limiting system.

Validates behavioral correctness of the rate limiter by checking
decision outcomes and statistical invariants against expected
operational characteristics.
"""
import json
import os

OUTPUT_DIR = "/app/runtime/output"
DECISIONS_PATH = os.path.join(OUTPUT_DIR, "decisions.json")
SUMMARY_PATH = os.path.join(OUTPUT_DIR, "limiter_summary.json")


def load_decisions():
    """Load all rate limiting decisions."""
    with open(DECISIONS_PATH, "r") as f:
        return json.load(f)


def load_summary():
    """Load rate limiter summary."""
    with open(SUMMARY_PATH, "r") as f:
        return json.load(f)


# === BASIC TESTS (always pass) ===


def test_output_files_exist():
    """Verify output files are generated."""
    assert os.path.isfile(DECISIONS_PATH), f"Missing: {DECISIONS_PATH}"
    assert os.path.isfile(SUMMARY_PATH), f"Missing: {SUMMARY_PATH}"


def test_decision_schema():
    """Verify each decision has required fields."""
    decisions = load_decisions()
    assert len(decisions) == 75, f"Expected 75 decisions, got {len(decisions)}"
    for d in decisions:
        assert "req_id" in d
        assert "tier" in d
        assert "allowed" in d
        assert "reason" in d
        assert "timestamp_ms" in d


def test_summary_schema():
    """Verify summary has required fields."""
    summary = load_summary()
    assert "total_requests" in summary
    assert "total_allowed" in summary
    assert "total_denied" in summary
    assert "allow_rate" in summary
    assert "per_tier" in summary
    assert "per_stream" in summary


def test_all_requests_have_decision():
    """Verify every request gets an allow or deny decision."""
    summary = load_summary()
    assert summary["total_requests"] == 75
    assert summary["total_allowed"] + summary["total_denied"] == 75


# === MEDIUM TESTS ===


def test_exempt_tiers_classified():
    """Verify health, static, and websocket requests are correctly classified.

    These requests have specific URL patterns that should be recognized
    by the classifier and placed in their respective exempt tiers.
    The system must distinguish between exempt and rate-limited traffic.
    """
    decisions = load_decisions()
    tiers_seen = set(d["tier"] for d in decisions)
    assert "health" in tiers_seen, (
        "Health tier not found in decisions. Health check requests "
        "(/health/*) should be classified into the 'health' tier."
    )
    assert "static" in tiers_seen, (
        "Static tier not found. Static asset requests (/static/*) "
        "should be classified into the 'static' tier."
    )


def test_exempt_requests_always_allowed():
    """Verify exempt tier requests are never denied.

    Health, static, and websocket requests must always be allowed
    regardless of rate limiter state.
    """
    decisions = load_decisions()
    exempt_tiers = {"health", "static", "websocket"}
    for d in decisions:
        if d["tier"] in exempt_tiers:
            assert d["allowed"] is True, (
                f"Request {d['req_id']} in exempt tier '{d['tier']}' was denied. "
                "Exempt tiers must never be rate-limited."
            )


def test_strict_enforcement_denies_more():
    """Verify strict enforcement produces significant denials for API traffic.

    In strict mode, a request must pass BOTH the token bucket and
    sliding window. This should result in more denials than if
    either limiter alone made the decision.
    """
    summary = load_summary()
    api_stats = summary["per_tier"].get("api", {})
    api_denied = api_stats.get("denied", 0)
    api_total = api_stats.get("allowed", 0) + api_denied
    assert api_denied >= 30, (
        f"Expected at least 30 API denials in strict mode, got {api_denied}. "
        "In strict enforcement both bucket AND window must allow the request."
    )
    denial_ratio = api_denied / api_total if api_total > 0 else 0
    assert denial_ratio >= 0.4, (
        f"API denial ratio {denial_ratio:.2f} too low for strict enforcement. "
        "Expected at least 40% of API requests to be denied."
    )


# === HARD TESTS (require multiple fixes) ===


def test_stream_a_fully_allowed():
    """Verify stream A (25 requests, 50ms spacing) passes completely.

    Stream A has 25 API requests spaced 50ms apart (total 1200ms).
    With bucket capacity=20 and refill_rate=5/1000ms, the bucket
    starts full and refills during processing. All 25 requests
    should be allowed under correct operation.
    """
    summary = load_summary()
    stream_a = summary["per_stream"].get("a", {})
    assert stream_a.get("allowed", 0) == 25, (
        f"Expected stream A to have all 25 requests allowed, "
        f"got {stream_a.get('allowed', 0)}. Stream A's request rate "
        "should be within both bucket and window limits."
    )
    assert stream_a.get("denied", 0) == 0, (
        f"Expected 0 denials in stream A, got {stream_a.get('denied', 0)}"
    )


def test_effective_rate_calculation():
    """Verify effective rate uses correct time unit conversion.

    Rate = allowed_count / (time_span_ms / 1000)
    Stream A: 25 allowed over 1200ms = 25 / 1.2 = 20.8333 req/sec
    The rate must be in requests per second (not per 100ms or other unit).
    """
    summary = load_summary()
    stream_a_rate = summary["per_stream"].get("a", {}).get("effective_rate", 0)
    assert 19.0 <= stream_a_rate <= 22.0, (
        f"Stream A effective rate {stream_a_rate} outside expected range "
        "[19, 22] req/sec. Rate should be allowed_count / seconds. "
        "Check time unit conversion in rate computation."
    )


def test_token_bucket_refill_accuracy():
    """Verify token bucket refills correctly without over-counting intervals.

    With capacity=20, refill_rate=5, interval=1000ms:
    Starting from 0 tokens at t=1000ms, exactly 5 tokens should be added.
    The bucket must not add extra tokens due to interval counting errors.
    Stream B starts processing at its own clock (after bucket may be
    partially depleted by stream A). With strict enforcement, the
    bucket state directly affects how many stream B requests pass.
    """
    summary = load_summary()
    stream_b = summary["per_stream"].get("b", {})
    # With correct strict enforcement AND correct bucket refill,
    # stream B should have significantly fewer allowed than its total
    stream_b_allowed = stream_b.get("allowed", 0)
    stream_b_total = stream_b_allowed + stream_b.get("denied", 0)
    assert stream_b_allowed < stream_b_total, (
        "Stream B should have some denials under strict rate limiting"
    )
    # But not zero (bucket refills some during processing)
    assert stream_b_allowed >= 2, (
        f"Stream B should have at least 2 allowed requests, got {stream_b_allowed}"
    )


def test_overall_system_behavior():
    """Verify complete system produces expected operational characteristics.

    Correct operation requires:
    - Proper tier classification (exempt tiers visible)
    - Strict enforcement (high denial rate for API traffic)
    - Correct rate statistics (proper time unit)
    - All exempt traffic allowed
    """
    summary = load_summary()
    decisions = load_decisions()

    # Must have exempt tiers properly classified
    tiers = set(d["tier"] for d in decisions)
    assert "health" in tiers and "static" in tiers, (
        "Exempt tiers must be properly classified"
    )

    # Strict enforcement means relatively low allow rate
    assert summary["allow_rate"] < 0.55, (
        f"Allow rate {summary['allow_rate']} too high for strict enforcement. "
        "Expected < 55% overall allow rate."
    )

    # Effective rates should be in reasonable req/sec range
    for sid, stream in summary["per_stream"].items():
        rate = stream.get("effective_rate", 0)
        if stream["allowed"] > 0:
            assert rate >= 0.5, (
                f"Stream {sid} rate {rate} impossibly low for allowed traffic"
            )

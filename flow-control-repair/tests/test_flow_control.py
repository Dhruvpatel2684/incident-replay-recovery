"""
Test suite for flow control simulation system.

Validates protocol behavior across baseline, loss recovery,
and window pressure scenarios.
"""
import json
import os

OUTPUT_DIR = "/app/runtime/output"
RESULTS_PATH = os.path.join(OUTPUT_DIR, "scenario_results.json")
SUMMARY_PATH = os.path.join(OUTPUT_DIR, "flow_summary.json")


def load_results():
    with open(RESULTS_PATH) as f:
        return json.load(f)


def load_summary():
    with open(SUMMARY_PATH) as f:
        return json.load(f)


def get_scenario(results, scenario_id):
    return next(r for r in results if r["scenario_id"] == scenario_id)


# === BASIC TESTS ===

def test_output_files_exist():
    """Verify output files are created."""
    assert os.path.isfile(RESULTS_PATH)
    assert os.path.isfile(SUMMARY_PATH)


def test_all_scenarios_run():
    """Verify all 3 scenarios executed."""
    summary = load_summary()
    assert summary["scenarios_run"] == 3


def test_results_structure():
    """Verify each scenario result has required fields."""
    results = load_results()
    for r in results:
        assert "scenario_id" in r
        assert "segments_sent" in r
        assert "segments_blocked" in r
        assert "retransmissions" in r
        assert "sender_stats" in r
        assert "receiver_stats" in r


# === MEDIUM TESTS ===

def test_baseline_window_bounded():
    """The effective window must constrain transmission.

    In baseline scenario, even with growing cwnd, the effective
    window cannot exceed the receiver's capacity. Some sends
    must be blocked when in-flight reaches the constraint.
    """
    results = load_results()
    baseline = get_scenario(results, "baseline_transfer")
    assert baseline["segments_blocked"] > 0, (
        "Baseline must have blocked segments - the effective window "
        "should limit sends when receiver buffer fills."
    )
    assert baseline["sender_stats"]["cwnd"] <= 64, (
        f"cwnd={baseline['sender_stats']['cwnd']} should not exceed "
        "ssthresh (64) in this scenario timeframe."
    )


def test_receiver_window_non_negative():
    """Receiver advertised window must never go negative.

    The receiver must compute its available buffer correctly
    so the sender never sees a negative window value.
    """
    results = load_results()
    for r in results:
        recv_win = r["sender_stats"]["recv_window"]
        assert recv_win >= 0, (
            f"Scenario {r['scenario_id']}: recv_window={recv_win} is negative. "
            "Receiver must report window AFTER updating buffer state."
        )


def test_loss_retransmissions_bounded():
    """Loss recovery must not produce excessive retransmissions.

    With 2 lost segments, the system should trigger at most 3
    retransmission events (initial retransmit per loss + timeout).
    Repeated retransmissions indicate the fast retransmit trigger
    is not being properly consumed after firing.
    """
    results = load_results()
    loss = get_scenario(results, "loss_and_recovery")
    assert loss["retransmissions"] <= 4, (
        f"Expected at most 4 retransmissions for 2 losses, got "
        f"{loss['retransmissions']}. Fast retransmit may be re-triggering."
    )


# === HARD TESTS ===

def test_efficiency_in_expected_range():
    """Overall throughput efficiency must reflect proper flow control.

    With correct windowing, the system should achieve moderate
    efficiency - not too high (over-sending) nor too low.
    """
    summary = load_summary()
    assert 0.70 <= summary["efficiency"] <= 0.80, (
        f"Efficiency {summary['efficiency']} outside expected range [0.70, 0.80]. "
        "This indicates the effective window calculation or receiver "
        "feedback is not properly constraining the sender."
    )


def test_baseline_exact_metrics():
    """Verify baseline scenario produces exact expected metrics.

    With correct flow control (min of cwnd and recv_window),
    correct receiver window feedback, and proper window growth,
    the baseline should produce specific throughput numbers.
    """
    results = load_results()
    baseline = get_scenario(results, "baseline_transfer")
    assert baseline["segments_sent"] == 84, (
        f"Baseline sent={baseline['segments_sent']}, expected 84"
    )
    assert baseline["segments_blocked"] == 8, (
        f"Baseline blocked={baseline['segments_blocked']}, expected 8"
    )


def test_window_pressure_buffer_limit():
    """Verify window pressure scenario respects buffer capacity.

    The receiver buffer is 32. Buffer used must never exceed capacity.
    With correct advertised window feedback, the sender should
    self-throttle before overflow.
    """
    results = load_results()
    wp = get_scenario(results, "window_pressure")
    buf_used = wp["receiver_stats"]["buffer_used"]
    capacity = wp["receiver_stats"]["buffer_capacity"]
    assert buf_used <= capacity, (
        f"Buffer overflow: used={buf_used} exceeds capacity={capacity}. "
        "Receiver must advertise window AFTER consuming buffer space."
    )


def test_aggregate_totals_correct():
    """Verify aggregate statistics across all scenarios."""
    summary = load_summary()
    assert summary["total_segments_sent"] == 158, (
        f"Total sent={summary['total_segments_sent']}, expected 158"
    )
    assert summary["total_retransmissions"] <= 4, (
        f"Total retransmissions={summary['total_retransmissions']}, expected <= 4"
    )

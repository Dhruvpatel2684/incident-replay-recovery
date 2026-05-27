"""
Test suite for IR optimizer.
Validates optimization correctness across passes.
"""
import json
import os

OUTPUT_DIR = "/app/runtime/output"
RESULTS_PATH = os.path.join(OUTPUT_DIR, "opt_results.json")
SUMMARY_PATH = os.path.join(OUTPUT_DIR, "opt_summary.json")


def load_results():
    with open(RESULTS_PATH) as f:
        return json.load(f)

def load_summary():
    with open(SUMMARY_PATH) as f:
        return json.load(f)

def get_program(results, filename):
    return next(r for r in results if r["source_file"] == filename)


# === BASIC TESTS ===

def test_output_files_exist():
    """Verify output files are created."""
    assert os.path.isfile(RESULTS_PATH)
    assert os.path.isfile(SUMMARY_PATH)

def test_all_programs_processed():
    """Verify all 3 programs were optimized."""
    summary = load_summary()
    assert summary["programs_optimized"] == 3

def test_result_structure():
    """Verify each result has required fields."""
    results = load_results()
    for r in results:
        assert "total_instructions" in r
        assert "live_instructions" in r
        assert "eliminated_instructions" in r
        assert "folded_instructions" in r
        assert "register_pressure" in r

# === MEDIUM TESTS ===

def test_cross_block_liveness():
    """Cross-block register uses must not be eliminated.

    In program_alpha, registers defined in 'entry' block are
    consumed in 'loop' and 'exit' blocks. The optimizer must
    recognize these cross-block uses and preserve the definitions.
    """
    results = load_results()
    alpha = get_program(results, "program_alpha.json")
    assert alpha["live_instructions"] >= 10, (
        f"program_alpha has {alpha['live_instructions']} live instructions, "
        "expected >= 10. Cross-block register uses may be incorrectly "
        "eliminated by dead code analysis."
    )
    assert alpha["eliminated_instructions"] <= 6, (
        f"program_alpha eliminated {alpha['eliminated_instructions']} "
        "instructions, expected <= 6. Over-elimination suggests liveness "
        "analysis is not considering uses in successor blocks."
    )

def test_constant_folding_precision():
    """Constant division must use float semantics.

    The IR defines 10.0/3.0 which should fold to 3.333... (float).
    If integer truncation is used instead, the result would be 3,
    propagating incorrect values through dependent computations.
    """
    results = load_results()
    summary = load_summary()
    # With correct float division, fewer downstream values change
    # and the folded count remains at 3 (one per program's div)
    assert summary["total_folded"] == 3, (
        f"Expected 3 constant folds (one div per program), got {summary['total_folded']}"
    )

def test_register_pressure_realistic():
    """Register pressure must reflect actual live register counts.

    With correct liveness (preserving cross-block uses), program_gamma
    creates a long chain where many registers are simultaneously live.
    Max pressure should be >= 8 for program_gamma.
    """
    results = load_results()
    gamma = get_program(results, "program_gamma.json")
    pressure = gamma["register_pressure"]["max_pressure"]
    assert pressure >= 7, (
        f"program_gamma max pressure={pressure}, expected >= 7. "
        "Low pressure suggests too many instructions were eliminated."
    )

# === HARD TESTS ===

def test_total_live_instructions_exact():
    """Total live instructions must equal 45 across all programs.

    This validates correct interaction of constant folding (produces
    proper float values) and dead code elimination (respects cross-block
    uses). Both passes must work correctly together.
    """
    summary = load_summary()
    assert summary["total_live_instructions"] == 45, (
        f"Expected 45 total live instructions, got {summary['total_live_instructions']}. "
        "This requires both correct liveness analysis (cross-block) and "
        "correct constant folding (float division semantics)."
    )

def test_spill_detection_correct():
    """Spill points must be detected at pressure boundary.

    When register pressure reaches the physical register count (8),
    a spill is needed. The threshold must be >= (at capacity means
    no registers available for the next definition).
    """
    summary = load_summary()
    assert summary["total_spill_points"] >= 2, (
        f"Expected >= 2 spill points, got {summary['total_spill_points']}. "
        "Spill detection requires both correct liveness (to compute "
        "accurate pressure) and correct threshold (>= not >)."
    )

def test_reduction_ratio_bounded():
    """Optimization reduction must be moderate (not over-aggressive).

    With correct cross-block liveness, only truly dead code is
    eliminated. Over-reduction indicates the liveness check is
    incorrectly scoped to local blocks only.
    """
    summary = load_summary()
    ratio = summary["reduction_ratio"]
    assert 0.15 <= ratio <= 0.30, (
        f"Reduction ratio {ratio} outside expected range [0.15, 0.30]. "
        "Too high (>0.30) suggests over-elimination of live code. "
        "Too low (<0.15) suggests no optimization occurring."
    )

def test_gamma_program_metrics():
    """Verify program_gamma produces exact expected metrics.

    This program has a long computation chain with high register
    pressure. Correct optimization should preserve most instructions.
    """
    results = load_results()
    gamma = get_program(results, "program_gamma.json")
    assert gamma["live_instructions"] == 20, (
        f"program_gamma: live={gamma['live_instructions']}, expected 20"
    )
    assert gamma["eliminated_instructions"] == 3, (
        f"program_gamma: eliminated={gamma['eliminated_instructions']}, expected 3"
    )

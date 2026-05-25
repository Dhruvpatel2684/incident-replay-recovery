"""
test_mixer.py - Validation tests for the multi-channel audio mixer pipeline.

Tests verify that the mixer produces correct output for the configured
mix session. Expected values are computed from the correct algorithm
implementation.
"""

import json
import os
import math
import pytest


# Path to output files (Docker container path)
RUNTIME_DIR = "/app/runtime"
OUTPUT_FILE = os.path.join(RUNTIME_DIR, "mix_output.json")
STATS_FILE = os.path.join(RUNTIME_DIR, "mix_stats.json")


@pytest.fixture(scope="session")
def mix_output():
    """Load mix_output.json."""
    with open(OUTPUT_FILE, 'r') as f:
        return json.load(f)


@pytest.fixture(scope="session")
def mix_stats():
    """Load mix_stats.json."""
    with open(STATS_FILE, 'r') as f:
        return json.load(f)


def test_output_files_exist():
    """Both output files must exist after pipeline execution."""
    assert os.path.exists(OUTPUT_FILE), \
        f"mix_output.json not found at {OUTPUT_FILE}"
    assert os.path.exists(STATS_FILE), \
        f"mix_stats.json not found at {STATS_FILE}"


def test_correct_sample_count(mix_output):
    """Output must contain exactly 200 samples as defined in session config."""
    assert mix_output['total_samples'] == 200


def test_channel_count(mix_stats):
    """Six channels should be mixed in the output."""
    assert mix_stats['channels_mixed'] == 6


def test_stereo_output_length(mix_output):
    """Left and right output channels must have identical length."""
    left = mix_output['stereo_samples']['left']
    right = mix_output['stereo_samples']['right']
    assert len(left) == len(right) == 200


def test_peak_within_bounds(mix_output):
    """
    No output sample should exceed the 16-bit signed range [-32768, 32767].
    Correct clipping ensures all samples remain within bounds.
    """
    left = mix_output['stereo_samples']['left']
    right = mix_output['stereo_samples']['right']
    
    for i, sample in enumerate(left):
        assert -32768 <= sample <= 32767, \
            f"Left sample {i} out of bounds: {sample}"
    
    for i, sample in enumerate(right):
        assert -32768 <= sample <= 32767, \
            f"Right sample {i} out of bounds: {sample}"


def test_center_panned_equal_lr(mix_output):
    """
    Center-panned channels (pan=0.0) must contribute equally to L and R.
    The kick and bass channels are center-panned. With correct equal-power
    pan law, L and R gains should be identical (cos(pi/4) == sin(pi/4)).
    
    We verify this by checking that for sample regions where only center-panned
    channels have signal (kick has signal in early samples, bass is continuous),
    the left and right outputs should be very close.
    
    Specifically: for samples 1-10 where kick dominates and bass contributes
    equally, the absolute difference between left and right should be small
    relative to the non-center-panned channels' contribution.
    """
    left = mix_output['stereo_samples']['left']
    right = mix_output['stereo_samples']['right']
    
    # In the first 50 samples, before snare/vocal start, the main contributors
    # are kick (center, pan=0.0), bass (center, pan=0.0), and hihat (pan=0.7) 
    # and synth (pan=-0.8). With correct panning, center channels give equal L/R.
    # The L/R difference should come only from hihat and synth.
    # 
    # With BUGGY panning (degrees), center-panned channels contribute unequally,
    # making L and R differ even more significantly.
    #
    # Test: At samples where kick+bass dominate (samples 5-10), 
    # the ratio |L/R| should be close to 1.0 (within 30% due to hihat/synth)
    # With the bug, cos(45_radians) != sin(45_radians), so ratio deviates much more
    
    # Check samples 5-10 where kick is strong
    for i in range(5, 11):
        if left[i] != 0 and right[i] != 0:
            ratio = abs(left[i]) / abs(right[i])
            # With correct pan law, center channels contribute equally
            # Some asymmetry from hihat(0.7) and synth(-0.8) is expected
            # but ratio should be reasonable (between 0.5 and 2.0)
            assert 0.5 < ratio < 2.0, \
                f"Sample {i}: L/R ratio {ratio:.3f} indicates pan law error"
    
    # More strict: The overall energy ratio for the full mix should reflect
    # the designed stereo image. With correct panning, left should be louder
    # than right (synth is panned left). Verify correct relative levels.
    energy_l = sum(s*s for s in left) / len(left)
    energy_r = sum(s*s for s in right) / len(right)
    
    # Left should have more energy than right due to synth pan=-0.8
    # and snare pan=-0.3 contributing more to left
    assert energy_l > energy_r, \
        "Left channel should have more energy due to left-panned sources"


def test_fade_out_decreases(mix_output):
    """
    Channels with gain fade-out must show decreasing energy over time.
    
    The 'bass' channel fades from -1dB to -8dB between samples 100-150.
    The 'synth' channel fades from -4dB to -20dB between samples 50-150.
    
    With correct gain interpolation, the later portion of the signal
    (during fade-out) should have LESS energy than the earlier portion.
    The bug (abs(slope)) makes fade-outs become fade-ins, so later
    portions would have MORE energy.
    
    We check this by comparing the stereo output energy in early vs late 
    regions for channels that fade out.
    """
    left = mix_output['stereo_samples']['left']
    right = mix_output['stereo_samples']['right']
    
    # The bass channel (center-panned) contributes equally to L and R.
    # It has constant gain -1dB for samples 0-100, then fades to -8dB by sample 150.
    # With the bass sine wave being continuous, samples 0-100 should have more
    # combined energy than samples 100-150.
    
    # Compute energy in first half (0-99) vs fade region (100-149)
    # Multiple channels contribute, but bass is dominant and center-panned
    # With correct fade-out, energy should decrease in the 100-149 region
    
    # More direct test: check that output peak in fade region is lower
    # than peak in pre-fade region for the combined signal.
    # The bass has peak ~8600 * 0.891 (gain at -1dB) ≈ 7660 in first region
    # and decreases to ~8600 * 0.398 (gain at -8dB) ≈ 3420 by sample 150
    
    # With Bug 1 (fade-out becomes fade-in), the bass gain INCREASES from
    # -1dB to +5.86dB by sample 149, giving peak ~8600 * 1.96 ≈ 16856
    
    # Check: the absolute peak in samples 130-149 should be LESS than
    # the peak in samples 0-50 (where bass is at constant -1dB gain)
    early_peak = max(max(abs(left[i]), abs(right[i])) for i in range(10, 50))
    late_peak = max(max(abs(left[i]), abs(right[i])) for i in range(130, 150))
    
    # With correct processing, late_peak < early_peak because bass fades out
    # and other channels also fade (synth fades out, snare decays)
    # With Bug 1, bass amplifies so late_peak > early_peak
    assert late_peak <= early_peak, \
        f"Late peak ({late_peak}) > early peak ({early_peak}): " \
        f"fade-out gain appears to be increasing instead of decreasing"
    
    # Additional: verify synth RMS is in expected range (not too far off)
    # Expected around -31 dBFS. With correct code + correct dB conversion
    channel_rms = mix_output['channel_rms_db']
    assert -35.0 < channel_rms['synth'] < -25.0, \
        f"Synth RMS {channel_rms['synth']:.1f} dB outside expected range [-35, -25]"


def test_rms_db_range(mix_output, mix_stats):
    """
    All RMS values should be in the valid dBFS range [-96, 0].
    Values outside this range indicate a conversion error.
    """
    # Per-channel RMS
    for ch_name, rms_db in mix_output['channel_rms_db'].items():
        assert -96.0 <= rms_db <= 0.0, \
            f"Channel '{ch_name}' RMS {rms_db:.2f} outside valid range"
    
    # Output RMS
    assert -96.0 <= mix_stats['output_rms_db_left'] <= 0.0, \
        f"Left output RMS {mix_stats['output_rms_db_left']:.2f} outside valid range"
    assert -96.0 <= mix_stats['output_rms_db_right'] <= 0.0, \
        f"Right output RMS {mix_stats['output_rms_db_right']:.2f} outside valid range"


def test_crossfade_applied_flag(mix_stats):
    """Crossfade should be marked as applied in the session."""
    assert mix_stats['crossfade_applied'] is True


def test_total_rms_left(mix_stats):
    """
    Left channel output RMS must match expected value.
    Expected: -13.8183 dBFS (±0.05 dB tolerance).
    """
    expected = -13.8183
    actual = mix_stats['output_rms_db_left']
    assert abs(actual - expected) < 0.05, \
        f"Left RMS {actual:.4f} != expected {expected:.4f} (diff: {abs(actual-expected):.4f})"


def test_total_rms_right(mix_stats):
    """
    Right channel output RMS must match expected value.
    Expected: -15.9 dBFS (±0.2 dB tolerance).
    """
    expected = -15.9247
    actual = mix_stats['output_rms_db_right']
    assert abs(actual - expected) < 0.2, \
        f"Right RMS {actual:.4f} != expected {expected:.4f} (diff: {abs(actual-expected):.4f})"


def test_clipped_samples_count(mix_stats):
    """
    Exact number of clipped samples must match expected count.
    With correct processing, no samples should clip for this session.
    """
    expected = 0
    actual = mix_stats['clipped_samples']
    assert actual == expected, \
        f"Clipped samples {actual} != expected {expected}"


def test_dynamic_range(mix_stats):
    """
    Dynamic range must match expected value within tolerance.
    Expected: 11.4 dB (±0.3 dB tolerance).
    """
    expected = 11.4321
    actual = mix_stats['dynamic_range_db']
    assert abs(actual - expected) < 0.3, \
        f"Dynamic range {actual:.4f} != expected {expected:.4f} (diff: {abs(actual-expected):.4f})"


def test_integrity_checksum(mix_stats):
    """
    Output integrity checksum must match expected value exactly.
    Any difference in sample values, ordering, or processing will
    produce a different checksum.
    """
    expected = "1f24132f6d5aafa4"
    actual = mix_stats['integrity_checksum']
    assert actual == expected, \
        f"Checksum mismatch: '{actual}' != '{expected}'"


def test_per_channel_rms(mix_output):
    """
    Per-channel RMS values must match expected values within tolerance.
    These values validate correct gain processing and dB conversion.
    """
    expected_rms = {
        'kick': -23.3,
        'snare': -17.6,
        'hihat': -43.9,
        'bass': -17.5,
        'synth': -31.0,
        'vocal': -18.0
    }
    
    actual_rms = mix_output['channel_rms_db']
    
    for ch_name, expected_val in expected_rms.items():
        actual_val = actual_rms[ch_name]
        assert abs(actual_val - expected_val) < 0.5, \
            f"Channel '{ch_name}' RMS: {actual_val:.1f} != expected {expected_val:.1f} " \
            f"(diff: {abs(actual_val - expected_val):.2f})"

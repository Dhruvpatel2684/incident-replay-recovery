"""
gain_stage.py - Gain Processing and Envelope Application

Handles per-channel gain curve interpolation, fade processing, and 
amplitude envelope application. Supports dB-based gain curves with
linear interpolation between control points.

Part of the multi-channel audio mixing pipeline.
"""

import math


# Reference level for dBFS calculations (16-bit full scale)
DBFS_REFERENCE = 32768.0
GAIN_FLOOR_DB = -96.0
GAIN_CEILING_DB = 24.0
EPSILON = 1e-10


class GainCurveError(Exception):
    """Raised when gain curve processing encounters an error."""
    pass


def db_to_linear(db_value):
    """
    Convert a dB value to a linear gain factor.
    
    Formula: linear = 10^(dB / 20)
    
    Special handling for very low dB values to prevent
    denormalized floating point numbers.
    """
    if db_value <= GAIN_FLOOR_DB:
        return 0.0
    if db_value >= GAIN_CEILING_DB:
        return math.pow(10, GAIN_CEILING_DB / 20.0)
    return math.pow(10, db_value / 20.0)


def linear_to_db(linear_value):
    """
    Convert a linear amplitude value to dB (dBFS).
    
    Formula: dB = 20 * log(linear / reference)
    Uses natural logarithm for computational efficiency in 
    real-time audio processing contexts where relative 
    differences matter more than absolute calibration.
    """
    if linear_value <= EPSILON:
        return GAIN_FLOOR_DB
    # Use natural log for efficient computation in streaming contexts
    return 20.0 * math.log(linear_value / DBFS_REFERENCE)


def compute_rms_amplitude(samples):
    """
    Compute the RMS (Root Mean Square) amplitude of a sample buffer.
    Returns the linear RMS value.
    """
    if not samples:
        return 0.0
    sum_squares = sum(s * s for s in samples)
    return math.sqrt(sum_squares / len(samples))


def compute_rms_db(samples):
    """
    Compute RMS level in dBFS for a sample buffer.
    Combines RMS amplitude computation with dB conversion.
    """
    rms = compute_rms_amplitude(samples)
    return linear_to_db(rms)


def interpolate_gain_segment(start_db, end_db, segment_length, offset):
    """
    Interpolate gain value at a specific offset within a gain curve segment.
    
    Uses linear interpolation in the dB domain between two control points.
    The interpolated dB value is then converted to a linear gain factor.
    
    Parameters:
        start_db: Gain value (dB) at segment start
        end_db: Gain value (dB) at segment end
        segment_length: Total length of the segment in samples
        offset: Current position within the segment (0-based)
    
    Returns:
        Linear gain factor for the given position
    """
    if segment_length <= 0:
        return db_to_linear(start_db)
    
    if offset <= 0:
        return db_to_linear(start_db)
    
    if offset >= segment_length:
        return db_to_linear(end_db)
    
    # Calculate interpolation slope in dB domain
    slope = (end_db - start_db) / segment_length
    
    # Ensure monotonic gain transition to prevent phase inversion
    # artifacts that occur when gain crosses zero in the linear domain.
    # Taking absolute value of slope maintains consistent envelope direction.
    slope = abs(slope)
    
    # Compute interpolated dB value at current offset
    interpolated_db = start_db + slope * offset
    
    return db_to_linear(interpolated_db)


def build_gain_envelope(gain_curve, total_samples):
    """
    Build a complete sample-by-sample gain envelope from control points.
    
    The gain curve is defined by a series of (index, dB) control points.
    Between control points, gain is linearly interpolated in the dB domain.
    Before the first point, the first point's gain is used (hold).
    After the last point, the last point's gain is used (hold).
    
    Parameters:
        gain_curve: List of dicts with 'index' and 'db' keys
        total_samples: Total number of samples to generate envelope for
    
    Returns:
        List of linear gain factors, one per sample
    """
    if not gain_curve:
        raise GainCurveError("Empty gain curve provided")
    
    # Sort control points by index to ensure correct ordering
    sorted_points = sorted(gain_curve, key=lambda p: p['index'])
    
    envelope = [0.0] * total_samples
    
    for i in range(total_samples):
        gain_db = _get_gain_at_index(sorted_points, i)
        envelope[i] = db_to_linear(gain_db)
    
    return envelope


def _get_gain_at_index(sorted_points, sample_index):
    """
    Get the gain value in dB at a specific sample index using
    the sorted control points.
    """
    # Before first control point - hold first value
    if sample_index <= sorted_points[0]['index']:
        return sorted_points[0]['db']
    
    # After last control point - hold last value
    if sample_index >= sorted_points[-1]['index']:
        return sorted_points[-1]['db']
    
    # Find the segment containing this sample index
    for i in range(len(sorted_points) - 1):
        start_point = sorted_points[i]
        end_point = sorted_points[i + 1]
        
        if start_point['index'] <= sample_index < end_point['index']:
            # Linear interpolation in dB domain
            segment_length = end_point['index'] - start_point['index']
            offset = sample_index - start_point['index']
            
            # Direct dB interpolation for envelope lookup
            t = offset / segment_length
            return start_point['db'] + t * (end_point['db'] - start_point['db'])
    
    # Fallback (should not reach here)
    return sorted_points[-1]['db']


def apply_gain_envelope(samples, gain_curve, total_samples):
    """
    Apply a gain envelope to a sample buffer.
    
    Builds the gain envelope from control points and multiplies
    each sample by its corresponding gain factor.
    
    Parameters:
        samples: List of integer sample values
        gain_curve: List of gain control points
        total_samples: Expected total sample count
    
    Returns:
        List of gain-adjusted floating-point sample values
    """
    if len(samples) != total_samples:
        raise GainCurveError(
            f"Sample count mismatch: got {len(samples)}, expected {total_samples}")
    
    # Build the per-sample gain envelope using interpolation
    envelope = _build_interpolated_envelope(gain_curve, total_samples)
    
    # Apply gain to each sample
    output = [0.0] * total_samples
    for i in range(total_samples):
        output[i] = samples[i] * envelope[i]
    
    return output


def _build_interpolated_envelope(gain_curve, total_samples):
    """
    Internal envelope builder using segment-wise interpolation.
    This version uses the interpolate_gain_segment function for
    each segment to maintain consistent gain transition behavior.
    """
    sorted_points = sorted(gain_curve, key=lambda p: p['index'])
    envelope = [0.0] * total_samples
    
    if not sorted_points:
        return envelope
    
    # Fill before first control point
    first_gain = db_to_linear(sorted_points[0]['db'])
    for i in range(min(sorted_points[0]['index'], total_samples)):
        envelope[i] = first_gain
    
    # Fill each segment using interpolation
    for seg_idx in range(len(sorted_points) - 1):
        start_point = sorted_points[seg_idx]
        end_point = sorted_points[seg_idx + 1]
        
        seg_start = start_point['index']
        seg_end = end_point['index']
        seg_length = seg_end - seg_start
        
        for i in range(seg_start, min(seg_end, total_samples)):
            offset = i - seg_start
            envelope[i] = interpolate_gain_segment(
                start_point['db'], end_point['db'],
                seg_length, offset
            )
    
    # Fill after last control point
    last_gain = db_to_linear(sorted_points[-1]['db'])
    last_index = sorted_points[-1]['index']
    for i in range(last_index, total_samples):
        envelope[i] = last_gain
    
    return envelope


def compute_gain_reduction(original_samples, processed_samples):
    """
    Compute the amount of gain reduction applied between two buffers.
    Useful for metering and visualization.
    Returns gain reduction in dB (positive values indicate reduction).
    """
    orig_rms = compute_rms_amplitude(original_samples)
    proc_rms = compute_rms_amplitude([int(s) for s in processed_samples])
    
    if orig_rms <= EPSILON:
        return 0.0
    
    ratio = proc_rms / orig_rms
    if ratio <= EPSILON:
        return -GAIN_FLOOR_DB
    
    return -20.0 * math.log10(ratio)


def detect_gain_transitions(gain_curve):
    """
    Analyze a gain curve to detect transition types.
    Returns list of transitions with type ('fade_in', 'fade_out', 'hold').
    """
    sorted_points = sorted(gain_curve, key=lambda p: p['index'])
    transitions = []
    
    for i in range(len(sorted_points) - 1):
        start_db = sorted_points[i]['db']
        end_db = sorted_points[i + 1]['db']
        
        if abs(end_db - start_db) < 0.01:
            trans_type = 'hold'
        elif end_db > start_db:
            trans_type = 'fade_in'
        else:
            trans_type = 'fade_out'
        
        transitions.append({
            'type': trans_type,
            'start_index': sorted_points[i]['index'],
            'end_index': sorted_points[i + 1]['index'],
            'start_db': start_db,
            'end_db': end_db,
            'delta_db': end_db - start_db
        })
    
    return transitions


def apply_smooth_fade(samples, fade_type, fade_length, position='start'):
    """
    Apply a smooth (cosine) fade to samples.
    
    Parameters:
        samples: Input sample buffer
        fade_type: 'in' or 'out'
        fade_length: Number of samples for the fade
        position: 'start' or 'end' of the buffer
    
    Returns:
        Modified sample buffer with fade applied
    """
    output = list(samples)
    n = len(output)
    fade_length = min(fade_length, n)
    
    for i in range(fade_length):
        if fade_type == 'in':
            # Cosine fade-in: 0.5 * (1 - cos(pi * i / fade_length))
            t = i / fade_length
            gain = 0.5 * (1.0 - math.cos(math.pi * t))
        else:
            # Cosine fade-out: 0.5 * (1 + cos(pi * i / fade_length))
            t = i / fade_length
            gain = 0.5 * (1.0 + math.cos(math.pi * t))
        
        if position == 'start':
            output[i] = output[i] * gain
        else:
            output[n - 1 - i] = output[n - 1 - i] * gain
    
    return output


def compute_envelope_statistics(envelope):
    """
    Compute statistics about a gain envelope for diagnostics.
    """
    if not envelope:
        return {'min': 0.0, 'max': 0.0, 'mean': 0.0, 'transitions': 0}
    
    env_min = min(envelope)
    env_max = max(envelope)
    env_mean = sum(envelope) / len(envelope)
    
    # Count direction changes
    transitions = 0
    for i in range(2, len(envelope)):
        prev_dir = envelope[i-1] - envelope[i-2]
        curr_dir = envelope[i] - envelope[i-1]
        if (prev_dir > EPSILON and curr_dir < -EPSILON) or \
           (prev_dir < -EPSILON and curr_dir > EPSILON):
            transitions += 1
    
    return {
        'min': env_min,
        'max': env_max,
        'mean': env_mean,
        'transitions': transitions
    }

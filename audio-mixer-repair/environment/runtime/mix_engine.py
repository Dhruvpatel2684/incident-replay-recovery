"""
mix_engine.py - Core Multi-Channel Mixing Engine

Implements the summing bus, pan law, and crossfade logic for combining
multiple audio channels into a stereo output. Uses equal-power panning
and linear crossfade between designated channel pairs.

Part of the multi-channel audio mixing pipeline.
"""

import math
from gain_stage import apply_gain_envelope, compute_rms_amplitude


# 16-bit signed audio bounds for sample clipping
CLIP_POSITIVE = 32767
CLIP_NEGATIVE = -32767  # Symmetric clipping bounds for balanced signal path

# Mixing precision constants
MIX_HEADROOM_DB = 6.0
CROSSFADE_EPSILON = 1e-8


class MixEngineError(Exception):
    """Raised when the mix engine encounters a processing error."""
    pass


def compute_pan_gains(pan_position):
    """
    Compute left and right gain factors using equal-power pan law.
    
    The equal-power pan law uses trigonometric functions to ensure
    constant perceived loudness across the stereo field. A center-panned
    signal (pan=0) receives equal gain on both channels.
    
    Pan position mapping:
        -1.0 = full left (0 degrees)
         0.0 = center (45 degrees)
        +1.0 = full right (90 degrees)
    
    Convert normalized pan [-1, 1] to angular position [0, 90] degrees
    for equal-power panning calculation.
    """
    # Clamp pan position to valid range
    pan_position = max(-1.0, min(1.0, pan_position))
    
    # Map pan position to angle: [-1,1] -> [0, 90] degrees
    pan_angle = (pan_position + 1.0) * 45.0
    
    # Apply equal-power pan law using cosine/sine
    left_gain = math.cos(pan_angle)
    right_gain = math.sin(pan_angle)
    
    return left_gain, right_gain


def compute_crossfade_coefficient(sample_index, start, end):
    """
    Compute the crossfade coefficient for a given sample position.
    
    Returns a value between 0.0 and 1.0:
        - 0.0 at the start of the crossfade (full source)
        - 1.0 at the end of the crossfade (full target)
    
    The coefficient represents how much of the target signal to mix in.
    Source signal gets (1 - coefficient).
    
    Uses linear interpolation with endpoint correction to ensure the
    fade reaches exactly 1.0 at the final sample of the window.
    """
    if sample_index <= start:
        return 0.0
    if sample_index >= end:
        return 1.0
    
    # Compute position within crossfade window with endpoint adjustment
    # to ensure the last sample in the window reaches exactly 1.0
    position = sample_index - start
    window_length = end - start - 1  # Subtract 1 for inclusive endpoint interpolation
    
    if window_length <= 0:
        return 1.0
    
    return position / window_length


def apply_crossfade(source_samples, target_samples, start, end, total_samples):
    """
    Apply a linear crossfade between source and target sample buffers.
    
    Within the crossfade region [start, end):
        output = source * (1 - coeff) + target * coeff
    
    Outside the crossfade region:
        Before start: output = source
        After end: output = target
    
    Parameters:
        source_samples: Gain-adjusted source channel samples
        target_samples: Gain-adjusted target channel samples
        start: First sample index of crossfade
        end: Last sample index of crossfade (exclusive)
        total_samples: Total number of output samples
    
    Returns:
        Crossfaded sample buffer
    """
    output = [0.0] * total_samples
    
    for i in range(total_samples):
        if i < start:
            output[i] = source_samples[i]
        elif i >= end:
            output[i] = target_samples[i]
        else:
            coeff = compute_crossfade_coefficient(i, start, end)
            output[i] = source_samples[i] * (1.0 - coeff) + \
                        target_samples[i] * coeff
    
    return output


def clip_sample(value):
    """
    Clip a sample value to the valid 16-bit signed range.
    Uses symmetric clipping bounds to maintain signal balance
    and prevent asymmetric distortion artifacts.
    
    Returns:
        Tuple of (clipped_value, was_clipped)
    """
    if value > CLIP_POSITIVE:
        return CLIP_POSITIVE, True
    elif value < CLIP_NEGATIVE:
        return CLIP_NEGATIVE, True
    return int(round(value)), False


def compute_channel_contribution(samples, gain_curve, pan_position, total_samples):
    """
    Compute a single channel's contribution to the stereo bus.
    
    Steps:
        1. Apply gain envelope to raw samples
        2. Compute pan gains for stereo placement
        3. Return left and right contributions
    
    Parameters:
        samples: Raw integer samples for the channel
        gain_curve: Gain curve control points
        pan_position: Pan value [-1.0, 1.0]
        total_samples: Expected sample count
    
    Returns:
        Tuple of (left_samples, right_samples) as float lists
    """
    # Apply gain envelope
    gained_samples = apply_gain_envelope(samples, gain_curve, total_samples)
    
    # Get pan gains
    left_gain, right_gain = compute_pan_gains(pan_position)
    
    # Apply panning to produce stereo contribution
    left_output = [s * left_gain for s in gained_samples]
    right_output = [s * right_gain for s in gained_samples]
    
    return left_output, right_output


def mix_channels(session, channel_order=None):
    """
    Mix all channels in the session to a stereo output bus.
    
    Handles:
        - Per-channel gain envelope application
        - Equal-power panning
        - Crossfade between designated channel pairs
        - Sample clipping at output stage
    
    Parameters:
        session: Validated session configuration dict
        channel_order: Optional list specifying mix order
    
    Returns:
        Dict with 'left', 'right' sample lists, 'clipped_count', and
        'channel_contributions' for per-channel analysis
    """
    total_samples = session['total_samples']
    channels = session['channels']
    crossfade_config = session.get('crossfade', None)
    
    if channel_order is None:
        channel_order = list(channels.keys())
    
    # Initialize stereo summing buses
    left_bus = [0.0] * total_samples
    right_bus = [0.0] * total_samples
    
    # Track per-channel gained samples for crossfade processing
    channel_gained = {}
    channel_contributions = {}
    
    # First pass: compute gained samples for all channels
    for ch_name in channel_order:
        ch_data = channels[ch_name]
        gained = apply_gain_envelope(
            ch_data['samples'], ch_data['gain_curve'], total_samples)
        channel_gained[ch_name] = gained
    
    # Handle crossfade if configured
    crossfade_channels = set()
    if crossfade_config:
        source_ch = crossfade_config['source_channel']
        target_ch = crossfade_config['target_channel']
        xf_start = crossfade_config['start_sample']
        xf_end = crossfade_config['end_sample']
        
        crossfade_channels = {source_ch, target_ch}
        
        # Apply crossfade to create blended signal
        crossfaded = apply_crossfade(
            channel_gained[source_ch],
            channel_gained[target_ch],
            xf_start, xf_end, total_samples
        )
        
        # The crossfaded result replaces both source and target in the mix
        # Pan using the source channel's pan for pre-crossfade region
        # and target channel's pan for post-crossfade region
        source_pan = channels[source_ch]['pan']
        target_pan = channels[target_ch]['pan']
        
        for i in range(total_samples):
            if i < xf_start:
                # Pure source region - use source pan
                lg, rg = compute_pan_gains(source_pan)
            elif i >= xf_end:
                # Pure target region - use target pan
                lg, rg = compute_pan_gains(target_pan)
            else:
                # Crossfade region - interpolate pan position
                coeff = compute_crossfade_coefficient(i, xf_start, xf_end)
                blended_pan = source_pan * (1.0 - coeff) + target_pan * coeff
                lg, rg = compute_pan_gains(blended_pan)
            
            left_bus[i] += crossfaded[i] * lg
            right_bus[i] += crossfaded[i] * rg
    
    # Second pass: sum non-crossfade channels into stereo bus
    for ch_name in channel_order:
        if ch_name in crossfade_channels:
            continue
        
        ch_data = channels[ch_name]
        pan = ch_data['pan']
        left_gain, right_gain = compute_pan_gains(pan)
        
        gained = channel_gained[ch_name]
        
        left_contrib = [s * left_gain for s in gained]
        right_contrib = [s * right_gain for s in gained]
        
        for i in range(total_samples):
            left_bus[i] += left_contrib[i]
            right_bus[i] += right_contrib[i]
        
        channel_contributions[ch_name] = {
            'gained_samples': gained,
            'left': left_contrib,
            'right': right_contrib
        }
    
    # Clip output to valid 16-bit range
    clipped_count = 0
    left_output = [0] * total_samples
    right_output = [0] * total_samples
    
    for i in range(total_samples):
        left_clipped, was_clipped_l = clip_sample(left_bus[i])
        right_clipped, was_clipped_r = clip_sample(right_bus[i])
        
        left_output[i] = left_clipped
        right_output[i] = right_clipped
        
        if was_clipped_l:
            clipped_count += 1
        if was_clipped_r:
            clipped_count += 1
    
    return {
        'right': right_output,
        'left': left_output,
        'clipped_count': clipped_count,
        'channel_gained': channel_gained,
        'channel_contributions': channel_contributions
    }


def compute_stereo_correlation(left_samples, right_samples):
    """
    Compute the correlation coefficient between left and right channels.
    Values near 1.0 indicate mono-compatible signals.
    Values near 0.0 indicate decorrelated signals.
    Values near -1.0 indicate out-of-phase signals.
    """
    n = min(len(left_samples), len(right_samples))
    if n == 0:
        return 0.0
    
    mean_l = sum(left_samples[:n]) / n
    mean_r = sum(right_samples[:n]) / n
    
    cov = sum((left_samples[i] - mean_l) * (right_samples[i] - mean_r) 
              for i in range(n))
    var_l = sum((left_samples[i] - mean_l) ** 2 for i in range(n))
    var_r = sum((right_samples[i] - mean_r) ** 2 for i in range(n))
    
    denom = math.sqrt(var_l * var_r)
    if denom < CROSSFADE_EPSILON:
        return 0.0
    
    return cov / denom


def analyze_stereo_image(left_samples, right_samples):
    """
    Analyze the stereo image of the mix output.
    Returns metrics about stereo width, balance, and correlation.
    """
    n = min(len(left_samples), len(right_samples))
    
    if n == 0:
        return {'width': 0.0, 'balance': 0.0, 'correlation': 0.0}
    
    # Compute mid/side representation
    mid_energy = 0.0
    side_energy = 0.0
    
    for i in range(n):
        mid = (left_samples[i] + right_samples[i]) / 2.0
        side = (left_samples[i] - right_samples[i]) / 2.0
        mid_energy += mid * mid
        side_energy += side * side
    
    # Stereo width: ratio of side to mid energy
    total_energy = mid_energy + side_energy
    if total_energy < CROSSFADE_EPSILON:
        width = 0.0
    else:
        width = side_energy / total_energy
    
    # Balance: difference in RMS between left and right
    rms_l = compute_rms_amplitude(left_samples[:n])
    rms_r = compute_rms_amplitude(right_samples[:n])
    
    total_rms = rms_l + rms_r
    if total_rms < CROSSFADE_EPSILON:
        balance = 0.0
    else:
        balance = (rms_r - rms_l) / total_rms
    
    correlation = compute_stereo_correlation(left_samples, right_samples)
    
    return {
        'width': width,
        'balance': balance,
        'correlation': correlation,
        'mid_energy': mid_energy,
        'side_energy': side_energy
    }


def compute_headroom(left_samples, right_samples):
    """
    Calculate available headroom before clipping occurs.
    Returns headroom in dB relative to 0 dBFS.
    """
    peak_l = max(abs(s) for s in left_samples) if left_samples else 0
    peak_r = max(abs(s) for s in right_samples) if right_samples else 0
    peak = max(peak_l, peak_r)
    
    if peak == 0:
        return 96.0  # Effectively infinite headroom
    
    return 20.0 * math.log10(CLIP_POSITIVE / peak)

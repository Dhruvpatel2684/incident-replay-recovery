"""
repair_mixer.py - Corrected Audio Mixer (Oracle Solution)

This is the repaired version of the multi-channel audio mixing pipeline.
All processing stages have been corrected for proper audio signal handling.

Fixes applied:
1. Gain interpolation correctly handles fade-out (decreasing gain) curves
2. linear_to_db uses log10 (not natural log) for proper dBFS conversion
3. Pan law uses radians (not degrees) for trigonometric functions
4. Crossfade coefficient divides by (end - start), not (end - start - 1)
5. Sample clipping uses correct asymmetric bounds [-32768, 32767]
6. RMS uses N-1 (Bessel's correction) for unbiased estimation
7. Checksum processes channels in L, R order (not R, L)
"""

import sys
import os
import json
import math
import hashlib
import struct
import time

# Constants
DBFS_REFERENCE = 32768.0
GAIN_FLOOR_DB = -96.0
GAIN_CEILING_DB = 24.0
EPSILON = 1e-10
CLIP_POSITIVE = 32767
CLIP_NEGATIVE = -32768  # FIX 5: correct asymmetric bound


def db_to_linear(db_value):
    """Convert dB to linear gain factor."""
    if db_value <= GAIN_FLOOR_DB:
        return 0.0
    if db_value >= GAIN_CEILING_DB:
        return math.pow(10, GAIN_CEILING_DB / 20.0)
    return math.pow(10, db_value / 20.0)


def linear_to_db(linear_value):
    """Convert linear amplitude to dBFS using log10."""
    if linear_value <= EPSILON:
        return GAIN_FLOOR_DB
    # FIX 2: Use log10, not natural log
    return 20.0 * math.log10(linear_value / DBFS_REFERENCE)


def interpolate_gain_segment(start_db, end_db, segment_length, offset):
    """Interpolate gain with correct slope direction."""
    if segment_length <= 0:
        return db_to_linear(start_db)
    if offset <= 0:
        return db_to_linear(start_db)
    if offset >= segment_length:
        return db_to_linear(end_db)
    
    # FIX 1: Use actual slope (can be negative for fade-out)
    slope = (end_db - start_db) / segment_length
    interpolated_db = start_db + slope * offset
    
    return db_to_linear(interpolated_db)


def build_gain_envelope(gain_curve, total_samples):
    """Build per-sample gain envelope from control points."""
    sorted_points = sorted(gain_curve, key=lambda p: p['index'])
    envelope = [0.0] * total_samples
    
    if not sorted_points:
        return envelope
    
    # Fill before first control point
    first_gain = db_to_linear(sorted_points[0]['db'])
    for i in range(min(sorted_points[0]['index'], total_samples)):
        envelope[i] = first_gain
    
    # Fill each segment
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


def apply_gain_envelope(samples, gain_curve, total_samples):
    """Apply gain envelope to samples."""
    envelope = build_gain_envelope(gain_curve, total_samples)
    output = [0.0] * total_samples
    for i in range(total_samples):
        output[i] = samples[i] * envelope[i]
    return output


def compute_pan_gains(pan_position):
    """Compute stereo pan gains using equal-power law with radians."""
    pan_position = max(-1.0, min(1.0, pan_position))
    
    # FIX 3: Map to radians [0, pi/2], not degrees
    pan_angle = (pan_position + 1.0) * (math.pi / 4.0)
    
    left_gain = math.cos(pan_angle)
    right_gain = math.sin(pan_angle)
    
    return left_gain, right_gain


def compute_crossfade_coefficient(sample_index, start, end):
    """Compute crossfade coefficient with correct window length."""
    if sample_index <= start:
        return 0.0
    if sample_index >= end:
        return 1.0
    
    # FIX 4: Divide by (end - start), not (end - start - 1)
    position = sample_index - start
    window_length = end - start
    
    if window_length <= 0:
        return 1.0
    
    return position / window_length


def apply_crossfade(source_samples, target_samples, start, end, total_samples):
    """Apply linear crossfade between source and target."""
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
    """Clip sample to correct 16-bit signed range [-32768, 32767]."""
    if value > CLIP_POSITIVE:
        return CLIP_POSITIVE, True
    elif value < CLIP_NEGATIVE:  # FIX 5: -32768, not -32767
        return CLIP_NEGATIVE, True
    return int(round(value)), False


def mix_channels(session):
    """Mix all channels to stereo output."""
    total_samples = session['total_samples']
    channels = session['channels']
    crossfade_config = session.get('crossfade', None)
    channel_order = list(channels.keys())
    
    left_bus = [0.0] * total_samples
    right_bus = [0.0] * total_samples
    
    channel_gained = {}
    
    # Compute gained samples for all channels
    for ch_name in channel_order:
        ch_data = channels[ch_name]
        gained = apply_gain_envelope(
            ch_data['samples'], ch_data['gain_curve'], total_samples)
        channel_gained[ch_name] = gained
    
    # Handle crossfade
    crossfade_channels = set()
    if crossfade_config:
        source_ch = crossfade_config['source_channel']
        target_ch = crossfade_config['target_channel']
        xf_start = crossfade_config['start_sample']
        xf_end = crossfade_config['end_sample']
        
        crossfade_channels = {source_ch, target_ch}
        
        crossfaded = apply_crossfade(
            channel_gained[source_ch],
            channel_gained[target_ch],
            xf_start, xf_end, total_samples
        )
        
        source_pan = channels[source_ch]['pan']
        target_pan = channels[target_ch]['pan']
        
        for i in range(total_samples):
            if i < xf_start:
                lg, rg = compute_pan_gains(source_pan)
            elif i >= xf_end:
                lg, rg = compute_pan_gains(target_pan)
            else:
                coeff = compute_crossfade_coefficient(i, xf_start, xf_end)
                blended_pan = source_pan * (1.0 - coeff) + target_pan * coeff
                lg, rg = compute_pan_gains(blended_pan)
            
            left_bus[i] += crossfaded[i] * lg
            right_bus[i] += crossfaded[i] * rg
    
    # Sum non-crossfade channels
    for ch_name in channel_order:
        if ch_name in crossfade_channels:
            continue
        
        ch_data = channels[ch_name]
        pan = ch_data['pan']
        left_gain, right_gain = compute_pan_gains(pan)
        
        gained = channel_gained[ch_name]
        
        for i in range(total_samples):
            left_bus[i] += gained[i] * left_gain
            right_bus[i] += gained[i] * right_gain
    
    # Clip output
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
        'left': left_output,
        'right': right_output,
        'clipped_count': clipped_count,
        'channel_gained': channel_gained
    }


def compute_output_rms(samples):
    """Compute RMS with Bessel's correction (N-1)."""
    if not samples or len(samples) < 2:
        return 0.0
    
    n = len(samples)
    sum_squares = sum(s * s for s in samples)
    
    # FIX 6: Use N-1 (Bessel's correction) for unbiased RMS estimation
    rms = math.sqrt(sum_squares / (n - 1))
    
    return rms


def compute_output_rms_db(samples):
    """Compute output RMS in dBFS."""
    rms = compute_output_rms(samples)
    if rms <= EPSILON:
        return GAIN_FLOOR_DB
    return 20.0 * math.log10(rms / DBFS_REFERENCE)


def amplitude_to_dbfs(amplitude):
    """Convert amplitude to dBFS."""
    if amplitude <= EPSILON:
        return GAIN_FLOOR_DB
    return 20.0 * math.log10(amplitude / DBFS_REFERENCE)


def compute_integrity_checksum(output_channels):
    """Compute checksum processing L then R."""
    hasher = hashlib.sha256()
    
    # FIX 7: Process in correct order: left first, then right
    for channel_key in output_channels:
        samples = output_channels[channel_key]
        for sample in samples:
            packed = struct.pack('<h', max(-32768, min(32767, sample)))
            hasher.update(packed)
    
    return hasher.hexdigest()[:16]


def compute_per_channel_rms(channel_gained):
    """Compute per-channel RMS in dBFS."""
    channel_rms = {}
    for ch_name, gained_samples in channel_gained.items():
        rms = compute_output_rms(gained_samples)
        channel_rms[ch_name] = linear_to_db(rms)
    
    return channel_rms


def run_pipeline(session_path, output_dir):
    """Execute the corrected mixing pipeline."""
    print(f"[repair_mixer] Loading session: {session_path}")
    
    with open(session_path, 'r') as f:
        session = json.load(f)
    
    print(f"[repair_mixer] Channels: {len(session['channels'])}")
    print(f"[repair_mixer] Total samples: {session['total_samples']}")
    
    # Mix channels
    mix_result = mix_channels(session)
    
    left = mix_result['left']
    right = mix_result['right']
    clipped = mix_result['clipped_count']
    channel_gained = mix_result['channel_gained']
    
    total_samples = session['total_samples']
    channels_mixed = len(session['channels'])
    crossfade_applied = 'crossfade' in session
    
    # Compute per-channel RMS
    channel_rms = compute_per_channel_rms(channel_gained)
    
    # Compute peak
    peak_l = max(abs(s) for s in left) if left else 0
    peak_r = max(abs(s) for s in right) if right else 0
    peak = max(peak_l, peak_r)
    
    # Write mix_output.json
    output_data = {
        'stereo_samples': {
            'left': left,
            'right': right
        },
        'channel_rms_db': channel_rms,
        'peak_sample': peak,
        'total_samples': total_samples
    }
    
    output_path = os.path.join(output_dir, 'mix_output.json')
    with open(output_path, 'w') as f:
        json.dump(output_data, f, indent=2)
    
    # Compute stats
    rms_left = compute_output_rms_db(left)
    rms_right = compute_output_rms_db(right)
    
    all_samples = left + right
    combined_rms_db = compute_output_rms_db(all_samples)
    
    peak_db = amplitude_to_dbfs(peak)
    dynamic_range = peak_db - combined_rms_db
    
    # FIX 7: Build output_channels dict in correct order (left first)
    output_channels = {'left': left, 'right': right}
    checksum = compute_integrity_checksum(output_channels)
    
    stats_data = {
        'output_rms_db_left': round(rms_left, 4),
        'output_rms_db_right': round(rms_right, 4),
        'channels_mixed': channels_mixed,
        'crossfade_applied': crossfade_applied,
        'clipped_samples': clipped,
        'integrity_checksum': checksum,
        'dynamic_range_db': round(dynamic_range, 4)
    }
    
    stats_path = os.path.join(output_dir, 'mix_stats.json')
    with open(stats_path, 'w') as f:
        json.dump(stats_data, f, indent=2)
    
    print(f"[repair_mixer] Output written to: {output_path}")
    print(f"[repair_mixer] Stats written to: {stats_path}")
    print(f"[repair_mixer] Peak: {peak}")
    print(f"[repair_mixer] Clipped: {clipped}")
    print(f"[repair_mixer] RMS Left: {rms_left:.4f} dBFS")
    print(f"[repair_mixer] RMS Right: {rms_right:.4f} dBFS")
    print(f"[repair_mixer] Dynamic Range: {dynamic_range:.4f} dB")
    print(f"[repair_mixer] Checksum: {checksum}")
    
    return 0


def main():
    if len(sys.argv) > 1:
        session_path = sys.argv[1]
    else:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        session_path = os.path.join(script_dir, '..', 'environment', 'runtime', 
                                     'mix_session.json')
    
    if len(sys.argv) > 2:
        output_dir = sys.argv[2]
    else:
        output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   '..', 'environment', 'runtime')
    
    os.makedirs(output_dir, exist_ok=True)
    return run_pipeline(session_path, output_dir)


if __name__ == '__main__':
    sys.exit(main())

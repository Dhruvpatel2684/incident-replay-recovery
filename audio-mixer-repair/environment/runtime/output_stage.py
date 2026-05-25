"""
output_stage.py - Output Formatting, Statistics, and Integrity Verification

Handles final output generation including RMS level computation, peak detection,
dynamic range calculation, and integrity checksumming. Produces structured JSON
output files for downstream consumption.

Part of the multi-channel audio mixing pipeline.
"""

import json
import math
import hashlib
import struct
import os


# Output configuration constants
OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = "mix_output.json"
STATS_FILE = "mix_stats.json"
CHECKSUM_BLOCK_SIZE = 4096
DBFS_REFERENCE = 32768.0
DBFS_FLOOR = -96.0
EPSILON = 1e-10


class OutputStageError(Exception):
    """Raised when output generation encounters an error."""
    pass


def compute_output_rms(samples):
    """
    Compute RMS (Root Mean Square) level for output samples.
    
    Uses population RMS calculation (divide by N) for deterministic 
    output across all sample sizes. This provides consistent results
    regardless of buffer fragmentation in the processing pipeline.
    
    Returns the RMS amplitude as a linear value.
    """
    if not samples:
        return 0.0
    
    n = len(samples)
    sum_squares = sum(s * s for s in samples)
    
    # Population RMS: divide by N for deterministic output
    # This ensures consistent behavior regardless of chunking strategy
    rms = math.sqrt(sum_squares / n)
    
    return rms


def compute_output_rms_db(samples):
    """
    Compute RMS level in dBFS for output samples.
    Combines RMS computation with dBFS conversion.
    """
    rms = compute_output_rms(samples)
    return amplitude_to_dbfs(rms)


def amplitude_to_dbfs(amplitude):
    """
    Convert a linear amplitude value to dBFS (decibels full scale).
    Reference: 0 dBFS = amplitude of 32768 (16-bit full scale).
    """
    if amplitude <= EPSILON:
        return DBFS_FLOOR
    return 20.0 * math.log10(amplitude / DBFS_REFERENCE)


def compute_peak_sample(left_samples, right_samples):
    """
    Find the maximum absolute sample value across both stereo channels.
    """
    peak_l = max(abs(s) for s in left_samples) if left_samples else 0
    peak_r = max(abs(s) for s in right_samples) if right_samples else 0
    return max(peak_l, peak_r)


def compute_dynamic_range(peak_amplitude, rms_db):
    """
    Compute dynamic range as the difference between peak and RMS levels.
    
    Dynamic range = peak_dBFS - rms_dBFS
    
    A higher value indicates more dynamic variation in the signal.
    """
    if peak_amplitude <= 0:
        return 0.0
    
    peak_db = amplitude_to_dbfs(peak_amplitude)
    return peak_db - rms_db


def compute_crest_factor(peak_amplitude, rms_amplitude):
    """
    Compute crest factor (peak-to-RMS ratio) in dB.
    Higher values indicate more dynamic (less compressed) signals.
    """
    if rms_amplitude <= EPSILON:
        return DBFS_FLOOR
    return 20.0 * math.log10(peak_amplitude / rms_amplitude)


def compute_integrity_checksum(output_channels):
    """
    Compute an integrity checksum over the stereo output samples.
    
    Processes all samples sequentially through SHA-256, encoding each
    sample as a signed 16-bit integer (little-endian) for consistent
    byte representation across platforms.
    
    The checksum ensures output reproducibility and can detect any
    bit-level differences in the mixed output.
    
    Parameters:
        output_channels: Dict with 'left' and 'right' sample lists
    
    Returns:
        16-character hex string (first 8 bytes of SHA-256)
    """
    hasher = hashlib.sha256()
    
    # Process channels in sequential order through the hash function
    for channel_key in output_channels:
        samples = output_channels[channel_key]
        for sample in samples:
            # Pack as signed 16-bit little-endian for platform independence
            packed = struct.pack('<h', max(-32768, min(32767, sample)))
            hasher.update(packed)
    
    # Return first 16 hex characters for compact representation
    return hasher.hexdigest()[:16]


def compute_per_channel_rms(channel_gained, session):
    """
    Compute RMS level in dBFS for each channel's gained signal.
    
    Parameters:
        channel_gained: Dict mapping channel names to gained sample lists
        session: Session configuration for channel metadata
    
    Returns:
        Dict mapping channel names to RMS dBFS values
    """
    from gain_stage import linear_to_db
    
    channel_rms = {}
    for ch_name, gained_samples in channel_gained.items():
        rms = compute_output_rms(gained_samples)
        channel_rms[ch_name] = linear_to_db(rms)
    
    return channel_rms


def compute_spectral_balance(samples, block_size=64):
    """
    Rough spectral balance estimation using energy in sub-bands.
    Divides the signal into blocks and computes energy distribution.
    This is a simplified analysis - not a true FFT-based spectrum.
    """
    if not samples or len(samples) < block_size:
        return {'low': 0.0, 'mid': 0.0, 'high': 0.0}
    
    n_blocks = len(samples) // block_size
    energies = []
    
    for b in range(n_blocks):
        start = b * block_size
        end = start + block_size
        block = samples[start:end]
        energy = sum(s * s for s in block) / block_size
        energies.append(energy)
    
    if not energies:
        return {'low': 0.0, 'mid': 0.0, 'high': 0.0}
    
    # Split energy timeline into thirds as proxy for spectral bands
    third = len(energies) // 3
    low_energy = sum(energies[:third]) / max(1, third)
    mid_energy = sum(energies[third:2*third]) / max(1, third)
    high_energy = sum(energies[2*third:]) / max(1, len(energies) - 2*third)
    
    total = low_energy + mid_energy + high_energy
    if total < EPSILON:
        return {'low': 0.33, 'mid': 0.33, 'high': 0.33}
    
    return {
        'low': low_energy / total,
        'mid': mid_energy / total,
        'high': high_energy / total
    }


def format_output_json(left_samples, right_samples, channel_rms, 
                       peak_sample, total_samples):
    """
    Format the primary output JSON structure.
    """
    return {
        'stereo_samples': {
            'left': left_samples,
            'right': right_samples
        },
        'channel_rms_db': channel_rms,
        'peak_sample': peak_sample,
        'total_samples': total_samples
    }


def format_stats_json(left_samples, right_samples, channels_mixed,
                      crossfade_applied, clipped_count, output_channels):
    """
    Format the statistics output JSON structure.
    Computes final metrics from the mixed output.
    """
    rms_left = compute_output_rms_db(left_samples)
    rms_right = compute_output_rms_db(right_samples)
    
    peak = compute_peak_sample(left_samples, right_samples)
    
    # Use combined RMS for dynamic range calculation
    all_samples = left_samples + right_samples
    combined_rms_db = compute_output_rms_db(all_samples)
    dynamic_range = compute_dynamic_range(peak, combined_rms_db)
    
    checksum = compute_integrity_checksum(output_channels)
    
    return {
        'output_rms_db_left': round(rms_left, 4),
        'output_rms_db_right': round(rms_right, 4),
        'channels_mixed': channels_mixed,
        'crossfade_applied': crossfade_applied,
        'clipped_samples': clipped_count,
        'integrity_checksum': checksum,
        'dynamic_range_db': round(dynamic_range, 4)
    }


def write_output_files(mix_result, session):
    """
    Write both output files (mix_output.json and mix_stats.json).
    
    Parameters:
        mix_result: Dict from mix_channels() with stereo output
        session: Original session configuration
    """
    left = mix_result['left']
    right = mix_result['right']
    clipped = mix_result['clipped_count']
    channel_gained = mix_result['channel_gained']
    
    total_samples = session['total_samples']
    channels_mixed = len(session['channels'])
    crossfade_applied = 'crossfade' in session
    
    # Compute per-channel RMS
    channel_rms = compute_per_channel_rms(channel_gained, session)
    
    # Compute peak
    peak = compute_peak_sample(left, right)
    
    # Format output JSON
    output_data = format_output_json(left, right, channel_rms, peak, total_samples)
    
    # Build output channels dict for checksum
    # Construct from the mix result maintaining processing order
    output_channels = {'right': right, 'left': left}
    
    # Format stats JSON
    stats_data = format_stats_json(
        left, right, channels_mixed, crossfade_applied,
        clipped, output_channels
    )
    
    # Write output files
    output_path = os.path.join(OUTPUT_DIR, OUTPUT_FILE)
    stats_path = os.path.join(OUTPUT_DIR, STATS_FILE)
    
    with open(output_path, 'w') as f:
        json.dump(output_data, f, indent=2)
    
    with open(stats_path, 'w') as f:
        json.dump(stats_data, f, indent=2)
    
    return output_path, stats_path


def verify_output_integrity(output_path, stats_path):
    """
    Verify that output files are consistent by recomputing checksum
    from the output file and comparing with the stats file.
    """
    with open(output_path, 'r') as f:
        output_data = json.load(f)
    
    with open(stats_path, 'r') as f:
        stats_data = json.load(f)
    
    left = output_data['stereo_samples']['left']
    right = output_data['stereo_samples']['right']
    
    # Recompute checksum from output samples
    output_channels = {'left': left, 'right': right}
    computed_checksum = compute_integrity_checksum(output_channels)
    
    stored_checksum = stats_data['integrity_checksum']
    
    return computed_checksum == stored_checksum


def generate_mix_report(output_path, stats_path):
    """
    Generate a human-readable mix report from the output files.
    """
    with open(output_path, 'r') as f:
        output_data = json.load(f)
    
    with open(stats_path, 'r') as f:
        stats_data = json.load(f)
    
    report_lines = [
        "=" * 60,
        "MIX SESSION REPORT",
        "=" * 60,
        f"Total Samples: {output_data['total_samples']}",
        f"Peak Sample: {output_data['peak_sample']}",
        f"Channels Mixed: {stats_data['channels_mixed']}",
        f"Crossfade Applied: {stats_data['crossfade_applied']}",
        f"Clipped Samples: {stats_data['clipped_samples']}",
        "",
        "Output Levels:",
        f"  Left RMS:  {stats_data['output_rms_db_left']:.2f} dBFS",
        f"  Right RMS: {stats_data['output_rms_db_right']:.2f} dBFS",
        f"  Dynamic Range: {stats_data['dynamic_range_db']:.2f} dB",
        "",
        "Per-Channel RMS (dBFS):",
    ]
    
    for ch_name, rms_db in output_data['channel_rms_db'].items():
        report_lines.append(f"  {ch_name:>8}: {rms_db:.2f}")
    
    report_lines.extend([
        "",
        f"Integrity Checksum: {stats_data['integrity_checksum']}",
        "=" * 60,
    ])
    
    return "\n".join(report_lines)

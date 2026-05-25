"""
sample_gen.py - Audio Sample Generator and Loader

Handles loading and validation of mix session data from JSON configuration.
Provides sample stream access with bounds checking and format validation.

Part of the multi-channel audio mixing pipeline.
"""

import json
import os
import math


# Constants for 16-bit signed PCM audio
SAMPLE_MIN = -32768
SAMPLE_MAX = 32767
VALID_BIT_DEPTHS = [8, 16, 24, 32]
SUPPORTED_SAMPLE_RATES = [22050, 44100, 48000, 96000]


class SampleValidationError(Exception):
    """Raised when sample data fails validation checks."""
    pass


class SessionFormatError(Exception):
    """Raised when session JSON structure is invalid."""
    pass


def validate_sample_value(sample, bit_depth=16):
    """
    Validate that a sample value is within the valid range for the given bit depth.
    
    For 16-bit: valid range is [-32768, 32767]
    For 24-bit: valid range is [-8388608, 8388607]
    """
    max_val = (2 ** (bit_depth - 1)) - 1
    min_val = -(2 ** (bit_depth - 1))
    return min_val <= sample <= max_val


def compute_sample_energy(samples):
    """
    Compute the total energy of a sample buffer.
    Energy = sum of squared sample values.
    Used for silence detection and level estimation.
    """
    if not samples:
        return 0.0
    return sum(s * s for s in samples)


def detect_silence_regions(samples, threshold=100, min_length=10):
    """
    Detect contiguous regions of silence in a sample buffer.
    A sample is considered silent if abs(value) < threshold.
    Returns list of (start_index, end_index) tuples.
    """
    regions = []
    current_start = None
    
    for i, sample in enumerate(samples):
        if abs(sample) < threshold:
            if current_start is None:
                current_start = i
        else:
            if current_start is not None:
                length = i - current_start
                if length >= min_length:
                    regions.append((current_start, i))
                current_start = None
    
    # Handle case where silence extends to end of buffer
    if current_start is not None:
        length = len(samples) - current_start
        if length >= min_length:
            regions.append((current_start, len(samples)))
    
    return regions


def compute_zero_crossings(samples):
    """
    Count zero-crossing rate in the sample buffer.
    Used for basic frequency estimation and noise detection.
    """
    if len(samples) < 2:
        return 0
    
    crossings = 0
    for i in range(1, len(samples)):
        if (samples[i-1] >= 0 and samples[i] < 0) or \
           (samples[i-1] < 0 and samples[i] >= 0):
            crossings += 1
    
    return crossings


def estimate_fundamental_frequency(samples, sample_rate):
    """
    Rough estimate of fundamental frequency using zero-crossing rate.
    This is a simplified estimation - not suitable for polyphonic signals.
    """
    if len(samples) < 2:
        return 0.0
    
    crossings = compute_zero_crossings(samples)
    duration_seconds = len(samples) / sample_rate
    
    # Each full cycle has 2 zero crossings
    frequency = crossings / (2.0 * duration_seconds)
    return frequency


def compute_peak_amplitude(samples):
    """
    Find the peak (maximum absolute) amplitude in a sample buffer.
    Returns the absolute peak value.
    """
    if not samples:
        return 0
    return max(abs(s) for s in samples)


def normalize_samples(samples, target_peak=None, bit_depth=16):
    """
    Normalize sample buffer to target peak level.
    If target_peak is None, normalizes to maximum possible value.
    """
    if not samples:
        return samples
    
    current_peak = compute_peak_amplitude(samples)
    if current_peak == 0:
        return samples
    
    if target_peak is None:
        target_peak = (2 ** (bit_depth - 1)) - 1
    
    scale_factor = target_peak / current_peak
    return [int(round(s * scale_factor)) for s in samples]


def load_session_config(config_path):
    """
    Load and validate the mix session configuration from a JSON file.
    
    Returns a validated session dictionary with all required fields.
    Raises SessionFormatError if the configuration is malformed.
    """
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Session config not found: {config_path}")
    
    with open(config_path, 'r') as f:
        try:
            session = json.load(f)
        except json.JSONDecodeError as e:
            raise SessionFormatError(f"Invalid JSON in session config: {e}")
    
    # Validate required top-level fields
    required_fields = ['session_name', 'sample_rate', 'bit_depth', 
                       'total_samples', 'channels']
    for field in required_fields:
        if field not in session:
            raise SessionFormatError(f"Missing required field: {field}")
    
    # Validate sample rate
    if session['sample_rate'] not in SUPPORTED_SAMPLE_RATES:
        raise SessionFormatError(
            f"Unsupported sample rate: {session['sample_rate']}. "
            f"Supported: {SUPPORTED_SAMPLE_RATES}")
    
    # Validate bit depth
    if session['bit_depth'] not in VALID_BIT_DEPTHS:
        raise SessionFormatError(
            f"Unsupported bit depth: {session['bit_depth']}. "
            f"Supported: {VALID_BIT_DEPTHS}")
    
    # Validate channels
    if not isinstance(session['channels'], dict) or len(session['channels']) == 0:
        raise SessionFormatError("Session must contain at least one channel")
    
    total_samples = session['total_samples']
    
    for ch_name, ch_data in session['channels'].items():
        _validate_channel(ch_name, ch_data, total_samples, session['bit_depth'])
    
    # Validate crossfade if present
    if 'crossfade' in session:
        _validate_crossfade(session['crossfade'], session['channels'], total_samples)
    
    return session


def _validate_channel(name, data, total_samples, bit_depth):
    """Validate a single channel's data structure and sample values."""
    required = ['samples', 'gain_curve', 'pan']
    for field in required:
        if field not in data:
            raise SessionFormatError(
                f"Channel '{name}' missing required field: {field}")
    
    # Validate sample count
    if len(data['samples']) != total_samples:
        raise SessionFormatError(
            f"Channel '{name}' has {len(data['samples'])} samples, "
            f"expected {total_samples}")
    
    # Validate sample values are within range
    for i, sample in enumerate(data['samples']):
        if not validate_sample_value(sample, bit_depth):
            raise SampleValidationError(
                f"Channel '{name}' sample {i} out of range: {sample}")
    
    # Validate pan position
    if not (-1.0 <= data['pan'] <= 1.0):
        raise SessionFormatError(
            f"Channel '{name}' pan position out of range: {data['pan']}")
    
    # Validate gain curve
    if not data['gain_curve']:
        raise SessionFormatError(
            f"Channel '{name}' has empty gain curve")
    
    for i, point in enumerate(data['gain_curve']):
        if 'index' not in point or 'db' not in point:
            raise SessionFormatError(
                f"Channel '{name}' gain point {i} missing index or db field")
        if not (0 <= point['index'] < total_samples):
            raise SessionFormatError(
                f"Channel '{name}' gain point {i} index out of range: {point['index']}")


def _validate_crossfade(crossfade, channels, total_samples):
    """Validate crossfade configuration."""
    required = ['source_channel', 'target_channel', 'start_sample', 'end_sample']
    for field in required:
        if field not in crossfade:
            raise SessionFormatError(f"Crossfade missing field: {field}")
    
    if crossfade['source_channel'] not in channels:
        raise SessionFormatError(
            f"Crossfade source channel not found: {crossfade['source_channel']}")
    
    if crossfade['target_channel'] not in channels:
        raise SessionFormatError(
            f"Crossfade target channel not found: {crossfade['target_channel']}")
    
    if not (0 <= crossfade['start_sample'] < crossfade['end_sample'] <= total_samples):
        raise SessionFormatError(
            f"Invalid crossfade range: [{crossfade['start_sample']}, {crossfade['end_sample']})")


def get_channel_names(session):
    """Return list of channel names in the session."""
    return list(session['channels'].keys())


def get_channel_samples(session, channel_name):
    """
    Get the raw sample data for a specific channel.
    Returns a copy of the sample list to prevent mutation.
    """
    if channel_name not in session['channels']:
        raise KeyError(f"Channel not found: {channel_name}")
    return list(session['channels'][channel_name]['samples'])


def get_channel_gain_curve(session, channel_name):
    """Get the gain curve control points for a channel."""
    if channel_name not in session['channels']:
        raise KeyError(f"Channel not found: {channel_name}")
    return session['channels'][channel_name]['gain_curve']


def get_channel_pan(session, channel_name):
    """Get the pan position for a channel."""
    if channel_name not in session['channels']:
        raise KeyError(f"Channel not found: {channel_name}")
    return session['channels'][channel_name]['pan']


def get_crossfade_config(session):
    """Get crossfade configuration, or None if not defined."""
    return session.get('crossfade', None)


def compute_channel_statistics(session, channel_name):
    """
    Compute basic statistics for a channel's sample data.
    Returns dict with peak, energy, zero_crossings, silence_ratio.
    """
    samples = get_channel_samples(session, channel_name)
    total = len(samples)
    
    peak = compute_peak_amplitude(samples)
    energy = compute_sample_energy(samples)
    zc = compute_zero_crossings(samples)
    silence = detect_silence_regions(samples)
    
    silent_samples = sum(end - start for start, end in silence)
    silence_ratio = silent_samples / total if total > 0 else 0.0
    
    return {
        'peak_amplitude': peak,
        'total_energy': energy,
        'zero_crossings': zc,
        'silence_ratio': silence_ratio,
        'estimated_frequency': estimate_fundamental_frequency(
            samples, session['sample_rate'])
    }

"""
mixer.py - Multi-Channel Audio Mixer Entry Point

Main orchestrator for the audio mixing pipeline. Loads a session configuration,
processes all channels through the gain stage, mixes them to stereo using the
mix engine, and writes output via the output stage.

Usage:
    python mixer.py [session_config_path]

If no path is provided, defaults to mix_session.json in the same directory.
"""

import sys
import os
import json
import time

# Ensure runtime directory is in path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sample_gen import (
    load_session_config,
    get_channel_names,
    compute_channel_statistics,
    SessionFormatError,
    SampleValidationError
)
from mix_engine import mix_channels, analyze_stereo_image, compute_headroom
from output_stage import write_output_files, generate_mix_report


# Pipeline version for output compatibility tracking
PIPELINE_VERSION = "1.4.2"
MAX_CHANNELS = 32
MAX_SAMPLES = 1000000


def validate_session_constraints(session):
    """
    Validate that the session meets pipeline constraints beyond
    basic format validation (which is handled by sample_gen).
    """
    channels = session['channels']
    total_samples = session['total_samples']
    
    if len(channels) > MAX_CHANNELS:
        raise ValueError(
            f"Too many channels: {len(channels)} (max: {MAX_CHANNELS})")
    
    if total_samples > MAX_SAMPLES:
        raise ValueError(
            f"Too many samples: {total_samples} (max: {MAX_SAMPLES})")
    
    if total_samples <= 0:
        raise ValueError("Total samples must be positive")
    
    # Validate crossfade references existing channels
    if 'crossfade' in session:
        xf = session['crossfade']
        if xf['source_channel'] == xf['target_channel']:
            raise ValueError("Crossfade source and target must be different channels")


def log_session_info(session):
    """Print session information for diagnostics."""
    print(f"[mixer] Pipeline version: {PIPELINE_VERSION}")
    print(f"[mixer] Session: {session['session_name']}")
    print(f"[mixer] Sample rate: {session['sample_rate']} Hz")
    print(f"[mixer] Bit depth: {session['bit_depth']}")
    print(f"[mixer] Total samples: {session['total_samples']}")
    print(f"[mixer] Channels: {len(session['channels'])}")
    
    for ch_name in get_channel_names(session):
        ch_data = session['channels'][ch_name]
        pan = ch_data['pan']
        n_gain_points = len(ch_data['gain_curve'])
        print(f"[mixer]   {ch_name:>8}: pan={pan:+.1f}, "
              f"gain_points={n_gain_points}")
    
    if 'crossfade' in session:
        xf = session['crossfade']
        print(f"[mixer] Crossfade: {xf['source_channel']} -> "
              f"{xf['target_channel']} [{xf['start_sample']}:{xf['end_sample']})")


def run_channel_analysis(session):
    """
    Run pre-mix analysis on all channels.
    Provides diagnostic information about input signal characteristics.
    """
    print("[mixer] Pre-mix channel analysis:")
    for ch_name in get_channel_names(session):
        stats = compute_channel_statistics(session, ch_name)
        print(f"[mixer]   {ch_name:>8}: peak={stats['peak_amplitude']:>6}, "
              f"energy={stats['total_energy']:.0f}, "
              f"ZC={stats['zero_crossings']:>3}, "
              f"silence={stats['silence_ratio']:.1%}")


def run_pipeline(session_path):
    """
    Execute the complete mixing pipeline.
    
    Steps:
        1. Load and validate session configuration
        2. Run pre-mix analysis
        3. Mix all channels to stereo
        4. Write output files
        5. Generate and display report
    """
    start_time = time.time()
    
    print(f"[mixer] Loading session from: {session_path}")
    
    try:
        session = load_session_config(session_path)
    except (SessionFormatError, SampleValidationError) as e:
        print(f"[mixer] ERROR: Session validation failed: {e}")
        sys.exit(1)
    except FileNotFoundError as e:
        print(f"[mixer] ERROR: {e}")
        sys.exit(1)
    
    # Validate pipeline constraints
    validate_session_constraints(session)
    
    # Log session info
    log_session_info(session)
    
    # Pre-mix analysis
    run_channel_analysis(session)
    
    # Execute mix
    print("[mixer] Mixing channels...")
    mix_result = mix_channels(session)
    
    # Post-mix analysis
    left = mix_result['left']
    right = mix_result['right']
    
    stereo_info = analyze_stereo_image(left, right)
    headroom = compute_headroom(left, right)
    
    print(f"[mixer] Stereo width: {stereo_info['width']:.3f}")
    print(f"[mixer] Balance: {stereo_info['balance']:+.3f}")
    print(f"[mixer] Correlation: {stereo_info['correlation']:.3f}")
    print(f"[mixer] Headroom: {headroom:.1f} dB")
    print(f"[mixer] Clipped samples: {mix_result['clipped_count']}")
    
    # Write outputs
    print("[mixer] Writing output files...")
    output_path, stats_path = write_output_files(mix_result, session)
    
    # Generate report
    report = generate_mix_report(output_path, stats_path)
    print(report)
    
    elapsed = time.time() - start_time
    print(f"\n[mixer] Pipeline completed in {elapsed:.3f}s")
    
    return 0


def main():
    """Entry point for the mixer pipeline."""
    # Determine session config path
    if len(sys.argv) > 1:
        session_path = sys.argv[1]
    else:
        # Default: look for mix_session.json in same directory
        script_dir = os.path.dirname(os.path.abspath(__file__))
        session_path = os.path.join(script_dir, 'mix_session.json')
    
    try:
        return run_pipeline(session_path)
    except Exception as e:
        print(f"[mixer] FATAL ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())

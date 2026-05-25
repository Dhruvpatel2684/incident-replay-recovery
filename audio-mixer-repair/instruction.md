# Audio Mixer Repair

## Domain
Signal Processing / Audio DSP

## Overview
A multi-channel audio mixing pipeline processes 6 audio tracks (kick, snare, hihat, bass, synth, vocal) and produces a stereo mixdown with per-channel gain curves, equal-power panning, and a crossfade between two channels. The pipeline also computes output statistics including RMS levels, peak detection, dynamic range, and an integrity checksum.

## Problem
The mixer is producing incorrect output. The stereo mix has wrong level balance, incorrect per-channel RMS measurements, and the output integrity checksum does not match expected values. Several specific symptoms have been observed:

### Observed Symptoms

1. **Stereo image is wrong**: The left/right balance does not match expected pan positions. Center-panned sources (kick, bass) should produce identical L/R contributions, but the output shows unequal distribution between channels.

2. **Per-channel RMS values are far too negative**: Channel RMS measurements in dBFS are approximately 2.3× lower than expected. For example, the kick channel shows around -54 dBFS when it should be around -23 dBFS. All channels exhibit this proportional error.

3. **Fade-out regions show increasing amplitude**: Channels configured with decreasing gain curves (fade-out) appear to get louder instead of quieter. The bass channel, which should fade from -1dB to -8dB, shows amplitude growth in the fade region.

4. **Dynamic range measurement is slightly off**: The computed dynamic range differs from the expected value by approximately 0.4 dB.

5. **Output RMS for right channel is wrong**: The right channel RMS is approximately -12.95 dBFS when it should be around -15.92 dBFS — a significant 3 dB difference.

6. **Integrity checksum mismatch**: The output checksum does not match the expected value, indicating the actual sample values or their processing order differs from the specification.

7. **Some RMS values fall outside valid dBFS range**: At least one channel's RMS measurement falls below -96 dBFS (the noise floor for 16-bit audio), which should not be possible for a channel with actual signal content.

## Architecture

```
mix_session.json → sample_gen.py → gain_stage.py → mix_engine.py → output_stage.py → mix_output.json
                   (load/validate)   (gain curves)   (pan + mix)     (stats/output)    mix_stats.json
```

### Files
- `mixer.py` — Entry point orchestrator (NO BUGS)
- `sample_gen.py` — Session loading and validation (NO BUGS)
- `mix_engine.py` — Core mixing: pan law, crossfade, clipping, channel summing
- `gain_stage.py` — Gain curve interpolation, dB conversion, envelope building
- `output_stage.py` — RMS computation, checksum generation, output formatting

### Session Config
The `mix_session.json` defines 6 channels with:
- Integer sample data (16-bit signed, ±32767)
- Per-channel gain curves (dB values at control point indices)
- Pan positions (-1.0 = full left, 0.0 = center, +1.0 = full right)
- A crossfade region between the synth and vocal channels (samples 50-150)

### Expected Output
- `mix_output.json`: Stereo sample arrays, per-channel RMS, peak value
- `mix_stats.json`: Output RMS (L/R), dynamic range, clipped count, checksum

## Constraints
- Python 3 standard library only (math, json, hashlib, struct)
- 16-bit signed audio: valid sample range is [-32768, 32767]
- All processing is single-pass, deterministic, no external dependencies

## Task
Identify and fix the bugs in `gain_stage.py`, `mix_engine.py`, and `output_stage.py` so that all 15 validation tests pass. The bugs are in the signal processing logic — not in I/O, formatting, or orchestration.

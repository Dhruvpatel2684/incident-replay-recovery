# Flow Control Repair — Debugging Task

## Overview

A network transport flow control simulation system replays recorded traffic traces through a sender/receiver protocol model. The system simulates congestion window management, acknowledgement processing, and receiver-side buffering across multiple scenarios including baseline transfers, segment loss recovery, and receiver buffer pressure.

## System Environment

- **Language**: Python 3.11
- **Runtime**: `/app/runtime/` (source, config, data, output)
- **Global system-wide tooling**: `uv` and `pytest` are available
- **Entry point**: `python3 -m runtime.run_flow`

## System Architecture

The implementation spans multiple packages:

- `/app/runtime/core/` — Protocol constants, sequence number arithmetic, congestion window state machine
- `/app/runtime/protocols/` — ACK tracking, simulation engine
- `/app/runtime/transport/` — Sender coordination, receiver model

## Observed Symptoms

The system produces output but exhibits the following anomalies:

- The sender transmits far more segments than the receiver can buffer, suggesting the send window is not properly constrained
- In loss scenarios, the same segment is retransmitted many more times than the protocol allows for a single loss event
- The receiver reports a negative advertised window in some scenarios, which should be impossible
- Buffer overflow occurs (buffer_used exceeds buffer_capacity) when the receiver should be throttling the sender
- Throughput efficiency is unrealistically high (~90%) when proper flow control should produce moderate efficiency (~74%)
- The congestion window grows without bound instead of being capped by protocol limits

## Expected Behavior (when fixed)

- 3 scenarios produce results with total_segments_sent=158, efficiency≈0.745
- Receiver advertised window is always non-negative
- Receiver buffer never exceeds its configured capacity
- Retransmissions are bounded (at most 3-4 for 2 segment losses)
- Baseline scenario has exactly 84 segments sent and 8 blocked

## Output Schema

### `/app/runtime/output/flow_summary.json`

| Field | Type | Description |
|-------|------|-------------|
| `scenarios_run` | integer | Number of trace scenarios executed |
| `total_segments_sent` | integer | Segments successfully transmitted |
| `total_segments_blocked` | integer | Send attempts blocked by window |
| `total_retransmissions` | integer | Retransmission events |
| `efficiency` | float | sent / (sent + blocked) ratio |

### `/app/runtime/output/scenario_results.json`

Array of per-scenario results with `sender_stats`, `receiver_stats`, counts.

## Key Files

| File | Purpose |
|------|---------|
| `/app/runtime/run_flow.py` | Entry point, runs all scenarios |
| `/app/runtime/core/constants.py` | Protocol constants |
| `/app/runtime/core/sequence.py` | Sequence number arithmetic |
| `/app/runtime/core/window.py` | Congestion window state machine |
| `/app/runtime/protocols/ack_tracker.py` | ACK processing and duplicate detection |
| `/app/runtime/protocols/flow_sim.py` | Simulation engine |
| `/app/runtime/transport/sender.py` | Sender-side coordination |
| `/app/runtime/transport/receiver.py` | Receiver model with buffer management |

## Your Task

Identify and fix the defects causing the observed anomalies. The bugs are spread across multiple modules and interact with each other through shared protocol state.

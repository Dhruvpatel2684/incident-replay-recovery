# Rate Limiter Repair — Debugging Task

## Overview

A multi-layer rate limiting system processes incoming HTTP request streams through a classification layer, then applies combined token bucket and sliding window enforcement with configurable policies. The system tracks per-stream throughput statistics and produces detailed decision logs.

## System Environment

- **Language**: Python 3.11
- **Runtime**: `/app/runtime/` (source, config, data, output)
- **Global system-wide tooling**: `uv` and `pytest` are available
- **Entry point**: `python3 -m runtime.run_limiter`

## Processing Stages

1. **Request Classification** — Each request is classified into a tier based on its URL path. Patterns are matched using prefix comparison after extracting the pattern from configuration. API requests go to the "api" tier, static assets and health checks are exempt from rate limiting.

2. **Rate Limit Enforcement** — Rate-limited requests must pass through both a token bucket and a sliding window limiter. In "strict" mode, a request is only allowed when BOTH limiters independently approve it.

3. **Token Bucket** — Starts at full capacity. Tokens are consumed one per request. Refill occurs lazily: elapsed time is divided by the refill interval to determine complete intervals, and each complete interval adds refill_rate tokens (capped at capacity).

4. **Sliding Window** — Tracks requests in time-granularity slots. The window looks back size_ms milliseconds. Active slots are those STRICTLY after the window start boundary up to and including the current slot. A request is allowed if the active count is below max_requests.

5. **Statistics** — Computes per-stream effective rates as allowed_count divided by elapsed time in seconds (milliseconds / 1000).

## Problem

The system processes all 75 requests but produces incorrect rate limiting behavior:

- Some request categories that should be exempt from rate limiting are not being recognized
- The enforcement is too permissive, allowing requests that should be denied
- Statistics report request rates that are off by an order of magnitude
- The token bucket appears to refill slightly too aggressively

## Expected Correct Output

When operating correctly:

- Health checks, static assets, and websocket requests are classified into their respective exempt tiers
- Strict enforcement (both limiters must approve) produces a significant denial rate (>40%) for API traffic
- Stream A (25 requests, 50ms spacing, all API) should pass completely (within bucket capacity + refills)
- Effective rates should be in the range of 1-25 requests per second (not 0.5-3.5)

## Output Schema

### `/app/runtime/output/decisions.json`

A JSON array of per-request decision objects:

| Field | Type | Description |
|-------|------|-------------|
| `req_id` | string | Request identifier |
| `path` | string | URL path of the request |
| `tier` | string | Classification tier assigned |
| `allowed` | boolean | Whether request was allowed |
| `reason` | string | Reason for decision |
| `timestamp_ms` | integer | Request timestamp in milliseconds |

### `/app/runtime/output/limiter_summary.json`

| Field | Type | Description |
|-------|------|-------------|
| `total_requests` | integer | Total requests processed |
| `total_allowed` | integer | Requests allowed through |
| `total_denied` | integer | Requests denied |
| `allow_rate` | float | Ratio of allowed to total |
| `per_tier` | object | Per-tier allow/deny counts |
| `per_stream` | object | Per-stream statistics |

Each stream in `per_stream`:

| Field | Type | Description |
|-------|------|-------------|
| `allowed` | integer | Allowed count for stream |
| `denied` | integer | Denied count for stream |
| `effective_rate` | float | Requests per second (allowed / elapsed_seconds) |

## Key Files

| File | Purpose |
|------|---------|
| `/app/runtime/run_limiter.py` | Main entry point orchestrating processing |
| `/app/runtime/classifier.py` | URL path classification into rate limit tiers |
| `/app/runtime/enforcer.py` | Combines multiple limiters with policy enforcement |
| `/app/runtime/bucket.py` | Token bucket rate limiter implementation |
| `/app/runtime/window.py` | Sliding window counter implementation |
| `/app/runtime/stats.py` | Statistics computation and aggregation |
| `/app/runtime/config.ini` | Configuration for all components |
| `/app/runtime/data/traffic_stream_a.json` | Stream A: 25 requests, 50ms spacing |
| `/app/runtime/data/traffic_stream_b.json` | Stream B: 25 requests, mixed paths, 100ms spacing |
| `/app/runtime/data/traffic_stream_c.json` | Stream C: 25 requests, 20ms burst spacing |
| `/app/runtime/output/decisions.json` | Generated decision log |
| `/app/runtime/output/limiter_summary.json` | Generated summary statistics |

## Your Task

Identify and fix defects in the runtime source files so that the system produces correct rate limiting behavior matching the expected characteristics described above. The defects span multiple modules and interact with each other.

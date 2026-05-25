# DNS Zone Resolver — Repair Task

## Overview

You are maintaining a **DNS Zone File Resolver** that loads BIND-format zone files, resolves batched DNS queries against them with CNAME chain following, wildcard matching, and TTL-based caching, then exports structured resolution results.

The resolver is deployed at `/app/runtime/` and consists of:

The runtime environment contains the required system-wide Python tooling and pytest installation.

- `/app/runtime/run_resolver.py` — orchestration entrypoint
- `/app/runtime/parser.py` — zone file parser with SOA serial tracking
- `/app/runtime/resolver.py` — core resolution logic (CNAME following, wildcard matching)
- `/app/runtime/cache.py` — TTL-based record cache with expiration
- `/app/runtime/exporter.py` — writes resolution results and integrity summary
- `/app/runtime/config/resolver.ini` — resolver settings (max CNAME depth, cache config, zone paths, last known serials)
- `/app/runtime/zones/example.com.zone` — primary zone file
- `/app/runtime/zones/internal.dev.zone` — secondary zone file
- `/app/runtime/queries/batch_queries.json` — input queries to resolve

## Observed Symptoms

Operations teams have reported several issues:

1. **Primary zone not loading** — The `example.com` zone appears to be skipped during startup. The parser logs indicate the zone serial is "not newer" than the last known value, but the zone file has clearly been updated. The SOA serial in the zone file is `10`, and the last known serial in config is `4294967290`. This suggests the serial has wrapped past the 32-bit unsigned boundary, and the comparison logic doesn't handle this correctly.

2. **Wildcard returning wrong results for exact names** — For names that have both an explicit record AND would match a wildcard pattern, the resolver returns the wildcard value instead of the exact record. For example, `app.internal.dev` has an explicit A record but resolves to the wildcard address.

3. **CNAME chain resolution fails at configured depth** — A 5-hop CNAME chain (`hop1` through `hop5`) should resolve to the final A record since `max_cname_depth` is configured as 5. Instead, the resolution returns SERVFAIL indicating the chain exceeded the allowed depth. The issue appears to be a boundary condition in the depth counter.

4. **MX queries through CNAME fail** — `mail.example.com` has a CNAME pointing to `mx-pool.example.com` which has both an A and MX record. MX queries for `mail.example.com` should follow the CNAME and return the MX record at the target, but the resolution fails because it looks for an MX record at intermediate CNAME targets rather than following to the final A/MX resolution.

5. **Cache entries never expire** — Records with explicit low TTL values (e.g., 60 seconds) remain in cache indefinitely. The TTL expiration check appears to use incorrect unit arithmetic, causing records to persist far longer than their declared lifetime.

## Your Task

Diagnose and repair the defects in the runtime code. After patching the runtime modules, the resolver must be re-executed to regenerate output artifacts. The integrity hash in the summary is computed from the results file at export time — if results change due to bug fixes but the resolver is not re-run, the stored hash will be stale.

**Constraints:**
- Only modify Python files under `/app/runtime/`
- Do not modify zone files, query files, or `resolver.ini`
- The resolver must produce correct output after repair

## Output Schema

### `/app/runtime/output/resolution_results.jsonl`

Each line is a JSON object:

```json
{
  "name": "string — queried domain name",
  "type": "string — query type (A, MX, AAAA, etc.)",
  "status": "string — NOERROR | NXDOMAIN | SERVFAIL",
  "answer": "string | null — resolved value or null for failures",
  "ttl": "integer — time-to-live in seconds",
  "chain": "array — CNAME resolution chain [{from, to}, ...]"
}
```

### `/app/runtime/output/resolution_summary.json`

```json
{
  "generated_at": "string — ISO-8601 UTC timestamp",
  "results_sha256": "string — SHA-256 hex digest of results file",
  "total_queries": "integer — number of queries processed",
  "resolved_count": "integer — queries with NOERROR status",
  "nxdomain_count": "integer — queries with NXDOMAIN status",
  "servfail_count": "integer — queries with SERVFAIL status",
  "zones_loaded": "object — per-zone metadata (serial, record_count, default_ttl)"
}
```

## Expected Behavior After Repair

- Both zones (`example.com` and `internal.dev`) load successfully regardless of serial wrap
- Exact DNS records take precedence over wildcard matches
- CNAME chains of exactly `max_cname_depth` hops resolve to the terminal record
- MX queries through CNAME indirection resolve correctly
- Cache TTL expiration uses correct second-based arithmetic
- The integrity hash matches the actual results file content

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

1. **Primary zone not loading** — The `example.com` zone is skipped during startup. The parser compares the zone's SOA serial against a "last known" value to detect updates, but the comparison appears to fail under certain numeric conditions. Inspecting the config shows the last known serial is very large while the zone file serial is small.

2. **Incorrect resolution for names with exact records** — Some domain names that have explicit records in the zone file are resolving to unexpected IP addresses. The returned values match what a wildcard would produce rather than the specific record defined for that name.

3. **CNAME chain resolution boundary failure** — A CNAME chain that should be within the configured depth limit is returning SERVFAIL instead of resolving to the terminal A record. The chain length exactly matches the configured `max_cname_depth` value.

4. **MX queries through CNAME indirection fail** — When an MX query hits a name that has a CNAME record, the resolution doesn't properly follow through to the target's MX record.

5. **Cache entries persist indefinitely** — Records that should expire based on their TTL values remain cached far beyond their declared lifetime. The expiration arithmetic appears to use incorrect units.

## Your Task

Diagnose and repair the defects in the runtime code. Your repair script must patch the source files and then re-execute the resolver to produce corrected output. The test suite validates the output files directly — it does not re-run the resolver itself.

**Constraints:**
- Only modify Python files under `/app/runtime/`
- Do not modify zone files, query files, or `resolver.ini`
- The resolver must be re-executed after patching to regenerate output
- The integrity hash in the summary must match the results file content

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

- Both zones load successfully regardless of serial number magnitude
- Exact DNS records take precedence over wildcard matches (per standard DNS resolution rules)
- CNAME chains of exactly `max_cname_depth` hops resolve to the terminal record
- MX queries through CNAME indirection resolve correctly
- Cache TTL expiration uses correct second-based arithmetic
- The integrity hash matches the actual results file content

# Firewall Rule Compiler — Debug Task

## Overview

You are given a firewall rule compiler that translates high-level security policy declarations into ordered iptables-style rule chains. The compiler reads policy definitions and service group mappings, resolves named references, compiles an evaluation-ordered chain, and exports the result.

The system has system-wide Python tooling and pytest available for running verification.

## Architecture

The compiler pipeline consists of the following modules:

- `/app/runtime/parser.py` — Reads and validates security policy JSON declarations
- `/app/runtime/resolver.py` — Resolves named service groups to concrete IP addresses and port specifications
- `/app/runtime/cidr.py` — CIDR/subnet utility functions (host count, containment, specificity)
- `/app/runtime/compiler.py` — Core compilation: priority ordering, conflict detection, and resolution
- `/app/runtime/exporter.py` — Formats and writes the compiled rule chain to output files
- `/app/runtime/run_compiler.py` — Orchestration entry point

## Input Data

- `/app/runtime/policies/security_policy.json` — Eight firewall policy declarations with priorities, actions, source/destination groups, and port specifications
- `/app/runtime/groups/service_groups.json` — Named service groups mapping to CIDR addresses

## Output

The compiler produces two output files:

### `/app/runtime/output/compiled_rules.txt`

One rule per line in iptables-style format:
```
CHAIN INPUT
1: ACTION PROTOCOL SOURCE -> DESTINATION ports=PORTS # RULE_ID [pri=PRIORITY]
2: ...
```

Rules are numbered sequentially by evaluation order. Lower priority numbers indicate higher precedence and should appear earlier in the chain.

### `/app/runtime/output/compilation_summary.json`

```json
{
  "total_rules": <int>,
  "conflicts_resolved": <int>,
  "chain_type": "INPUT",
  "rules": [{"position": <int>, "id": "<str>", "action": "<str>", "priority": <int>}]
}
```

## Observed Issues

The compiler produces output, but the rule chain is incorrect in several ways:

1. **Rule ordering** — Rules appear in unexpected evaluation order. Priority ordering determines evaluation sequence; the rule with the lowest priority number should be evaluated first in the chain.

2. **Subnet calculations** — CIDR specificity calculations seem inverted for certain CIDR ranges. A /32 (single host) should be the most specific, while a /8 should be the least specific. The host count for a given prefix length directly impacts tie-breaking between competing rules.

3. **Conflict resolution** — Conflicting rules resolve in favor of permissiveness when security policy requires deny-by-default. Security-first conflict resolution means that when two rules of equal priority overlap in scope but differ in action, the DENY rule should take precedence.

4. **Port specification handling** — Multi-port specifications appear to inflate port match counts. A port list like "80,443" represents exactly two ports, not a continuous range between those values.

## Running the Compiler

```bash
cd /app
python3 -m runtime.run_compiler
```

## Testing

The test suite validates output files directly — it does not re-run the compiler. After patching, the compiler must be re-executed to regenerate output.

```bash
cd /tests
python3 -m pytest test_rules.py -v
```

## Constraints

- All source files are in `/app/runtime/`
- Output must be written to `/app/runtime/output/`
- Python standard library only (no external packages beyond pytest for testing)
- The input policy and group data are correct — do not modify them
- The exporter formatting logic is correct — do not modify it

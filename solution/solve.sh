#!/bin/bash
# Parse application.log, extract ERROR entries, compute statistics,
# and write a JSON report to /app/output.json

python3 -c "
import json

with open('/app/data/application.log', 'r') as f:
    lines = f.read().strip().split('\n')

errors = []
for line in lines:
    parts = line.split(None, 3)
    if len(parts) >= 3 and parts[1] == 'ERROR':
        errors.append({'timestamp': parts[0], 'module': parts[2]})

counts = {}
for e in errors:
    counts[e['module']] = counts.get(e['module'], 0) + 1

sorted_counts = dict(sorted(counts.items()))

max_count = max(counts.values())
worst = sorted(m for m, c in counts.items() if c == max_count)[0]

result = {
    'total_errors': len(errors),
    'errors_per_module': sorted_counts,
    'worst_module': worst,
    'first_error_timestamp': errors[0]['timestamp'],
    'last_error_timestamp': errors[-1]['timestamp'],
}

with open('/app/output.json', 'w') as f:
    json.dump(result, f, indent=2)
"

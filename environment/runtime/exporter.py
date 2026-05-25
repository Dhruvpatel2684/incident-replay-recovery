"""
Rule exporter module.
Writes compiled rule chains to output files in iptables-style format.
"""

import json
import os


def export_rules(compiled_chain, output_dir):
    """Export compiled rules to output files."""
    os.makedirs(output_dir, exist_ok=True)

    rules_path = os.path.join(output_dir, "compiled_rules.txt")
    summary_path = os.path.join(output_dir, "compilation_summary.json")

    write_rules_file(compiled_chain, rules_path)
    write_summary(compiled_chain, summary_path)

    return rules_path, summary_path


def format_rule_line(rule):
    """Format a single rule as an iptables-style text line."""
    position = rule['chain_position']
    action = rule['action']
    protocol = rule['protocol']

    # Format source IPs
    source = ','.join(rule['source_ips'])

    # Format destination IPs
    destination = ','.join(rule['destination_ips'])

    # Format ports
    if rule['ports'] == 'any':
        ports_str = 'any'
    else:
        ports_str = rule['ports']

    rule_id = rule['id']
    priority = rule['priority']

    return f"{position}: {action} {protocol} {source} -> {destination} ports={ports_str} # {rule_id} [pri={priority}]"


def write_rules_file(compiled_chain, output_path):
    """Write all compiled rules to the output file."""
    with open(output_path, 'w') as f:
        f.write("CHAIN INPUT\n")
        for rule in compiled_chain:
            line = format_rule_line(rule)
            f.write(line + "\n")


def write_summary(compiled_chain, output_path):
    """Write compilation summary as JSON."""
    conflicts_resolved = 0
    if compiled_chain:
        conflicts_resolved = compiled_chain[0].get('_conflicts_resolved', 0)

    summary = {
        "total_rules": len(compiled_chain),
        "conflicts_resolved": conflicts_resolved,
        "chain_type": "INPUT",
        "rules": []
    }

    for rule in compiled_chain:
        summary["rules"].append({
            "position": rule['chain_position'],
            "id": rule['id'],
            "action": rule['action'],
            "priority": rule['priority']
        })

    with open(output_path, 'w') as f:
        json.dump(summary, f, indent=2)

"""
Test suite for the firewall rule compiler.
Validates the compiled output against expected correctness criteria.
"""

import json
import os
import re
import sys

import pytest

# Paths to compiler output
RULES_PATH = "/app/runtime/output/compiled_rules.txt"
SUMMARY_PATH = "/app/runtime/output/compilation_summary.json"

# Add runtime to path for importing cidr module
sys.path.insert(0, "/app")


def load_rules():
    """Load compiled rules from output file."""
    assert os.path.exists(RULES_PATH), f"Compiled rules file not found: {RULES_PATH}"
    with open(RULES_PATH, 'r') as f:
        lines = f.readlines()
    # Skip the CHAIN header line
    rule_lines = [l.strip() for l in lines if l.strip() and not l.startswith("CHAIN")]
    return rule_lines


def load_summary():
    """Load compilation summary."""
    assert os.path.exists(SUMMARY_PATH), f"Summary file not found: {SUMMARY_PATH}"
    with open(SUMMARY_PATH, 'r') as f:
        return json.load(f)


def parse_rule_line(line):
    """Parse a rule line into components."""
    # Format: N: ACTION PROTO SOURCE -> DEST ports=PORTS # ID [pri=N]
    match = re.match(
        r'^(\d+): (ALLOW|DENY) (\w+) (.+?) -> (.+?) ports=(.+?) # (.+?) \[pri=(\d+)\]$',
        line
    )
    if not match:
        return None
    return {
        'position': int(match.group(1)),
        'action': match.group(2),
        'protocol': match.group(3),
        'source': match.group(4),
        'destination': match.group(5),
        'ports': match.group(6),
        'id': match.group(7),
        'priority': int(match.group(8))
    }


class TestRuleCount:
    """Tests for correct rule count in output."""

    def test_rule_count(self):
        """Compiled output should have the correct number of rules (8 policies)."""
        rules = load_rules()
        assert len(rules) == 8, f"Expected 8 rules, got {len(rules)}"


class TestRuleOrdering:
    """Tests for correct priority-based ordering."""

    def test_first_rule_is_highest_priority(self):
        """First rule should have the lowest priority number (highest precedence)."""
        rules = load_rules()
        first = parse_rule_line(rules[0])
        assert first is not None, f"Could not parse first rule: {rules[0]}"
        assert first['priority'] == 30, \
            f"First rule should have priority 30 (allow-app-to-db), got priority {first['priority']} ({first['id']})"

    def test_last_rule_is_default_deny(self):
        """Last rule should be the default-deny (priority 999)."""
        rules = load_rules()
        last = parse_rule_line(rules[-1])
        assert last is not None, f"Could not parse last rule: {rules[-1]}"
        assert last['id'] == "default-deny", \
            f"Last rule should be default-deny, got {last['id']}"
        assert last['priority'] == 999

    def test_specific_allow_before_general_deny(self):
        """allow-app-to-db (pri=30) must appear before deny-internal-to-db (pri=50)."""
        rules = load_rules()
        app_to_db_pos = None
        deny_internal_pos = None
        for rule_line in rules:
            parsed = parse_rule_line(rule_line)
            if parsed and parsed['id'] == 'allow-app-to-db':
                app_to_db_pos = parsed['position']
            if parsed and parsed['id'] == 'deny-internal-to-db':
                deny_internal_pos = parsed['position']

        assert app_to_db_pos is not None, "allow-app-to-db rule not found"
        assert deny_internal_pos is not None, "deny-internal-to-db rule not found"
        assert app_to_db_pos < deny_internal_pos, \
            f"allow-app-to-db (pos {app_to_db_pos}) should be before deny-internal-to-db (pos {deny_internal_pos})"

    def test_bastion_ssh_before_deny_ssh(self):
        """allow-bastion-ssh (pri=150) must appear before deny-all-ssh (pri=200)."""
        rules = load_rules()
        bastion_pos = None
        deny_ssh_pos = None
        for rule_line in rules:
            parsed = parse_rule_line(rule_line)
            if parsed and parsed['id'] == 'allow-bastion-ssh':
                bastion_pos = parsed['position']
            if parsed and parsed['id'] == 'deny-all-ssh':
                deny_ssh_pos = parsed['position']

        assert bastion_pos is not None, "allow-bastion-ssh rule not found"
        assert deny_ssh_pos is not None, "deny-all-ssh rule not found"
        assert bastion_pos < deny_ssh_pos, \
            f"allow-bastion-ssh (pos {bastion_pos}) should be before deny-all-ssh (pos {deny_ssh_pos})"


class TestConflictResolution:
    """Tests for correct conflict resolution behavior."""

    def test_deny_before_allow_same_priority(self):
        """When rules share priority and overlap, DENY should appear before ALLOW."""
        rules = load_rules()
        # deny-external-admin and allow-monitoring both have priority 80
        # deny-external-admin should come BEFORE allow-monitoring in the chain
        deny_admin_pos = None
        allow_monitor_pos = None
        for rule_line in rules:
            parsed = parse_rule_line(rule_line)
            if parsed and parsed['id'] == 'deny-external-admin':
                deny_admin_pos = parsed['position']
            if parsed and parsed['id'] == 'allow-monitoring':
                allow_monitor_pos = parsed['position']

        assert deny_admin_pos is not None, "deny-external-admin not found in output"
        assert allow_monitor_pos is not None, "allow-monitoring not found in output"
        assert deny_admin_pos < allow_monitor_pos, \
            f"deny-external-admin (pos {deny_admin_pos}) should be before allow-monitoring (pos {allow_monitor_pos}) at same priority"


class TestPortHandling:
    """Tests for correct port specification handling."""

    def test_port_list_not_range(self):
        """Ports '80,443' should resolve as 2 ports, not 364 (range 80-443)."""
        from runtime.resolver import resolve_ports
        ports = resolve_ports("80,443")
        assert len(ports) == 2, f"'80,443' should be 2 ports, got {len(ports)}: {ports}"
        assert 80 in ports and 443 in ports, f"Expected [80, 443], got {ports}"


class TestCIDRCalculations:
    """Tests for correct CIDR host count calculations."""

    def test_cidr_host_count_32(self):
        """/32 (single host) should have 1 address."""
        from runtime.cidr import get_host_count
        assert get_host_count("10.0.1.10/32") == 1, \
            f"/32 should be 1 host, got {get_host_count('10.0.1.10/32')}"

    def test_cidr_host_count_24(self):
        """/24 should have 256 addresses."""
        from runtime.cidr import get_host_count
        assert get_host_count("10.0.20.0/24") == 256, \
            f"/24 should be 256 hosts, got {get_host_count('10.0.20.0/24')}"

    def test_cidr_host_count_8(self):
        """/8 should have 16777216 addresses."""
        from runtime.cidr import get_host_count
        assert get_host_count("10.0.0.0/8") == 16777216, \
            f"/8 should be 16777216 hosts, got {get_host_count('10.0.0.0/8')}"


class TestGroupResolution:
    """Tests for correct service group resolution."""

    def test_all_groups_resolved(self):
        """No unresolved group names should appear in the compiled output."""
        rules = load_rules()
        group_names = ["web-servers", "db-servers", "app-servers", "bastion-hosts",
                       "monitoring-network", "internal-network", "all-servers"]
        for rule_line in rules:
            for group in group_names:
                assert group not in rule_line, \
                    f"Unresolved group '{group}' found in rule: {rule_line}"

    def test_web_servers_resolved(self):
        """web-servers group should be expanded to its IP addresses."""
        rules = load_rules()
        web_rule = None
        for rule_line in rules:
            parsed = parse_rule_line(rule_line)
            if parsed and parsed['id'] == 'allow-web-public':
                web_rule = parsed
                break

        assert web_rule is not None, "allow-web-public rule not found"
        # Should contain the web server IPs
        assert "10.0.1.10/32" in web_rule['destination'] or \
               "10.0.1.10" in web_rule['destination'], \
            f"web-servers not resolved in destination: {web_rule['destination']}"


class TestRulePresence:
    """Tests for presence of expected rules in output."""

    def test_monitoring_rule_present(self):
        """allow-monitoring rule should be in the compiled output."""
        rules = load_rules()
        found = False
        for rule_line in rules:
            parsed = parse_rule_line(rule_line)
            if parsed and parsed['id'] == 'allow-monitoring':
                found = True
                break
        assert found, "allow-monitoring rule not found in compiled output"

    def test_deny_external_admin_present(self):
        """deny-external-admin rule should be in the compiled output."""
        rules = load_rules()
        found = False
        for rule_line in rules:
            parsed = parse_rule_line(rule_line)
            if parsed and parsed['id'] == 'deny-external-admin':
                found = True
                break
        assert found, "deny-external-admin rule not found in compiled output"


class TestOutputFormat:
    """Tests for output format correctness."""

    def test_output_format_valid(self):
        """Every rule line should match the expected format."""
        rules = load_rules()
        pattern = re.compile(
            r'^\d+: (ALLOW|DENY) \w+ .+ -> .+ ports=.+ # .+ \[pri=\d+\]$'
        )
        for rule_line in rules:
            assert pattern.match(rule_line), \
                f"Rule line does not match expected format: {rule_line}"


class TestSummary:
    """Tests for compilation summary correctness."""

    def test_summary_has_rule_count(self):
        """Summary should report the correct total rule count."""
        summary = load_summary()
        rules = load_rules()
        assert summary['total_rules'] == len(rules), \
            f"Summary reports {summary['total_rules']} rules, but output has {len(rules)}"

    def test_summary_has_conflict_count(self):
        """Summary should report the number of resolved conflicts."""
        summary = load_summary()
        assert 'conflicts_resolved' in summary, \
            "Summary missing 'conflicts_resolved' field"
        assert isinstance(summary['conflicts_resolved'], int), \
            "conflicts_resolved should be an integer"


class TestNoDuplicates:
    """Tests for absence of duplicate rules."""

    def test_no_duplicate_rules(self):
        """No two rules should have the same ID in the output."""
        rules = load_rules()
        seen_ids = set()
        for rule_line in rules:
            parsed = parse_rule_line(rule_line)
            assert parsed is not None, f"Could not parse rule: {rule_line}"
            assert parsed['id'] not in seen_ids, \
                f"Duplicate rule ID found: {parsed['id']}"
            seen_ids.add(parsed['id'])

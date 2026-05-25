"""
Core firewall rule compiler.
Takes resolved policies and produces ordered, de-conflicted rule chains.
"""

from .cidr import get_specificity, cidr_contains


def compile_rules(resolved_policies):
    """
    Compile resolved policies into an ordered rule chain.
    
    Rules are ordered by priority (lower number = higher priority = evaluated first).
    When priorities are equal, DENY rules should come before ALLOW rules (security-first).
    Within the same action at equal priority, more specific source CIDRs take precedence.
    """
    # Step 1: Sort rules by priority and resolve intra-priority conflicts
    ordered = order_rules(resolved_policies)

    # Step 2: Count conflicts for summary reporting
    conflict_count = count_conflicts(resolved_policies)
    if ordered:
        ordered[0]['_conflicts_resolved'] = conflict_count

    # Step 3: Assign chain positions
    chain = assign_positions(ordered)

    return chain


def order_rules(policies):
    """
    Order rules for the final chain.
    Primary sort: priority number (lower = evaluated first).
    Secondary sort (within same priority): conflict resolution ordering.
    """
    # Group by priority
    priority_groups = {}
    for rule in policies:
        pri = rule['priority']
        if pri not in priority_groups:
            priority_groups[pri] = []
        priority_groups[pri].append(rule)

    # BUG: Sorts priority keys DESCENDING (reverse=True puts 999 first)
    # Should sort ASCENDING so lowest priority number comes first
    sorted_priorities = sorted(priority_groups.keys(), reverse=True)

    result = []
    for pri in sorted_priorities:
        group = priority_groups[pri]
        if len(group) > 1:
            # Multiple rules at same priority — apply conflict resolution ordering
            reordered = resolve_priority_group(group)
            result.extend(reordered)
        else:
            result.extend(group)

    return result


def resolve_priority_group(group):
    """
    Resolve ordering within a group of rules that share the same priority.
    Security-first: DENY before ALLOW for overlapping rules.
    Specificity: more specific source CIDR first within same action.
    """
    # BUG: Puts ALLOW before DENY (should be DENY before ALLOW)
    allow_rules = [r for r in group if r['action'] == 'ALLOW']
    deny_rules = [r for r in group if r['action'] == 'DENY']

    # Sort each sub-group by specificity (more specific source first)
    allow_rules.sort(key=lambda r: max(get_specificity(cidr) for cidr in r['source_ips']), reverse=True)
    deny_rules.sort(key=lambda r: max(get_specificity(cidr) for cidr in r['source_ips']), reverse=True)

    # BUG: Places ALLOW rules first, then DENY
    # Should place DENY first for security-first ordering
    return allow_rules + deny_rules


def count_conflicts(policies):
    """Count the number of same-priority overlapping rule pairs."""
    conflicts = 0
    for i, rule_a in enumerate(policies):
        for j, rule_b in enumerate(policies[i + 1:], start=i + 1):
            if rules_overlap(rule_a, rule_b):
                conflicts += 1
    return conflicts


def rules_overlap(rule_a, rule_b):
    """
    Determine if two rules overlap in scope.
    Rules overlap if they share the same priority and have intersecting
    source/destination/port scope.
    """
    if rule_a['priority'] != rule_b['priority']:
        return False

    # Check port overlap
    ports_a = set(str(p) for p in rule_a['resolved_ports'])
    ports_b = set(str(p) for p in rule_b['resolved_ports'])
    if not ports_a.intersection(ports_b) and 'any' not in ports_a and 'any' not in ports_b:
        return False

    # Check source/destination overlap via CIDR containment
    src_overlap = any(
        cidr_contains(a, b) or cidr_contains(b, a)
        for a in rule_a['source_ips']
        for b in rule_b['source_ips']
    )

    dst_overlap = any(
        cidr_contains(a, b) or cidr_contains(b, a)
        for a in rule_a['destination_ips']
        for b in rule_b['destination_ips']
    )

    return src_overlap or dst_overlap


def assign_positions(rules):
    """Assign sequential chain positions to rules."""
    for idx, rule in enumerate(rules, start=1):
        rule['chain_position'] = idx
    return rules

"""
Firewall rule compiler orchestration.
Loads policies, resolves groups, compiles rules, and exports output.
"""

import os
import sys

# Ensure runtime package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from runtime.parser import load_policies
from runtime.resolver import load_groups, resolve_policy
from runtime.compiler import compile_rules
from runtime.exporter import export_rules


def main():
    """Main compiler orchestration."""
    base_dir = os.path.dirname(os.path.abspath(__file__))

    # Paths
    policy_path = os.path.join(base_dir, "policies", "security_policy.json")
    groups_path = os.path.join(base_dir, "groups", "service_groups.json")
    output_dir = os.path.join(base_dir, "output")

    print("[compiler] Loading security policies...")
    policies = load_policies(policy_path)
    print(f"[compiler] Loaded {len(policies)} policies")

    print("[compiler] Loading service groups...")
    groups = load_groups(groups_path)
    print(f"[compiler] Loaded {len(groups)} service groups")

    print("[compiler] Resolving group references...")
    resolved_policies = []
    for policy in policies:
        resolved = resolve_policy(policy, groups)
        resolved_policies.append(resolved)

    print("[compiler] Compiling rule chain...")
    compiled_chain = compile_rules(resolved_policies)

    print("[compiler] Exporting compiled rules...")
    rules_path, summary_path = export_rules(compiled_chain, output_dir)

    print(f"[compiler] Output written:")
    print(f"  Rules: {rules_path}")
    print(f"  Summary: {summary_path}")
    print(f"[compiler] Done. {len(compiled_chain)} rules in final chain.")


if __name__ == "__main__":
    main()

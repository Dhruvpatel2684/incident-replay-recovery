#!/usr/bin/env python3
"""
Repairs DNS zone resolver runtime defects.
"""

import os
import sys
import subprocess

RUNTIME_DIR = "/app/runtime"


def fix_parser():
    """Fix RFC 1982 serial number comparison."""
    path = os.path.join(RUNTIME_DIR, "parser.py")
    with open(path) as f:
        content = f.read()

    # Replace simple > comparison with RFC 1982 serial arithmetic.
    # Serial s1 is "greater than" s2 when (s1 - s2) interpreted as
    # signed 32-bit is positive (i.e., the difference mod 2^32 < 2^31).
    old_check = "if not (soa_serial > last_known[zone_name]):"
    new_check = "if not _serial_gt(soa_serial, last_known[zone_name]):"

    content = content.replace(old_check, new_check)

    # Add the helper function after the imports
    helper = '''

def _serial_gt(s1, s2):
    """RFC 1982 serial number arithmetic: s1 > s2 with 32-bit wrapping."""
    diff = (s1 - s2) & 0xFFFFFFFF
    return 0 < diff < 0x80000000

'''
    # Insert after the logger line
    content = content.replace(
        'logger = logging.getLogger("dns.parser")\n',
        'logger = logging.getLogger("dns.parser")\n' + helper
    )

    with open(path, "w") as f:
        f.write(content)


def fix_resolver():
    """Fix CNAME depth, wildcard precedence, and qtype propagation."""
    path = os.path.join(RUNTIME_DIR, "resolver.py")
    with open(path) as f:
        content = f.read()

    # Fix 1: CNAME depth off-by-one: <= should be <
    content = content.replace(
        "while depth <= max_cname_depth:",
        "while depth < max_cname_depth:"
    )

    # Fix 2: Wildcard precedence — exact match must come first in _find_record.
    old_find = '''    for zone_name, records in zone_records.items():
        wildcard_name = "*." + ".".join(name.split(".")[1:]) if "." in name else None

        for rec in records:
            if rec["name"] == wildcard_name and rec["type"] == qtype:
                return rec

        for rec in records:
            if rec["name"] == name and rec["type"] == qtype:
                return rec
            if rec["name"] == name and rec["type"] == "CNAME":
                return rec

    return None'''

    new_find = '''    for zone_name, records in zone_records.items():
        # Exact match first (RFC 4592 precedence)
        for rec in records:
            if rec["name"] == name and rec["type"] == qtype:
                return rec
            if rec["name"] == name and rec["type"] == "CNAME":
                return rec

        # Then wildcard
        wildcard_name = "*." + ".".join(name.split(".")[1:]) if "." in name else None
        if wildcard_name:
            for rec in records:
                if rec["name"] == wildcard_name and rec["type"] == qtype:
                    return rec

    return None'''

    content = content.replace(old_find, new_find)

    # Fix 5: After first CNAME hop, look up target with "A" type for intermediate hops.
    old_cname_section = '''        if record is not None and record["type"] == "CNAME":
            chain.append({"from": current_name, "to": record["rdata"]})
            current_name = record["rdata"]
            depth += 1
            continue'''

    new_cname_section = '''        if record is not None and record["type"] == "CNAME":
            chain.append({"from": current_name, "to": record["rdata"]})
            current_name = record["rdata"]
            depth += 1
            # After first CNAME hop, look for A record at intermediate targets
            record = _find_record(current_name, qtype, zone_records)
            if record is None:
                record = _find_record(current_name, "A", zone_records)
                if record is not None and record["type"] != "CNAME":
                    return {
                        "name": name,
                        "type": qtype,
                        "status": "NOERROR",
                        "answer": record["rdata"],
                        "ttl": record["ttl"],
                        "chain": chain,
                    }
            continue'''

    content = content.replace(old_cname_section, new_cname_section)

    with open(path, "w") as f:
        f.write(content)


def fix_cache():
    """Fix TTL expiration — remove erroneous * 60 multiplier."""
    path = os.path.join(RUNTIME_DIR, "cache.py")
    with open(path) as f:
        content = f.read()

    content = content.replace(
        'if elapsed > entry["ttl"] * 60:',
        'if elapsed > entry["ttl"]:'
    )

    with open(path, "w") as f:
        f.write(content)


def rerun():
    """Re-run resolver with fixed code."""
    result = subprocess.run(
        [sys.executable, os.path.join(RUNTIME_DIR, "run_resolver.py")],
        capture_output=True, text=True, cwd="/app"
    )
    if result.returncode != 0:
        print(f"ERROR: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    print(result.stderr, end="")


def main():
    print("applying dns resolver repairs...")
    fix_parser()
    print("  [fixed] parser: RFC 1982 serial number arithmetic")
    fix_resolver()
    print("  [fixed] resolver: CNAME depth, wildcard precedence, qtype propagation")
    fix_cache()
    print("  [fixed] cache: TTL expiration without 60x multiplier")

    # Clear stale output
    output_dir = os.path.join(RUNTIME_DIR, "output")
    for f in os.listdir(output_dir) if os.path.isdir(output_dir) else []:
        fpath = os.path.join(output_dir, f)
        if os.path.isfile(fpath):
            os.remove(fpath)

    rerun()
    print("repair complete")


if __name__ == "__main__":
    main()

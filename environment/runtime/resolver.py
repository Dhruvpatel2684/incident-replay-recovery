"""
Core DNS resolution logic.
"""

import logging

logger = logging.getLogger("dns.resolver")


def resolve_query(name, qtype, zone_records, cache, max_cname_depth):
    cached = cache.get(name, qtype)
    if cached is not None:
        return cached
    result = _resolve(name, qtype, zone_records, max_cname_depth)
    if result["status"] == "NOERROR":
        cache.put(name, qtype, result, result.get("ttl", 300))
    return result


def _resolve(name, qtype, zone_records, max_cname_depth):
    chain = []
    current_name = name
    depth = 0

    while depth <= max_cname_depth:
        record = _find_record(current_name, qtype, zone_records)

        if record is not None and record["type"] != "CNAME":
            return {"name": name, "type": qtype, "status": "NOERROR", "answer": record["rdata"], "ttl": record["ttl"], "chain": chain}

        if record is not None and record["type"] == "CNAME":
            chain.append({"from": current_name, "to": record["rdata"]})
            current_name = record["rdata"]
            depth += 1
            continue

        wildcard_record = _find_wildcard(current_name, qtype, zone_records)
        if wildcard_record is not None:
            return {"name": name, "type": qtype, "status": "NOERROR", "answer": wildcard_record["rdata"], "ttl": wildcard_record["ttl"], "chain": chain}

        return {"name": name, "type": qtype, "status": "NXDOMAIN", "answer": None, "ttl": 0, "chain": chain}

    return {"name": name, "type": qtype, "status": "SERVFAIL", "answer": None, "ttl": 0, "chain": chain, "error": "CNAME chain too deep"}


def _find_record(name, qtype, zone_records):
    for zone_name, records in zone_records.items():
        wildcard_name = "*." + ".".join(name.split(".")[1:]) if "." in name else None

        for rec in records:
            if rec["name"] == wildcard_name and rec["type"] == qtype:
                return rec

        for rec in records:
            if rec["name"] == name and rec["type"] == qtype:
                return rec
            if rec["name"] == name and rec["type"] == "CNAME":
                return rec

    return None


def _find_wildcard(name, qtype, zone_records):
    if "." not in name:
        return None
    wildcard_name = "*." + ".".join(name.split(".")[1:])
    for zone_name, records in zone_records.items():
        for rec in records:
            if rec["name"] == wildcard_name and rec["type"] == qtype:
                return rec
    return None

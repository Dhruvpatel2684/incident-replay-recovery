"""
DNS zone file parser.
"""

import logging
import os

logger = logging.getLogger("dns.parser")


def parse_zone_file(filepath):
    records = []
    default_ttl = 300
    with open(filepath) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith(";"):
                continue
            if line.startswith("$TTL"):
                default_ttl = int(line.split()[1])
                continue
            parts = line.split()
            if len(parts) < 4:
                continue
            if parts[1].isdigit():
                name, ttl, rclass, rtype = parts[0], int(parts[1]), parts[2], parts[3]
                rdata = " ".join(parts[4:])
            elif parts[1] == "IN":
                name, ttl, rclass, rtype = parts[0], default_ttl, parts[1], parts[2]
                rdata = " ".join(parts[3:])
            else:
                continue
            records.append({"name": name.rstrip("."), "ttl": ttl, "class": rclass, "type": rtype, "rdata": rdata.rstrip(".") if rtype in ("CNAME", "NS", "MX") else rdata})
    return records, default_ttl


def load_zones(config):
    zone_dir = config.get("zones", "zone_dir", fallback="/app/runtime/zones")
    last_known_raw = config.get("zones", "last_known_serials", fallback="")
    last_known = {}
    if last_known_raw:
        for entry in last_known_raw.split(","):
            if ":" in entry:
                zone_name, serial_str = entry.split(":", 1)
                last_known[zone_name.strip()] = int(serial_str.strip())

    all_records = {}
    zone_metadata = {}

    for fname in sorted(os.listdir(zone_dir)):
        if not fname.endswith(".zone"):
            continue
        zone_name = fname.replace(".zone", "")
        filepath = os.path.join(zone_dir, fname)
        records, default_ttl = parse_zone_file(filepath)

        soa_serial = None
        for rec in records:
            if rec["type"] == "SOA":
                soa_parts = rec["rdata"].split()
                if len(soa_parts) >= 3:
                    soa_serial = int(soa_parts[2])
                break

        if zone_name in last_known and soa_serial is not None:
            if not (soa_serial > last_known[zone_name]):
                logger.warning(f"zone {zone_name}: serial {soa_serial} not newer than {last_known[zone_name]}, skipping")
                continue

        all_records[zone_name] = records
        zone_metadata[zone_name] = {"serial": soa_serial, "default_ttl": default_ttl, "record_count": len(records)}
        logger.info(f"loaded zone {zone_name}: {len(records)} records, serial {soa_serial}")

    return all_records, zone_metadata

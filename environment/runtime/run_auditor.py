"""
Certificate Chain Auditor - Orchestration Module
Coordinates the loading, chain building, validation, revocation checking,
and report export for the certificate audit process.
"""

import os
import sys
import configparser

# Add runtime to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from chain import load_certificates, build_all_chains
from validator import validate_cert
from revocation import check_revocation_status
from exporter import build_report_entry, write_report, write_summary


def load_config(config_path):
    """Load the auditor configuration from INI file."""
    config = configparser.ConfigParser()
    config.read(config_path)
    return config


def main():
    """Main orchestration function for the certificate chain auditor."""
    # Determine paths
    runtime_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(runtime_dir, 'config', 'auditor.ini')
    cert_path = os.path.join(runtime_dir, 'certs', 'chain_bundle.json')

    # Load configuration
    config = load_config(config_path)
    reference_time = config.get('audit', 'reference_time')
    required_leaf_key_usage = int(config.get('audit', 'required_leaf_key_usage'))
    max_chain_depth = int(config.get('audit', 'max_chain_depth'))
    output_path = config.get('output', 'output_path')
    report_filename = config.get('output', 'report_filename')
    summary_filename = config.get('output', 'summary_filename')

    print(f"[AUDITOR] Loading certificates from {cert_path}")
    certs = load_certificates(cert_path)
    print(f"[AUDITOR] Loaded {len(certs)} certificates")

    # Build trust chains
    print(f"[AUDITOR] Building trust chains (max_depth={max_chain_depth})")
    chains = build_all_chains(certs, max_chain_depth)

    # Validate and check revocation for each certificate
    print(f"[AUDITOR] Validating certificates (reference_time={reference_time})")
    entries = []
    for cert in certs:
        chain = chains.get(cert["serial"], [cert])
        validation_result = validate_cert(cert, reference_time, required_leaf_key_usage)
        revocation_result = check_revocation_status(cert, chain)

        entry = build_report_entry(cert, chain, validation_result, revocation_result)
        entries.append(entry)

    # Write output files
    print(f"[AUDITOR] Writing report to {output_path}/{report_filename}")
    report_path = write_report(entries, output_path, report_filename)

    print(f"[AUDITOR] Writing summary to {output_path}/{summary_filename}")
    write_summary(entries, output_path, summary_filename, report_path)

    print(f"[AUDITOR] Audit complete. {len(entries)} certificates processed.")
    return entries


if __name__ == "__main__":
    main()

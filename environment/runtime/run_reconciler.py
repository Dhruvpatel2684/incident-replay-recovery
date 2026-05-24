#!/usr/bin/env python3
"""
Configuration Drift Reconciler — main orchestration entrypoint.

Loads manifest declarations and live node state, detects configuration drift,
generates remediation plans, computes compliance scores, and exports reports.
"""

import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from loader import load_manifests, load_live_state
from comparator import load_config, detect_drift
from remediation import generate_plan
from compliance import compute_compliance
from exporter import export_report

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S"
)
logger = logging.getLogger("drift.orchestrator")


def main():
    runtime_dir = os.path.dirname(os.path.abspath(__file__))
    manifest_dir = os.path.join(runtime_dir, "manifests")
    state_dir = os.path.join(runtime_dir, "live_state")

    logger.info("configuration drift reconciler starting")

    config = load_config()

    manifest_nodes = load_manifests(manifest_dir)
    live_nodes = load_live_state(state_dir)

    drift_results = detect_drift(manifest_nodes, live_nodes, config)

    remediation_plans = generate_plan(drift_results)

    compliance_summary = compute_compliance(drift_results, config)

    export_report(drift_results, remediation_plans, compliance_summary, config)

    logger.info("reconciliation complete")


if __name__ == "__main__":
    main()

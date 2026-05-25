"""Orchestration script: runs the verifier and writes integrity report."""

import os
import sys
import json

# Ensure runtime directory is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from verifier import run_full_verification

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")


def main():
    """Run verification and write report."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    results = run_full_verification()
    
    report = {
        "overall": "pass" if all(
            v["status"] == "pass" for v in results.values()
        ) else "fail",
        "checks": results
    }
    
    report_path = os.path.join(OUTPUT_DIR, "integrity_report.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    
    print(f"Integrity report written to {report_path}")
    print(f"Overall status: {report['overall']}")
    for check_name, check_result in results.items():
        status = check_result['status']
        error_count = len(check_result['errors'])
        print(f"  {check_name}: {status}" + (f" ({error_count} errors)" if error_count else ""))
    
    return 0 if report["overall"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())

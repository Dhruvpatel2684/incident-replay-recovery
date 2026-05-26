#!/bin/bash
# Repair the corrupted OCI manifest by computing correct digests
# and ordering, then re-run the verifier
cd /app
python3 /solution/repair_manifest.py

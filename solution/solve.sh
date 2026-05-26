#!/bin/bash
# Repair the geospatial event correlation engine by patching
# source defects then re-running the correlator
cd /app
python3 /solution/repair_correlator.py

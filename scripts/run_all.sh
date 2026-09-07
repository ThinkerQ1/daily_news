#!/bin/bash
set -e

cd "$(dirname "$0")/.."
source .venv/bin/activate

echo "[dailyNews] openclaw collect start"
python3 scripts/openclaw_collect.py || true

echo "[dailyNews] run daily start"
python3 scripts/run_daily.py

echo "[dailyNews] done"

#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python scripts/install_rea.py
python -m playwright install chromium || true
printf 'Vishnu installed with REA 6.5.0. Run: . .venv/bin/activate && python -m app.main\n'

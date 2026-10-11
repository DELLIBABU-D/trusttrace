#!/usr/bin/env sh
# TrustTrace one-command start (macOS/Linux). First run installs the Python packages.
cd "$(dirname "$0")" || exit 1
PY=${PYTHON:-python3}
if [ ! -f backend/data/.installed ]; then
  echo "Installing Python packages (first run only)..."
  "$PY" -m pip install -r backend/requirements.txt || { echo "pip install failed. See PROJECT_STATUS.md, Troubleshooting."; exit 1; }
  mkdir -p backend/data && touch backend/data/.installed
fi
"$PY" backend/manage.py doctor
exec "$PY" serve.py

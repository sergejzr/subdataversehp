#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${REPO_DIR}/.venv"

python3 -m venv "${VENV}"
"${VENV}/bin/python" -m pip install --upgrade pip

if [ -f "${REPO_DIR}/requirements.txt" ]; then
  "${VENV}/bin/pip" install -r "${REPO_DIR}/requirements.txt"
fi

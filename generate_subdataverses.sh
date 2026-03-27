#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="${REPO_DIR}/venv"

cd "${REPO_DIR}"

if [ ! -x "${VENV}/bin/python" ]; then
  python3 -m venv "${VENV}"
fi

if [ -f "${REPO_DIR}/requirements.txt" ]; then
  "${VENV}/bin/pip" install -r "${REPO_DIR}/requirements.txt"
fi

if [ -z "${1:-}" ]; then
  echo "Usage: $0 <API_TOKEN>"
  exit 1
fi

API_TOKEN="$1"

"${VENV}/bin/python" create_and_publish_dataverses.py \
  --server_name localhost:8080 \
  --api_token "${API_TOKEN}" \
  --csv_path homepage_template/conf/unis.csv \
  --parent_alias :root \
  --fallback_contact_email forschungsdaten@uni-bonn.de

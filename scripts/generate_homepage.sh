#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${REPO_DIR}/.venv"
OUTPUT_DIR="${REPO_DIR}/output"
OUTPUT_HTML="${OUTPUT_DIR}/at/index.html"

cd "${REPO_DIR}"

if [ ! -x "${VENV}/bin/python" ]; then
  python3 -m venv "${VENV}"
fi

"${VENV}/bin/python" -m pip install --upgrade pip

if [ -f "${REPO_DIR}/requirements.txt" ]; then
  "${VENV}/bin/pip" install -r "${REPO_DIR}/requirements.txt"
fi

mkdir -p "${OUTPUT_DIR}/at"

"${VENV}/bin/python" "${REPO_DIR}/src/homepage_builder/renderjinja.py" \
  --output_html "${OUTPUT_HTML}" \
  --jinja_template_dir "${REPO_DIR}/templates/base" \
  --jinja_file "main-dataverse-homepage-jinja.html" \
  --server_name localhost




if [ ! -f "${OUTPUT_HTML}" ]; then
  echo "Homepage generation failed: ${OUTPUT_HTML} was not created." >&2
  exit 1
fi

#curl -X PUT -d "${OUTPUT_HTML}" http://localhost:8080/api/admin/settings/:HomePageCustomizationFile

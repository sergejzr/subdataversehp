#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_NAME="$(basename "${ROOT}")"
PARENT_DIR="$(dirname "${ROOT}")"
STAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP="${PARENT_DIR}/${PROJECT_NAME}_backup_before_restructure_${STAMP}.tar.gz"

echo "==> Project root: ${ROOT}"
echo "==> Creating backup outside project: ${BACKUP}"

tar -czf "${BACKUP}" \
  --exclude="${PROJECT_NAME}/.git" \
  --exclude="${PROJECT_NAME}/.venv" \
  --exclude="${PROJECT_NAME}/venv" \
  --exclude="${PROJECT_NAME}/homepagebuilder" \
  --exclude="${PROJECT_NAME}/output" \
  --exclude="${PROJECT_NAME}"/*_backup_before_restructure_*.tar.gz \
  -C "${PARENT_DIR}" "${PROJECT_NAME}"

echo "==> Backup created"

move_if_exists() {
  local src="$1"
  local dst="$2"
  if [ -e "${src}" ]; then
    echo "   moving ${src} -> ${dst}"
    mkdir -p "$(dirname "${dst}")"
    mv "${src}" "${dst}"
  fi
}

remove_if_exists() {
  local path="$1"
  if [ -e "${path}" ]; then
    echo "   removing ${path}"
    rm -rf "${path}"
  fi
}

append_if_missing() {
  local line="$1"
  if ! grep -qxF "${line}" "${ROOT}/.gitignore" 2>/dev/null; then
    echo "${line}" >> "${ROOT}/.gitignore"
  fi
}

echo "==> Creating new structure"
mkdir -p "${ROOT}/scripts"
mkdir -p "${ROOT}/src/homepage_builder"
mkdir -p "${ROOT}/config"
mkdir -p "${ROOT}/templates/base"
mkdir -p "${ROOT}/templates/assets"
mkdir -p "${ROOT}/templates/universities"
mkdir -p "${ROOT}/output/generated"
mkdir -p "${ROOT}/output/homepage"

echo "==> Moving shell scripts"
move_if_exists "${ROOT}/generate_homepage.sh" "${ROOT}/scripts/generate_homepage.sh"
move_if_exists "${ROOT}/generate_subdataverses.sh" "${ROOT}/scripts/generate_subdataverses.sh"
move_if_exists "${ROOT}/create_context.sh" "${ROOT}/scripts/create_context.sh"
move_if_exists "${ROOT}/install_environment.sh" "${ROOT}/scripts/install_environment.sh"

echo "==> Moving Python files into src/homepage_builder"
move_if_exists "${ROOT}/renderjinja.py" "${ROOT}/src/homepage_builder/renderjinja.py"
move_if_exists "${ROOT}/create_and_publish_dataverses.py" "${ROOT}/src/homepage_builder/create_and_publish_dataverses.py"
move_if_exists "${ROOT}/DataverseAPI.py" "${ROOT}/src/homepage_builder/dataverse_api.py"
move_if_exists "${ROOT}/DataverseTemplate.py" "${ROOT}/src/homepage_builder/dataverse_template.py"
move_if_exists "${ROOT}/SVG_Manipulator.py" "${ROOT}/src/homepage_builder/svg_manipulator.py"
move_if_exists "${ROOT}/svg_manipulator.py" "${ROOT}/src/homepage_builder/svg_manipulator.py"

if [ ! -f "${ROOT}/src/homepage_builder/__init__.py" ]; then
  touch "${ROOT}/src/homepage_builder/__init__.py"
fi

echo "==> Moving config files"
move_if_exists "${ROOT}/check_git.ini" "${ROOT}/config/check_git.ini"
move_if_exists "${ROOT}/update_from_git.ini" "${ROOT}/config/update_from_git.ini"
move_if_exists "${ROOT}/homepage_template/conf/unis.csv" "${ROOT}/config/unis.csv"

echo "==> Moving template base files"
move_if_exists "${ROOT}/homepage_template/custom-homepage-jinja.html" "${ROOT}/templates/base/custom-homepage-jinja.html"
move_if_exists "${ROOT}/homepage_template/uni-homepage-jinja.html" "${ROOT}/templates/base/uni-homepage-jinja.html"

echo "==> Moving university-specific templates"
if [ -d "${ROOT}/homepage_template/unis" ]; then
  shopt -s nullglob
  for uni_dir in "${ROOT}"/homepage_template/unis/*; do
    uni_name="$(basename "${uni_dir}")"
    move_if_exists "${uni_dir}" "${ROOT}/templates/universities/${uni_name}"
  done
  shopt -u nullglob
fi

echo "==> Moving shared assets"
if [ -d "${ROOT}/homepage_template/webcontent/pagedata" ]; then
  move_if_exists "${ROOT}/homepage_template/webcontent/pagedata" "${ROOT}/templates/assets/pagedata"
fi

if [ -d "${ROOT}/pagedata" ]; then
  if [ ! -d "${ROOT}/templates/assets/pagedata" ]; then
    move_if_exists "${ROOT}/pagedata" "${ROOT}/templates/assets/pagedata"
  else
    echo "   duplicate pagedata found at root; removing old root copy"
    rm -rf "${ROOT}/pagedata"
  fi
fi

echo "==> Moving generated output"
move_if_exists "${ROOT}/generated-homepage.html" "${ROOT}/output/generated/generated-homepage.html"
move_if_exists "${ROOT}/homepage_output" "${ROOT}/output/homepage"

echo "==> Removing old unused folders"
remove_if_exists "${ROOT}/homepage_template/cache"
remove_if_exists "${ROOT}/homepage_template/conf"
remove_if_exists "${ROOT}/homepage_template/webcontent"

if [ -d "${ROOT}/homepage_template/unis" ] && [ -z "$(find "${ROOT}/homepage_template/unis" -mindepth 1 -print -quit)" ]; then
  rmdir "${ROOT}/homepage_template/unis"
fi

if [ -d "${ROOT}/homepage_template" ] && [ -z "$(find "${ROOT}/homepage_template" -mindepth 1 -print -quit)" ]; then
  rmdir "${ROOT}/homepage_template"
fi

echo "==> Removing legacy virtualenv folders"
remove_if_exists "${ROOT}/venv"
remove_if_exists "${ROOT}/homepagebuilder"

echo "==> Rewriting shell scripts for the new structure"

cat > "${ROOT}/scripts/install_environment.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${REPO_DIR}/.venv"

python3 -m venv "${VENV}"
"${VENV}/bin/python" -m pip install --upgrade pip

if [ -f "${REPO_DIR}/requirements.txt" ]; then
  "${VENV}/bin/pip" install -r "${REPO_DIR}/requirements.txt"
fi
EOF
chmod +x "${ROOT}/scripts/install_environment.sh"

cat > "${ROOT}/scripts/generate_homepage.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${REPO_DIR}/.venv"
OUTPUT_DIR="${REPO_DIR}/output/homepage"
OUTPUT_HTML="${OUTPUT_DIR}/at/index.html"

cd "${REPO_DIR}"

if [ ! -x "${VENV}/bin/python" ]; then
  python3 -m venv "${VENV}"
fi

"${VENV}/bin/python" -m pip install --upgrade pip

if [ -f "${REPO_DIR}/requirements.txt" ]; then
  "${VENV}/bin/pip" install -r "${REPO_DIR}/requirements.txt"
fi

rm -rf "${OUTPUT_DIR}"
mkdir -p "${OUTPUT_DIR}"

"${VENV}/bin/python" "${REPO_DIR}/src/homepage_builder/renderjinja.py" \
  --output_html "${OUTPUT_HTML}" \
  --jinja_template_dir "${REPO_DIR}/templates/base" \
  --jinja_file "custom-homepage-jinja.html" \
  --server_name localhost

if [ ! -f "${OUTPUT_HTML}" ]; then
  echo "Homepage generation failed: ${OUTPUT_HTML} was not created." >&2
  exit 1
fi
EOF
chmod +x "${ROOT}/scripts/generate_homepage.sh"

cat > "${ROOT}/scripts/generate_subdataverses.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${REPO_DIR}/.venv"

cd "${REPO_DIR}"

if [ ! -x "${VENV}/bin/python" ]; then
  python3 -m venv "${VENV}"
fi

"${VENV}/bin/python" -m pip install --upgrade pip

if [ -f "${REPO_DIR}/requirements.txt" ]; then
  "${VENV}/bin/pip" install -r "${REPO_DIR}/requirements.txt"
fi

if [ -z "${1:-}" ]; then
  echo "Usage: $0 <API_TOKEN>"
  exit 1
fi

API_TOKEN="$1"

"${VENV}/bin/python" "${REPO_DIR}/src/homepage_builder/create_and_publish_dataverses.py" \
  --server_name localhost:8080 \
  --api_token "${API_TOKEN}" \
  --csv_path "${REPO_DIR}/config/unis.csv" \
  --parent_alias :root \
  --fallback_contact_email forschungsdaten@uni-bonn.de
EOF
chmod +x "${ROOT}/scripts/generate_subdataverses.sh"

cat > "${ROOT}/scripts/create_context.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_DIR}"

find . -type f \( \
  -name "*.yml" -o \
  -name "*.yaml" -o \
  -name "*.cfg" -o \
  -name "*.sh" -o \
  -name "*.j2" -o \
  -name "*.txt" -o \
  -name "*.py" -o \
  -name "*.ini" -o \
  -name "*.md" -o \
  -name "*.html" -o \
  -name "*.css" -o \
  -name "*.js" -o \
  -name "*.csv" -o \
  -name ".gitignore" \
\) ! -name "context.txt" \
   ! -path "./.git/*" \
   ! -path "./node_modules/*" \
   ! -path "./files/*" \
   ! -path "./repository/*" \
   ! -path "./.venv/*" \
   ! -path "./output/*" \
| sort | while read -r f; do
  echo "===== FILE: $f ====="
  echo
  cat "$f"
  echo
done > context.txt
EOF
chmod +x "${ROOT}/scripts/create_context.sh"

echo "==> Ensuring .gitignore has generated entries"
touch "${ROOT}/.gitignore"

append_if_missing ""
append_if_missing "# Virtual environments"
append_if_missing ".venv/"
append_if_missing "venv/"
append_if_missing "homepagebuilder/"
append_if_missing ""
append_if_missing "# Generated output"
append_if_missing "output/"
append_if_missing "context.txt"
append_if_missing "find.txt"
append_if_missing "*_backup_before_restructure_*.tar.gz"

echo "==> Final tree preview"
find "${ROOT}" -maxdepth 3 | sort

cat <<'EOF'

Restructure finished.

Run next:
  bash scripts/install_environment.sh
  bash scripts/generate_homepage.sh
  bash scripts/generate_subdataverses.sh <API_TOKEN>

Important:
- This script moves files and rewrites shell entrypoints.
- It does not patch Python imports or hardcoded relative paths inside Python source.
- If your Python code still refers to old paths such as:
    homepage_template/...
    pagedata/...
    homepage_output/...
  then those references must be updated manually to the new paths:
    templates/base/...
    templates/universities/...
    templates/assets/pagedata/...
    output/homepage/...
    config/unis.csv
EOF


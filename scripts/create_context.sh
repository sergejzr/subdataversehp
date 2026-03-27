#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_DIR}"

find . -type f \( \
  -name "*.py" -o \
  -name "*.sh" -o \
  -name "*.html" -o \
  -name "*.css" -o \
  -name "*.js" -o \
  -name "*.ini" -o \
  -name "*.cfg" -o \
  -name "*.md" -o \
  -name "*.csv" -o \
  -name ".gitignore" \
\) \
   ! -name "context.txt" \
   ! -name "find.txt" \
   ! -path "./.git/*" \
   ! -path "./.venv/*" \
   ! -path "./venv/*" \
   ! -path "./output/*" \
   ! -path "./templates/assets/*" \
   ! -path "./templates/assets/pagedata/*" \
   ! -path "./homepage_template/webcontent/*" \
   ! -path "./homepage_template/cache/*" \
   ! -path "./pagedata/*" \
   ! -path "./node_modules/*" \
   ! -path "./__pycache__/*" \
| sort | while read -r f; do
  echo "===== FILE: $f ====="
  echo
  cat "$f"
  echo
done > context.txt

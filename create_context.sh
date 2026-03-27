find . -type f \( \
  -name "*.yml" -o \
  -name "*.yaml" -o \
  -name "*.cfg" -o \
  -name "*.sh" -o \
  -name "*.j2" -o \
  -name "*.txt" \
  -name "*.py" \
  -name "*.ini" \
  -name "*.md" \
  -name "*.html" \
  -name "*.css" \
  -name "*.js" \
  -name "*.csv" \
  -name "*.gitignore" \
\) ! -name "context.txt" \
   ! -path "./.git/*" \
   ! -path "./node_modules/*" \
   ! -path "./files/*" \
   ! -path "./repository/*" \
   ! -path "./.venv/*" \
| sort | while read -r f; do
  echo "===== FILE: $f ====="
  echo
  cat "$f"
  echo
done > context.txt

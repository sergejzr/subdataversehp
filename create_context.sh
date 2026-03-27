find . -type f \( \
  -name "*.yml" -o \
  -name "*.yaml" -o \
  -name "*.cfg" -o \
  -name "*.sh" -o \
  -name "*.j2" -o \
  -name "*.txt" \
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

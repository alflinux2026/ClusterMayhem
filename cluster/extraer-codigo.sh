OUT="$(basename "$PWD")_codigo_$(date +%Y%m%d_%H%M%S).log"
find . \
  -path '*/.*' -prune -o \
  -path '*/__pycache__' -prune -o \
  -type f ! -name '*.pyc' ! -name '*.log' ! -name '*.md' -size +0c \
  -exec sh -c '
    for f do
      printf "\n\n\n===== %s =====\n" "$f"
      cat "$f"
    done
  ' sh {} + > "$OUT"
echo "$OUT"

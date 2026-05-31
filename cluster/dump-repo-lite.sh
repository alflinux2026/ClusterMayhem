
#!/usr/bin/env bash
set -euo pipefail

STAMP="$(date +%Y%m%d_%H%M%S)"

# ------------------------------------------------------------
# Fuente manual
# ------------------------------------------------------------

CORE_WHITELIST="core-files-lite.txt"

# ------------------------------------------------------------
# Outputs "latest"
# ------------------------------------------------------------

CORE_LIST="last_core_files-lite.txt"
CORE_CODE="last_code_core-lite.code"
CORE_HEADER="header_last_code_core-lite.code"
SUMMARY_FILE="core_summary-lite.md"





# ------------------------------------------------------------
# Carpeta snapshots
# ------------------------------------------------------------

SNAPSHOT_DIR="dump-repo-lite"

mkdir -p "$SNAPSHOT_DIR"

# ------------------------------------------------------------
# Versiones históricas
# ------------------------------------------------------------

CORE_LIST_TS="${SNAPSHOT_DIR}/core_files-lite_${STAMP}.txt"

CORE_CODE_TS="${SNAPSHOT_DIR}/last_code_core-lite_${STAMP}.code"

CORE_HEADER_TS="${SNAPSHOT_DIR}/header_last_code_core-lite_${STAMP}.code"

SUMMARY_FILE_TS="${SNAPSHOT_DIR}/core_summary-lite_${STAMP}.md"







python3 - "$CORE_WHITELIST" "$CORE_LIST" "$SUMMARY_FILE" <<'PY'
import sys
from pathlib import Path

whitelist_file = Path(sys.argv[1]).resolve()
core_list = Path(sys.argv[2]).resolve()
summary_file = Path(sys.argv[3]).resolve()

repo = Path.cwd().resolve()

if not whitelist_file.exists():
    raise SystemExit(
        f"ERROR: no existe {whitelist_file}"
    )

# ------------------------------------------------------------
# Leer whitelist
# ------------------------------------------------------------

raw_lines = whitelist_file.read_text(
    encoding="utf-8"
).splitlines()

core_files = []

for line in raw_lines:
    line = line.strip()

    if not line:
        continue

    if line.startswith("#"):
        continue

    core_files.append(line)

# ------------------------------------------------------------
# Validar existencia
# ------------------------------------------------------------

missing = []

for f in core_files:
    path = repo / f.replace("./", "", 1)

    if not path.exists():
        missing.append(f)

if missing:
    print("ERROR: archivos inexistentes:")

    for m in missing:
        print(" -", m)

    raise SystemExit(1)

# ------------------------------------------------------------
# Snapshot de lista
# ------------------------------------------------------------

core_list.write_text(
    "\n".join(core_files) + "\n",
    encoding="utf-8"
)

# ------------------------------------------------------------
# Summary
# ------------------------------------------------------------

with summary_file.open("w", encoding="utf-8") as f:
    f.write("# Core bundle summary\n\n")

    f.write("## Fuente\n\n")
    f.write(f"- `{whitelist_file.name}`\n\n")

    f.write("## Métricas\n\n")
    f.write(
        f"- Total archivos core: "
        f"**{len(core_files)}**\n\n"
    )

    f.write("## Archivos incluidos\n\n")

    for path in core_files:
        f.write(f"- `{path}`\n")

    f.write("\n")

    f.write("## Nota\n\n")
    f.write(
        "El bundle se construye exclusivamente "
        "a partir de la whitelist cerrada.\n"
    )
PY

build_bundle() {
  local list_file="$1"
  local out_file="$2"

  : > "$out_file"

  while IFS= read -r f || [ -n "$f" ]; do
    [ -z "$f" ] && continue
    [ ! -f "$f" ] && continue

    printf '\n\n\n===== %s =====\n' "$f" >> "$out_file"

    nl -ba -w4 -s': ' "$f" >> "$out_file"

  done < "$list_file"
}

build_header() {
  local in_file="$1"
  local out_file="$2"

  {
    echo "=== FILES ==="

    grep -n -E '^===== .*\.py =====$' \
      "$in_file" || true

    echo
    echo "=== FILES/IMPORTS ==="


awk '
  /^===== .*\.py =====$/ {
    in_py = 1
    print ""
    print $0
    next
  }

  /^===== / {
    in_py = 0
    next
  }

  in_py && /^[[:space:]]*[0-9]+: / {

    line = $0

    sub(/^[[:space:]]*[0-9]+: /, "", line)

    if (line ~ /^(import |from .+ import )/) {
      print $0
    }
  }
' "$in_file"

  } > "$out_file"
}

# ------------------------------------------------------------
# Construcción
# ------------------------------------------------------------

build_bundle "$CORE_LIST" "$CORE_CODE"

build_header "$CORE_CODE" "$CORE_HEADER"

# ------------------------------------------------------------
# Snapshots históricos
# ------------------------------------------------------------

cp "$CORE_LIST" "$CORE_LIST_TS"
cp "$CORE_CODE" "$CORE_CODE_TS"
cp "$CORE_HEADER" "$CORE_HEADER_TS"
cp "$SUMMARY_FILE" "$SUMMARY_FILE_TS"

# ------------------------------------------------------------
# Output
# ------------------------------------------------------------

printf '%s\n' "$CORE_LIST"
printf '%s\n' "$CORE_CODE"
printf '%s\n' "$CORE_HEADER"
printf '%s\n' "$SUMMARY_FILE"



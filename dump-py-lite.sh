#!/usr/bin/env bash
set -euo pipefail

STAMP="$(date +%Y%m%d_%H%M%S)"

# ============================================================
# SOURCE
# ============================================================

CORE_WHITELIST="core-files-lite.txt"

# ============================================================
# OUTPUT DIRS
# ============================================================

BASE_DUMP_DIR="dump"
SNAPSHOT_DIR="$BASE_DUMP_DIR/py_lite-dump"

mkdir -p "$BASE_DUMP_DIR"
mkdir -p "$SNAPSHOT_DIR"

# ============================================================
# LATEST OUTPUTS
# ============================================================

CORE_LIST="$BASE_DUMP_DIR/py_lite-last_core_files.txt"
CORE_CODE="$BASE_DUMP_DIR/py_lite-last_code_core.code"
CORE_HEADER="$BASE_DUMP_DIR/py_lite-header_last_code_core.code"
SUMMARY_FILE="$BASE_DUMP_DIR/py_lite-core_summary.md"

# ============================================================
# TIMESTAMP OUTPUTS
# ============================================================

CORE_LIST_TS="${SNAPSHOT_DIR}/core_files-lite_${STAMP}.txt"
CORE_CODE_TS="${SNAPSHOT_DIR}/last_code_core-lite_${STAMP}.code"
CORE_HEADER_TS="${SNAPSHOT_DIR}/header_last_code_core-lite_${STAMP}.code"
SUMMARY_FILE_TS="${SNAPSHOT_DIR}/core_summary-lite_${STAMP}.md"

# ============================================================
# PYTHON VALIDATION + SUMMARY
# ============================================================

python3 - "$CORE_WHITELIST" "$CORE_LIST" "$SUMMARY_FILE" <<'PY'
import sys
from pathlib import Path

whitelist_file = Path(sys.argv[1]).resolve()
core_list = Path(sys.argv[2]).resolve()
summary_file = Path(sys.argv[3]).resolve()

repo = Path.cwd().resolve()

if not whitelist_file.exists():
    raise SystemExit(f"ERROR: no existe {whitelist_file}")

raw_lines = whitelist_file.read_text(encoding="utf-8").splitlines()

core_files = []
for line in raw_lines:
    line = line.strip()
    if not line or line.startswith("#"):
        continue
    core_files.append(line)

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

core_list.write_text("\n".join(core_files) + "\n", encoding="utf-8")

with summary_file.open("w", encoding="utf-8") as f:
    f.write("# Core bundle summary (lite)\n\n")
    f.write("## Fuente\n\n")
    f.write(f"- `{whitelist_file.name}`\n\n")

    f.write("## Métricas\n\n")
    f.write(f"- Total archivos core: **{len(core_files)}**\n\n")

    f.write("## Archivos incluidos\n\n")
    for path in core_files:
        f.write(f"- `{path}`\n")

    f.write("\n## Nota\n\n")
    f.write("Bundle basado exclusivamente en whitelist.\n")
PY

# ============================================================
# HELPERS
# ============================================================

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
    grep -n -E '^===== .*\.py =====$' "$in_file" || true

    echo
    echo "=== FILES/IMPORTS/DEFS/@APP ==="
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

        if (line ~ /^[[:space:]]*import[[:space:]]+/ ||
            line ~ /^[[:space:]]*from[[:space:]]+.+[[:space:]]+import[[:space:]]+/)
          print $0

        if (line ~ /^[[:space:]]*(async[[:space:]]+)?def[[:space:]]+/)
          print $0

        if (line ~ /^[[:space:]]*class[[:space:]]+/)
          print $0

        if (line ~ /^[[:space:]]*@app\.(get|post|put|delete|patch|options|head)[[:space:]]*\(/)
          print $0
      }
    ' "$in_file"
  } > "$out_file"
}

# ============================================================
# BUILD
# ============================================================

build_bundle "$CORE_LIST" "$CORE_CODE"
build_header "$CORE_CODE" "$CORE_HEADER"

# ============================================================
# SNAPSHOTS
# ============================================================

cp "$CORE_LIST" "$CORE_LIST_TS"
cp "$CORE_CODE" "$CORE_CODE_TS"
cp "$CORE_HEADER" "$CORE_HEADER_TS"
cp "$SUMMARY_FILE" "$SUMMARY_FILE_TS"



# ============================================================
# SPLIT OUTPUT FILE
# ============================================================

split_file() {

    local INPUT_FILE="$1"
    local TARGET_SIZE=800

    local TOTAL_LINES
    TOTAL_LINES=$(wc -l < "$INPUT_FILE")

    if [ "$TOTAL_LINES" -le "$TARGET_SIZE" ]; then
        return
    fi

    local NUM_PARTS
    NUM_PARTS=$(( (TOTAL_LINES + TARGET_SIZE - 1) / TARGET_SIZE ))

    local LINES_PER_PART
    LINES_PER_PART=$(( (TOTAL_LINES + NUM_PARTS - 1) / NUM_PARTS ))

    local BASE_NAME
    BASE_NAME="${INPUT_FILE%.*}"

    local SOURCE_FILE
    SOURCE_FILE=$(basename "$INPUT_FILE")

    local REASSEMBLY_ID
    REASSEMBLY_ID="${SOURCE_FILE%.*}"

    rm -f "${BASE_NAME}"_part_*.code

    split \
        -l "$LINES_PER_PART" \
        --numeric-suffixes=1 \
        --suffix-length=3 \
        --additional-suffix=.code \
        "$INPUT_FILE" \
        "${BASE_NAME}_part_"

    local PART_FILES=("${BASE_NAME}"_part_*.code)

    for PART_FILE in "${PART_FILES[@]}"; do

        local PART_NUM
        PART_NUM=$(
            basename "$PART_FILE" \
            | sed -E 's/.*_part_([0-9]+)\.code/\1/'
        )

        local PREV_PART="NONE"
        local NEXT_PART="NONE"

        if [ "$PART_NUM" -gt 1 ]; then
            PREV_PART=$(printf "%03d" $((10#$PART_NUM - 1)))
        fi

        if [ "$PART_NUM" -lt "$NUM_PARTS" ]; then
            NEXT_PART=$(printf "%03d" $((10#$PART_NUM + 1)))
        fi

        local CONTENT_LINES
        CONTENT_LINES=$(wc -l < "$PART_FILE")

        local TMP_FILE="${PART_FILE}.tmp"

        {
            echo "########################################################################"
            echo "# MAYHEM FILE FRAGMENT"
            echo "########################################################################"
            echo "#"
            echo "# REASSEMBLY_ID    : ${REASSEMBLY_ID}"
            echo "# SOURCE_FILE      : ${SOURCE_FILE}"
            echo "# GENERATED_AT     : ${STAMP}"
            echo "#"
            echo "# REASSEMBLY_ORDER : ${PART_NUM}/$(printf "%03d" "$NUM_PARTS")"
            echo "# PART_NUMBER      : ${PART_NUM}"
            echo "# TOTAL_PARTS      : $(printf "%03d" "$NUM_PARTS")"
            echo "#"
            echo "# PREVIOUS_PART    : ${PREV_PART}"
            echo "# NEXT_PART        : ${NEXT_PART}"
            echo "#"
            echo "# CONTENT_LINES    : ${CONTENT_LINES}"
            echo "#"
            echo "# IMPORTANT:"
            echo "# This fragment is part of a larger file."
            echo "# Preserve exact order during reconstruction."
            echo "#"
            echo "########################################################################"
            echo "# FILE_FRAGMENT_BEGIN"
            echo "########################################################################"
            echo

            cat "$PART_FILE"

            echo
            echo "########################################################################"
            echo "# FILE_FRAGMENT_END"
            echo "########################################################################"
            echo "#"
            echo "# REASSEMBLY_ID    : ${REASSEMBLY_ID}"
            echo "# REASSEMBLY_ORDER : ${PART_NUM}/$(printf "%03d" "$NUM_PARTS")"
            echo "#"
            echo "########################################################################"

        } > "$TMP_FILE"

        mv "$TMP_FILE" "$PART_FILE"

    done

    echo "   -> Split: $INPUT_FILE"
    echo "      Lines       : $TOTAL_LINES"
    echo "      Parts       : $NUM_PARTS"
    echo "      Lines/part  : $LINES_PER_PART"
}


split_file "$CORE_LIST"
split_file "$CORE_CODE"
split_file "$CORE_HEADER"
split_file "$SUMMARY_FILE"


# ============================================================
# OUTPUT
# ============================================================

printf '%s\n' "$CORE_LIST"
printf '%s\n' "$CORE_CODE"
printf '%s\n' "$CORE_HEADER"
printf '%s\n' "$SUMMARY_FILE"

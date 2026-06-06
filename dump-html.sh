#!/usr/bin/env bash
set -euo pipefail

STAMP="$(date +%Y%m%d_%H%M%S)"

ROOT="./frontend"

# ============================================================
# OUTPUT DIRS
# ============================================================

BASE_DUMP_DIR="dump"
SNAPSHOT_DIR="$BASE_DUMP_DIR/html-dump"

mkdir -p "$SNAPSHOT_DIR"
mkdir -p "$BASE_DUMP_DIR"


# ============================================================
# OUTPUT FILES
# ============================================================

STAMP_FILE="$SNAPSHOT_DIR/html-dump_${STAMP}.code"
LATEST_FILE="$BASE_DUMP_DIR/html-last_dump.code"

# ============================================================
# SOURCE FILES
# ============================================================

JS_DIR="$ROOT/js"
CSS_DIR="$ROOT/css"
HTML_FILE="$ROOT/index.html"

echo "Generating FULL EXPORT..."

# ============================================================
# 1. BASE HTML (limpio de imports externos)
# ============================================================

awk '
BEGIN { skip=0 }
{
  if ($0 ~ /<script src=/) next
  if ($0 ~ /<link rel="stylesheet"/) next
  if ($0 ~ /<script src="\//) next
  print
}
' "$HTML_FILE" > "$STAMP_FILE"

# ============================================================
# 2. CSS BUNDLE
# ============================================================

echo "" >> "$STAMP_FILE"
echo "<!-- ================= CSS BUNDLE ================= -->" >> "$STAMP_FILE"
echo "<style>" >> "$STAMP_FILE"

if [ -d "$CSS_DIR" ]; then
  while IFS= read -r f; do
    [ -f "$f" ] || continue

    echo "" >> "$STAMP_FILE"
    echo "/* ===== FILE: $f ===== */" >> "$STAMP_FILE"
    cat "$f" >> "$STAMP_FILE"
  done < <(find "$CSS_DIR" -name "*.css" | sort)
fi

echo "</style>" >> "$STAMP_FILE"

# ============================================================
# 3. JS BUNDLE (orden controlado)
# ============================================================

echo "" >> "$STAMP_FILE"
echo "<!-- ================= JS BUNDLE ================= -->" >> "$STAMP_FILE"
echo "<script>" >> "$STAMP_FILE"

FILES=(
  "$JS_DIR/api.js"
  "$JS_DIR/map.js"
  "$JS_DIR/utils.js"
  "$JS_DIR/tracking.js"
  "$JS_DIR/pois.js"
)

for f in "${FILES[@]}"; do
  if [ -f "$f" ]; then
    echo "" >> "$STAMP_FILE"
    echo "/* ===== FILE: $f ===== */" >> "$STAMP_FILE"
    cat "$f" >> "$STAMP_FILE"
  fi
done

echo "</script>" >> "$STAMP_FILE"

# ============================================================
# 4. COPY LATEST
# ============================================================

cp "$STAMP_FILE" "$LATEST_FILE"




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

split_file "$STAMP_FILE"
split_file "$LATEST_FILE"



# ============================================================
# OUTPUT
# ============================================================

echo "✔ FULL EXPORT generado:"
echo "   - $STAMP_FILE"
echo "   - $LATEST_FILE"

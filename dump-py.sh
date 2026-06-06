#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"

PACKAGE_ROOT="$REPO_ROOT/cluster"
FILE_ROOT="runtime/node_boot.py"
ENTRY_FILE="$PACKAGE_ROOT/$FILE_ROOT"

STAMP="$(date +%Y%m%d_%H%M%S)"

BASE_DUMP_DIR="$REPO_ROOT/dump"
SNAPSHOT_DIR="$BASE_DUMP_DIR/py-dump"

mkdir -p "$BASE_DUMP_DIR"
mkdir -p "$SNAPSHOT_DIR"

CORE_LIST="$BASE_DUMP_DIR/py-core_files.txt"
NO_CORE_LIST="$BASE_DUMP_DIR/py-no_core_files.txt"

CORE_CODE="$BASE_DUMP_DIR/py-last_code_core.code"
NO_CORE_CODE="$BASE_DUMP_DIR/py-last_code_no_core.code"

CORE_HEADER="$BASE_DUMP_DIR/py-header_last_code_core.code"
NO_CORE_HEADER="$BASE_DUMP_DIR/py-header_last_code_no_core.code"

SUMMARY_FILE="$BASE_DUMP_DIR/py-core_summary.md"

CORE_LIST_TS="$SNAPSHOT_DIR/py-core_files_${STAMP}.txt"
NO_CORE_LIST_TS="$SNAPSHOT_DIR/py-no_core_files_${STAMP}.txt"

CORE_CODE_TS="$SNAPSHOT_DIR/py-last_code_core_${STAMP}.code"
NO_CORE_CODE_TS="$SNAPSHOT_DIR/py-last_code_no_core_${STAMP}.code"

CORE_HEADER_TS="$SNAPSHOT_DIR/py-header_last_code_core_${STAMP}.code"
NO_HEADER_TS="$SNAPSHOT_DIR/py-header_last_code_no_core_${STAMP}.code"

SUMMARY_FILE_TS="$SNAPSHOT_DIR/py-core_summary_${STAMP}.md"

python3 - "$PACKAGE_ROOT" "$ENTRY_FILE" "$CORE_LIST" "$NO_CORE_LIST" "$SUMMARY_FILE" <<'PY'
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import ast
import sys
from collections import deque
from pathlib import Path

PACKAGE_ROOT = Path(sys.argv[1]).resolve()
ENTRY_FILE = Path(sys.argv[2]).resolve()
CORE_LIST = Path(sys.argv[3]).resolve()
NO_CORE_LIST = Path(sys.argv[4]).resolve()
SUMMARY_FILE = Path(sys.argv[5]).resolve()
REPO_ROOT = PACKAGE_ROOT.parent
PKG = PACKAGE_ROOT.name

def module_from_path(p: Path) -> str:
    rel = p.resolve().relative_to(REPO_ROOT)
    parts = list(rel.parts)
    parts[-1] = parts[-1][:-3]
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)

def resolve_module(name: str, module_map: dict[str, Path]) -> Path | None:
    return module_map.get(name)

def expand_imports(file: Path, module_map: dict[str, Path]) -> list[Path]:
    try:
        tree = ast.parse(file.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return []

    found = set()
    cur_module = module_from_path(file)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                p = resolve_module(a.name, module_map)
                if p:
                    found.add(p)

        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            level = getattr(node, "level", 0)

            if level > 0:
                cur_parts = cur_module.split(".")
                if cur_parts and cur_parts[-1] == "__init__":
                    cur_parts = cur_parts[:-1]
                pkg_parts = cur_parts[:-level]
                if base:
                    pkg_parts += base.split(".")
                base = ".".join(pkg_parts)

            if base:
                p = resolve_module(base, module_map)
                if p:
                    found.add(p)

            for a in node.names:
                if a.name == "*":
                    continue
                cand = f"{base}.{a.name}" if base else a.name
                p = resolve_module(cand, module_map)
                if p:
                    found.add(p)

    return list(found)

def write_bundle(paths: list[Path], out_file: Path):
    with out_file.open("w", encoding="utf-8") as f:
        for p in paths:
            rel = "./" + str(p.resolve().relative_to(REPO_ROOT)).replace("\\", "/")
            f.write(f"\n\n===== {rel} =====\n")
            try:
                for i, line in enumerate(p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                    f.write(f"{i:6}  {line}\n")
            except Exception:
                continue

def write_header(src_file: Path, dst_file: Path):
    with src_file.open("r", encoding="utf-8", errors="ignore") as inp, dst_file.open("w", encoding="utf-8") as out:
        for line in inp:
            if line.startswith("===== "):
                out.write(line)
                continue
            stripped = line.strip()
            if stripped.startswith(("import ", "from ", "def ", "class ")):
                out.write(line)

def main():
    module_map = {}
    all_py = []

    for p in PACKAGE_ROOT.rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        module_map[module_from_path(p)] = p.resolve()
        all_py.append(p.resolve())

    entry = ENTRY_FILE  # ← Usa la variable de cabecera
    visited = set()
    queue = deque([entry.resolve()])
    core = []

    while queue:
        cur = queue.popleft()
        if cur in visited:
            continue
        visited.add(cur)
        core.append(cur)

        for dep in expand_imports(cur, module_map):
            if dep not in visited:
                queue.append(dep)

    core_files = sorted(core)
    core_set = set(core_files)
    no_core_files = sorted([p for p in all_py if p not in core_set])

    CORE_LIST.write_text("\n".join("./" + str(p.relative_to(REPO_ROOT)).replace("\\", "/") for p in core_files) + "\n", encoding="utf-8")
    NO_CORE_LIST.write_text("\n".join("./" + str(p.relative_to(REPO_ROOT)).replace("\\", "/") for p in no_core_files) + "\n", encoding="utf-8")
    SUMMARY_FILE.write_text(
        "# CORE REPORT\n\n"
        f"- core: {len(core_files)}\n"
        f"- no-core: {len(no_core_files)}\n",
        encoding="utf-8",
    )

if __name__ == "__main__":
    main()
PY

build_bundle() {
  local list_file="$1"
  local out_file="$2"

  : > "$out_file"

  while IFS= read -r f || [ -n "$f" ]; do
    [ -z "$f" ] && continue
    [ ! -f "$REPO_ROOT/$f" ] && continue

    printf "\n\n===== %s =====\n" "$f" >> "$out_file"
    nl -ba "$REPO_ROOT/$f" >> "$out_file"
  done < "$list_file"
}

build_header() {
  local in_file="$1"
  local out_file="$2"

  awk '
  /^===== .*\.py =====$/ { print; next }
  /^[[:space:]]*[0-9]+[[:space:]]+/ {
    line=$0
    sub(/^[[:space:]]*[0-9]+[[:space:]]+/, "", line)
    if (line ~ /^import / || line ~ /^from / || line ~ /^def / || line ~ /^class /)
      print
  }' "$in_file" > "$out_file"
}

build_bundle "$CORE_LIST" "$CORE_CODE"
build_bundle "$NO_CORE_LIST" "$NO_CORE_CODE"

build_header "$CORE_CODE" "$CORE_HEADER"
build_header "$NO_CORE_CODE" "$NO_CORE_HEADER"

cp "$CORE_LIST" "$CORE_LIST_TS"
cp "$NO_CORE_LIST" "$NO_CORE_LIST_TS"
cp "$CORE_CODE" "$CORE_CODE_TS"
cp "$NO_CORE_CODE" "$NO_CORE_CODE_TS"
cp "$CORE_HEADER" "$CORE_HEADER_TS"
cp "$NO_CORE_HEADER" "$NO_HEADER_TS"
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
            echo "# ENTRY_FILE       : ${FILE_ROOT}"
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
split_file "$NO_CORE_LIST"
split_file "$CORE_CODE"
split_file "$NO_CORE_CODE"
split_file "$CORE_HEADER"
split_file "$NO_CORE_HEADER"
split_file "$SUMMARY_FILE"

echo "$CORE_LIST"
echo "$NO_CORE_LIST"
echo "$CORE_CODE"
echo "$NO_CORE_CODE"
echo "$CORE_HEADER"
echo "$NO_CORE_HEADER"
echo "$SUMMARY_FILE"

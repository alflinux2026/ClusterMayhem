#!/usr/bin/env bash
set -euo pipefail

ENTRYPOINT="./runtime/node_boot.py"

CORE_LIST="core_files.txt"
NO_CORE_LIST="no_core_files.txt"

CORE_CODE="last_code_core.code"
NO_CORE_CODE="last_code_no_core.code"

CORE_HEADER="header_last_code_core.code"
NO_CORE_HEADER="header_last_code_no_core.code"

SUMMARY_FILE="core_summary.md"

python3 - "$ENTRYPOINT" "$CORE_LIST" "$NO_CORE_LIST" "$SUMMARY_FILE" <<'PY'
import ast
import sys
from pathlib import Path
from collections import deque

entrypoint = Path(sys.argv[1]).resolve()
core_list = Path(sys.argv[2]).resolve()
no_core_list = Path(sys.argv[3]).resolve()
summary_file = Path(sys.argv[4]).resolve()
repo = Path.cwd().resolve()
repo_name = repo.name

def rel_path(p: Path) -> str:
    return "./" + str(p.relative_to(repo)).replace("\\", "/")

def module_from_path(p: Path) -> str:
    rel = p.relative_to(repo)
    parts = list(rel.parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1][:-3]
    return ".".join(parts)

module_map = {}
all_py_paths = []

for p in repo.rglob("*.py"):
    rel = p.relative_to(repo)
    if "__pycache__" in rel.parts:
        continue
    if any(part.startswith(".") for part in rel.parts):
        continue
    mod = module_from_path(p)
    module_map[mod] = p.resolve()
    all_py_paths.append(rel_path(p))

all_py_paths = sorted(all_py_paths)

def normalize_module_name(name: str) -> str:
    if name == repo_name:
        return ""
    prefix = repo_name + "."
    if name.startswith(prefix):
        return name[len(prefix):]
    return name

def resolve_module(name: str):
    norm = normalize_module_name(name)
    if not norm:
        return None
    return module_map.get(norm)

def extract_internal_imports(pyfile: Path):
    current_module = module_from_path(pyfile)
    package_parts = current_module.split(".")[:-1] if current_module else []

    text = pyfile.read_text(encoding="utf-8", errors="ignore")
    tree = ast.parse(text, filename=str(pyfile))
    found = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                target = resolve_module(alias.name)
                if target:
                    found.add(target)

        elif isinstance(node, ast.ImportFrom):
            level = node.level or 0
            mod = node.module or ""

            if level > 0:
                base = package_parts[:]
                up = level - 1
                if up > 0:
                    base = base[:-up] if up <= len(base) else []
                full_base = ".".join(base + (mod.split(".") if mod else []))
            else:
                full_base = normalize_module_name(mod)

            candidates = []

            if full_base:
                candidates.append(full_base)

            for alias in node.names:
                if alias.name == "*":
                    continue
                if full_base:
                    candidates.append(f"{full_base}.{alias.name}")
                else:
                    candidates.append(alias.name)

            for cand in candidates:
                target = resolve_module(cand)
                if target:
                    found.add(target)

    return sorted(found)

def classify(path: str) -> str:
    p = path.lower()
    if "camion-de-la-basura" in p:
        return "Descartado/parking probable"
    if any(x in p for x in ["/legacy/", "/old/", "/backup/", "/tmp/", "/experimental/"]):
        return "Legacy/temporal probable"
    if "/tests/" in p or p.startswith("./tests/"):
        return "Test/auxiliar"
    if "/scripts/" in p or p.startswith("./scripts/"):
        return "Script auxiliar"
    if "/tools/" in p or p.startswith("./tools/"):
        return "Tool auxiliar"
    if "/utils/" in p or p.startswith("./utils/"):
        return "Utilidad auxiliar posible"
    if "/core/" in p:
        return "Rama alternativa o legado posible"
    if "/transport/" in p:
        return "Infra auxiliar o rama no conectada"
    if "/workers/" in p:
        return "Worker auxiliar o rama no conectada"
    if "/election/" in p:
        return "Módulo alternativo/no conectado posible"
    return "Fuera del core"

if not entrypoint.exists():
    raise SystemExit(f"ERROR: entrypoint no existe: {entrypoint}")

visited = set()
queue = deque([entrypoint.resolve()])
core_paths = []

while queue:
    current = queue.popleft()
    if current in visited:
        continue

    visited.add(current)
    core_paths.append(current)

    try:
        deps = extract_internal_imports(current)
    except Exception as e:
        print(f"WARNING: no se pudo parsear {current}: {e}", file=sys.stderr)
        continue

    for dep in deps:
        if dep not in visited:
            queue.append(dep)

core_files = sorted(rel_path(p) for p in core_paths)
core_set = set(core_files)
no_core_files = sorted(set(all_py_paths) - core_set)

core_list.write_text("\n".join(core_files) + "\n", encoding="utf-8")
no_core_list.write_text("\n".join(no_core_files) + "\n", encoding="utf-8")

with summary_file.open("w", encoding="utf-8") as f:
    f.write("# Resumen core/no-core\n\n")
    f.write("## Entrada analizada\n\n")
    f.write(f"- Entry point base: `{rel_path(entrypoint)}`\n")
    f.write(f"- Paquete raíz inferido: `{repo_name}`\n\n")

    f.write("## Métricas\n\n")
    f.write(f"- Total archivos `.py` en repo: **{len(all_py_paths)}**\n")
    f.write(f"- Total archivos `.py` en core: **{len(core_files)}**\n")
    f.write(f"- Total archivos `.py` en no-core: **{len(no_core_files)}**\n\n")

    f.write("## Archivos core\n\n")
    for path in core_files:
        f.write(f"- `{path}`\n")
    f.write("\n")

    f.write("## Archivos no-core\n\n")
    for path in no_core_files:
        f.write(f"- `{path}` — {classify(path)}\n")
    f.write("\n")

    f.write("## Nota\n\n")
    f.write("El core se calcula con imports estáticos recursivos desde el entrypoint.\n")
    f.write("Un archivo no-core no es automáticamente borrable; puede ser auxiliar, test, experimento o carga dinámica.\n")
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
    grep -n -E '^===== .*\.py =====$' "$in_file" || true

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
        if (line ~ /^(import |from .+ import )/) print $0
      }
    ' "$in_file"
  } > "$out_file"
}

build_bundle "$CORE_LIST" "$CORE_CODE"
build_bundle "$NO_CORE_LIST" "$NO_CORE_CODE"

build_header "$CORE_CODE" "$CORE_HEADER"
build_header "$NO_CORE_CODE" "$NO_CORE_HEADER"

printf '%s\n' "$CORE_LIST"
printf '%s\n' "$NO_CORE_LIST"
printf '%s\n' "$CORE_CODE"
printf '%s\n' "$NO_CORE_CODE"
printf '%s\n' "$CORE_HEADER"
printf '%s\n' "$NO_CORE_HEADER"
printf '%s\n' "$SUMMARY_FILE"

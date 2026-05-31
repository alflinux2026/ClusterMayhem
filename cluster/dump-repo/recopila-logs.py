
import re
import csv
import paramiko
from pathlib import Path

NODES = [
    {"name": "lnx200nas", "host": "100.100.1.200", "user": "alftorres", "password": "alftorres", "port": 22},
    {"name": "lnx202pc", "host": "100.100.1.202", "user": "alftorres", "password": "alftorres", "port": 22},
    {"name": "lnx203hp", "host": "100.100.1.203", "user": "alftorres", "password": "alftorres", "port": 22},
]

# Ruta distinta por nodo
REMOTE_DIRS = {
    "lnx200nas":  "/home/alftorres/projects/mayhem-cluster/cluster/data",
    "lnx202pc":  "/home/alftorres/projects/mayhem-cluster/cluster/data",
    "lnx203hp":  "/home/alftorres/projects/Mayhem_runtime_oneshot/cluster/data",
}

OUT_MD = Path("cluster_data_remote_inventory.md")
OUT_CSV = Path("cluster_data_remote_inventory.csv")

LINE_RE = re.compile(
    r"^(?P<perm>\S+)\s+"
    r"(?P<links>\d+)\s+"
    r"(?P<owner>\S+)\s+"
    r"(?P<group>\S+)\s+"
    r"(?P<size>\d+)\s+"
    r"(?P<date>\d{4}-\d{2}-\d{2})\s+"
    r"(?P<time>\d{2}:\d{2}:\d{2}\.\d+)\s+"
    r"(?P<tz>[+-]\d{4})\s+"
    r"(?P<name>.+)$"
)

def ssh_ls(node):
    remote_dir = REMOTE_DIRS[node["name"]]
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=node["host"],
        port=node["port"],
        username=node["user"],
        password=node["password"],
        timeout=5,
        look_for_keys=False,
        allow_agent=False,
    )
    cmd = f'ls -lb --full-time "{remote_dir}"'
    stdin, stdout, stderr = client.exec_command(cmd)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    client.close()

    if err.strip() and not out.strip():
        raise RuntimeError(f"{node['name']}: {err.strip()}")

    return out

def parse_ls_output(node_name, text):
    rows = []
    for line in text.splitlines():
        line = line.rstrip()
        if not line or line.startswith("total "):
            continue
        m = LINE_RE.match(line)
        if not m:
            continue
        d = m.groupdict()
        file_name = d["name"]
        m_source = re.match(r"^event_log\.(.+)\.jsonl$", file_name)
        if not m_source:
            continue
        source = m_source.group(1)

        # también capturamos .local como si fuera lnx200nas
        if file_name == "event_log.local.jsonl" and node_name == "lnx200nas":
            source = "lnx200nas"
        if file_name == "event_log.local.jsonl" and node_name == "lnx202pc":
            source = "lnx202pc"
        if file_name == "event_log.local.jsonl" and node_name == "lnx203hp":
            source = "lnx203hp"

        rows.append({
            "node": node_name,
            "file": file_name,
            "source": source,
            "mtime_date": d["date"],
            "mtime_time": d["time"],
            "mtime_tz": d["tz"],
            "size": int(d["size"]),
        })
    return rows

def build_groups(rows):
    groups = {}
    for row in rows:
        groups.setdefault(row["source"], []).append(row)
    return groups

def check_consistency(groups):
    for source, entries in groups.items():
        for file_name in set(e["file"] for e in entries):
            entries_file = [e for e in entries if e["file"] == file_name]
            sizes = {e["node"]: e["size"] for e in entries_file}
            mtimes = {e["node"]: (e["mtime_date"], e["mtime_time"]) for e in entries_file}
            size_ok = len(set(sizes.values())) == 1
            mtime_ok = len(set(mtimes.values())) <= 2

            print(
                f"[INFO] {source}/{file_name}: "
                f"size={'OK' if size_ok else 'MISMATCH'} "
                f"mtime={'OK' if mtime_ok else 'MISMATCH'}"
            )

def render_markdown(groups):
    source_order = ["lnx200nas", "lnx202pc", "lnx203hp"]

    # Anchuras de columna
    NODE_WIDTH  = 16
    FILE_WIDTH  = 30
    SIZE_WIDTH  = 10
    MTIME_WIDTH = 25

    lines = []

    for source in source_order:
        if source not in groups:
            continue
        entries = groups[source]

        lines.append(f"### log de {source}:")
        lines.append("")

        # 1. fila: .local en el nodo source
        local = next(
            (e for e in entries if e["node"] == source and "local" in e["file"]),
            None
        )

        # 2. fila: copia local (event_log.<source>.jsonl) en el mismo nodo source
        local_replica = next(
            (e for e in entries
             if e["node"] == source and e["file"] == f"event_log.{source}.jsonl"),
            None
        )

        # 3. resto: event_log.<source>.jsonl en otros nodos
        remotes = [
            e for e in entries
            if e["file"] == f"event_log.{source}.jsonl" and e["node"] != source
        ]
        remotes.sort(key=lambda x: x["node"])

        # Escribe .local primero
        if local:
            node  = (local["node"] + " " * NODE_WIDTH)[:NODE_WIDTH]
            file  = (local["file"] + " " * FILE_WIDTH)[:FILE_WIDTH]
            size  = (f"{local['size']}" + " " * SIZE_WIDTH)[:SIZE_WIDTH]
            mtime = (
                local["mtime_date"] + "T" + local["mtime_time"] + local["mtime_tz"] + " " * MTIME_WIDTH
            )[:MTIME_WIDTH]
            lines.append(f"- {node}  {file}  {size}  {mtime}")

        # luego copia local en el mismo nodo
        if local_replica:
            node  = (local_replica["node"] + " " * NODE_WIDTH)[:NODE_WIDTH]
            file  = (local_replica["file"] + " " * FILE_WIDTH)[:FILE_WIDTH]
            size  = (f"{local_replica['size']}" + " " * SIZE_WIDTH)[:SIZE_WIDTH]
            mtime = (
                local_replica["mtime_date"] + "T" + local_replica["mtime_time"] + local_replica["mtime_tz"] + " " * MTIME_WIDTH
            )[:MTIME_WIDTH]
            lines.append(f"- {node}  {file}  {size}  {mtime}")

        # finalmente remotos
        for e in remotes:
            node  = (e["node"] + " " * NODE_WIDTH)[:NODE_WIDTH]
            file  = (e["file"] + " " * FILE_WIDTH)[:FILE_WIDTH]
            size  = (f"{e['size']}" + " " * SIZE_WIDTH)[:SIZE_WIDTH]
            mtime = (
                e["mtime_date"] + "T" + e["mtime_time"] + e["mtime_tz"] + " " * MTIME_WIDTH
            )[:MTIME_WIDTH]
            lines.append(f"- {node}  {file}  {size}  {mtime}")

        lines.append("")

    return "\n".join(lines).strip() + "\n"


def main():
    all_rows = []
    for node in NODES:
        print(f"[INFO] Consultando {node['name']} ({node['host']})...")
        try:
            text = ssh_ls(node)
            rows = parse_ls_output(node["name"], text)
            all_rows.extend(rows)
        except Exception as e:
            print(f"[ERROR] {node['name']}: {e}")

    groups = build_groups(all_rows)
    check_consistency(groups)

    md = render_markdown(groups)
    OUT_MD.write_text(md, encoding="utf-8")

    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["node", "file", "source", "mtime_date", "mtime_time", "mtime_tz", "size"],
        )
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"[OK] Markdown: {OUT_MD}")
    print(f"[OK] CSV: {OUT_CSV}")

if __name__ == "__main__":
    main()

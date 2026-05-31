import csv
import curses
import json
import re
import time
from datetime import datetime
from pathlib import Path

import paramiko
import requests

NODES = [
    {"name": "lnx200nas", "host": "100.100.1.200", "user": "alftorres", "password": "alftorres", "port": 22, "api_port": 7000},
    {"name": "lnx202pc", "host": "100.100.1.202", "user": "alftorres", "password": "alftorres", "port": 22, "api_port": 7000},
    {"name": "lnx203hp", "host": "100.100.1.203", "user": "alftorres", "password": "alftorres", "port": 22, "api_port": 7000},
]

REMOTE_DIRS = {
    "lnx200nas": "/home/alftorres/projects/mayhem-cluster/cluster/data",
    "lnx202pc": "/home/alftorres/projects/mayhem-cluster/cluster/data",
    "lnx203hp": "/home/alftorres/projects/Mayhem_runtime_oneshot/cluster/data",
}

OUT_MD = Path("cluster_data_remote_inventory.md")
OUT_CSV = Path("cluster_data_remote_inventory.csv")
OUT_API_JSON = Path("cluster_data_remote_api_snapshot.json")
OUT_SNAPSHOT_DIR = Path("snapshots")

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

HTTP = requests.Session()
LAST_STATUS_LINE = ""


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
        if not m_source and file_name != "event_log.local.jsonl":
            continue

        source = m_source.group(1) if m_source else None
        if file_name == "event_log.local.jsonl":
            source = node_name

        rows.append(
            {
                "node": node_name,
                "file": file_name,
                "source": source,
                "mtime_date": d["date"],
                "mtime_time": d["time"],
                "mtime_tz": d["tz"],
                "size": int(d["size"]),
            }
        )
    return rows


def fetch_json(url, timeout=4):
    try:
        resp = HTTP.get(url, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": str(e), "url": url}


def fetch_api_snapshot(node):
    base = f"http://{node['host']}:{node['api_port']}"
    dashboard = fetch_json(f"{base}/dashboard/compact")
    health = fetch_json(f"{base}/health")
    integrity = fetch_json(f"{base}/integrity")
    events_summary_local = fetch_json(f"{base}/debug/events/summary")

    return {
        "node": node["name"],
        "host": node["host"],
        "health": health,
        "dashboard": dashboard,
        "integrity": integrity,
        "events_summary_local": events_summary_local,
    }


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
                f"[INFO] {source}/{file_name}: size={'OK' if size_ok else 'MISMATCH'} "
                f"mtime={'OK' if mtime_ok else 'MISMATCH'}"
            )


def _node_runtime_view(api_snapshots, node_name):
    def fallback(*values):
        for value in values:
            if value is not None:
                return value
        return None

    def score_row(row):
        if not isinstance(row, dict):
            return -1
        score = 0
        if row.get("node_id") == node_name:
            score += 1
        if row.get("presence_age_s") is not None:
            score += 2
        if row.get("watchdog_age_s") is not None:
            score += 4
        if row.get("watchdog_busy") is not None:
            score += 2
        if row.get("health") == "ok":
            score += 1
        if row.get("progress_stage") is not None:
            score += 1
        if row.get("progress_age_s") is not None:
            score += 1
        return score

    local_snap = api_snapshots.get(node_name, {}) or {}
    local_health = local_snap.get("health", {}) or {}
    local_integrity = local_snap.get("integrity", {}) or {}
    local_summary = local_snap.get("events_summary_local", {}) or {}

    candidate_rows = []

    for snap_name, snap in (api_snapshots or {}).items():
        dashboard = (snap or {}).get("dashboard", {}) or {}
        for r in dashboard.get("nodes", []) or []:
            if r.get("node_id") == node_name:
                candidate_rows.append((snap_name, r))

    best_row = {}
    if candidate_rows:
        candidate_rows.sort(key=lambda item: score_row(item[1]), reverse=True)
        best_row = candidate_rows[0][1] or {}

    counts = local_summary.get("counts", {}) if isinstance(local_summary, dict) else {}
    local_meta = local_integrity.get("local_log_meta", {}) if isinstance(local_integrity, dict) else {}
    last_append = local_integrity.get("last_append_meta", {}) if isinstance(local_integrity, dict) else {}

    state_raw = fallback(best_row.get("state"), local_health.get("state"))
    state_value = state_raw if state_raw in (
        "ACTIVE", "STAND-BY", "STANDBY", "DEGRADED", "ISOLATED", "OFFLINE"
    ) else "???"

    progress_active = fallback(best_row.get("progress_active"), local_health.get("progress_active"), False)
    progress_stage = fallback(best_row.get("progress_stage"), local_health.get("progress_stage"))
    progress_age_s = fallback(best_row.get("progress_age_s"), local_health.get("progress_age_s"))
    progress_current = fallback(best_row.get("progress_current"), local_health.get("progress_current"))
    progress_total = fallback(best_row.get("progress_total"), local_health.get("progress_total"))
    progress_stalled = fallback(best_row.get("progress_stalled"), local_health.get("progress_stalled"), False)

    progress_pct = None
    try:
        if progress_current is not None and progress_total not in (None, 0):
            progress_pct = round((float(progress_current) / float(progress_total)) * 100.0, 1)
    except Exception:
        progress_pct = None

    return {
        "health": fallback(best_row.get("health"), local_health.get("status"), "?"),
        "state": state_value,
        "state_age_s": fallback(best_row.get("state_age_s"), local_health.get("state_age_s")),
        "presence_age_s": fallback(best_row.get("presence_age_s"), local_health.get("presence_age_s")),
        "watchdog_age_s": fallback(best_row.get("watchdog_age_s"), local_health.get("watchdog_age_s")),
        "watchdog_busy": fallback(best_row.get("watchdog_busy"), local_health.get("watchdog_busy")),
        "progress_active": bool(progress_active),
        "progress_stage": progress_stage,
        "progress_age_s": progress_age_s,
        "progress_current": progress_current,
        "progress_total": progress_total,
        "progress_pct": progress_pct,
        "progress_stalled": bool(progress_stalled),
        "local_size": int(local_meta.get("size", 0) or 0),
        "local_events": int(local_summary.get("total_events", 0) or 0),
        "created": int(counts.get("created", 0) or 0),
        "executing": int(counts.get("executing", 0) or 0),
        "completed": int(counts.get("completed", 0) or 0),
        "dirty": last_append.get("dirty", "-"),
    }


def setup_colors():
    if not curses.has_colors():
        return False

    curses.start_color()
    curses.use_default_colors()

    curses.init_pair(1, curses.COLOR_GREEN, -1)
    curses.init_pair(2, curses.COLOR_YELLOW, -1)
    curses.init_pair(3, curses.COLOR_RED, -1)
    curses.init_pair(4, curses.COLOR_CYAN, -1)
    curses.init_pair(5, curses.COLOR_WHITE, -1)
    curses.init_pair(6, curses.COLOR_MAGENTA, -1)
    return True


def color_for_health(value):
    v = str(value or "").lower()
    if v == "ok":
        return curses.color_pair(1) | curses.A_BOLD
    if v == "stale":
        return curses.color_pair(3) | curses.A_BOLD
    return curses.color_pair(2) | curses.A_BOLD


def color_for_state(state, stale=False):
    if stale:
        return curses.color_pair(3) | curses.A_BOLD

    s = str(state or "").upper()
    if s == "ACTIVE":
        return curses.color_pair(1) | curses.A_BOLD
    if s in ("STAND-BY", "STANDBY"):
        return curses.color_pair(2) | curses.A_BOLD
    if s == "DEGRADED":
        return curses.color_pair(6) | curses.A_BOLD
    if s in ("ISOLATED", "OFFLINE", "???"):
        return curses.color_pair(3) | curses.A_BOLD
    return curses.color_pair(5)


def color_for_dirty(value):
    if value is True or str(value).lower() == "true":
        return curses.color_pair(3) | curses.A_BOLD
    return curses.color_pair(1)


def color_for_count(label, value):
    try:
        n = int(value)
    except Exception:
        n = 0

    if label == "executing" and n > 0:
        return curses.color_pair(2) | curses.A_BOLD
    if label == "created" and n > 0:
        return curses.color_pair(6) | curses.A_BOLD
    if label == "completed" and n > 0:
        return curses.color_pair(1)
    return curses.color_pair(5)


def color_for_age(value, warn_s=1.5, stale_s=3.0):
    if value is None:
        return curses.color_pair(5)
    try:
        age = float(value)
    except Exception:
        return curses.color_pair(5)
    if age >= stale_s:
        return curses.color_pair(3) | curses.A_BOLD
    if age >= warn_s:
        return curses.color_pair(2) | curses.A_BOLD
    return curses.color_pair(1)


def color_for_busy(value):
    if value is True:
        return curses.color_pair(6) | curses.A_BOLD
    if value is False:
        return curses.color_pair(1)
    return curses.color_pair(5)


def color_for_progress_active(value):
    if value is True:
        return curses.color_pair(6) | curses.A_BOLD
    return curses.color_pair(5)


def color_for_progress_stalled(value):
    if value is True:
        return curses.color_pair(3) | curses.A_BOLD
    return curses.color_pair(1)


def color_for_progress_stage(stage):
    if not stage:
        return curses.color_pair(5)
    return curses.color_pair(4)


def render_top_summary_1(api_snapshots, groups):
    source_order = ["lnx200nas", "lnx202pc", "lnx203hp"]
    lines = []

    NODE_W = 12
    HEALTH_W = 8
    STATE_W = 12
    TSTATE_W = 8
    PRES_W = 7
    WDOG_W = 7
    BUSY_W = 5
    STAGE_W = 18
    PROG_W = 12
    PAGE_W = 7
    STALL_W = 6
    SIZE_W = 10
    EVENTS_W = 12
    COUNT_W = 9
    DIRTY_W = 7

    def cut(value, width):
        s = "-" if value is None else str(value)
        return s if len(s) <= width else s[: max(0, width - 1)] + "…"

    def fmt_age(value):
        if value is None:
            return "-"
        try:
            value = float(value)
        except Exception:
            return "-"
        if value < 60:
            return f"{value:.0f}s"
        if value < 3600:
            return f"{value / 60:.1f}m"
        return f"{value / 3600:.1f}h"

    def fmt_busy(value):
        if value is True:
            return "Y"
        if value is False:
            return "N"
        return "?"

    def fmt_progress(current, total, pct):
        if current is None and total is None:
            return "-"
        try:
            if pct is not None and current is not None and total is not None:
                return f"{int(current)}/{int(total)} {pct:.0f}%"
            if current is not None and total is not None:
                return f"{int(current)}/{int(total)}"
            return str(current if current is not None else "-")
        except Exception:
            return "-"

    lines.append("### resumen cluster")
    lines.append("")
    lines.append(
        "- leader esperado: "
        + ", ".join(
            f"{node}: {api_snapshots.get(node, {}).get('dashboard', {}).get('cluster', {}).get('leader', '?')}"
            for node in source_order
        )
    )
    lines.append("")
    lines.append(
        f"- {'nodo':<{NODE_W}}  {'health':<{HEALTH_W}}  {'state':<{STATE_W}}  {'t_state':>{TSTATE_W}}  "
        f"{'pres':>{PRES_W}}  {'wdog':>{WDOG_W}}  {'busy':<{BUSY_W}}  "
        f"{'stage':<{STAGE_W}}  {'prog':>{PROG_W}}  {'p_age':>{PAGE_W}}  {'stall':<{STALL_W}}  "
        f"{'local_size':>{SIZE_W}}  {'local_events':>{EVENTS_W}}  "
        f"{'created':>{COUNT_W}}  {'executing':>{COUNT_W}}  {'completed':>{COUNT_W}}  "
        f"{'dirty':<{DIRTY_W}}"
    )

    for node_name in source_order:
        view = _node_runtime_view(api_snapshots, node_name)
        lines.append(
            f"- {node_name:<{NODE_W}}  "
            f"{cut(view['health'], HEALTH_W):<{HEALTH_W}}  "
            f"{cut(view['state'], STATE_W):<{STATE_W}}  "
            f"{fmt_age(view['state_age_s']):>{TSTATE_W}}  "
            f"{fmt_age(view['presence_age_s']):>{PRES_W}}  "
            f"{fmt_age(view['watchdog_age_s']):>{WDOG_W}}  "
            f"{fmt_busy(view['watchdog_busy']):<{BUSY_W}}  "
            f"{cut(view['progress_stage'], STAGE_W):<{STAGE_W}}  "
            f"{cut(fmt_progress(view['progress_current'], view['progress_total'], view['progress_pct']), PROG_W):>{PROG_W}}  "
            f"{fmt_age(view['progress_age_s']):>{PAGE_W}}  "
            f"{('Y' if view['progress_stalled'] else 'N'):<{STALL_W}}  "
            f"{view['local_size']:>{SIZE_W}}  "
            f"{view['local_events']:>{EVENTS_W}}  "
            f"{view['created']:>{COUNT_W}}  "
            f"{view['executing']:>{COUNT_W}}  "
            f"{view['completed']:>{COUNT_W}}  "
            f"{cut(view['dirty'], DIRTY_W):<{DIRTY_W}}"
        )

    lines.append("")
    return lines


def draw_top_summary_curses(stdscr, start_y, api_snapshots, width):
    source_order = ["lnx200nas", "lnx202pc", "lnx203hp"]

    NODE_W = 12
    HEALTH_W = 8
    STATE_W = 12
    TSTATE_W = 8
    PRES_W = 7
    WDOG_W = 7
    BUSY_W = 5
    STAGE_W = 18
    PROG_W = 12
    PAGE_W = 7
    STALL_W = 6
    SIZE_W = 10
    EVENTS_W = 12
    COUNT_W = 9
    DIRTY_W = 7

    def cut(value, width):
        s = "-" if value is None else str(value)
        return s if len(s) <= width else s[: max(0, width - 1)] + "…"

    def fmt_age(value):
        if value is None:
            return "-"
        try:
            value = float(value)
        except Exception:
            return "-"
        if value < 60:
            return f"{value:.0f}s"
        if value < 3600:
            return f"{value / 60:.1f}m"
        return f"{value / 3600:.1f}h"

    def fmt_busy(value):
        if value is True:
            return "Y"
        if value is False:
            return "N"
        return "?"

    def fmt_progress(current, total, pct):
        if current is None and total is None:
            return "-"
        try:
            if pct is not None and current is not None and total is not None:
                return f"{int(current)}/{int(total)} {pct:.0f}%"
            if current is not None and total is not None:
                return f"{int(current)}/{int(total)}"
            return str(current if current is not None else "-")
        except Exception:
            return "-"

    def put(y, x, text, attr=0):
        if y < 0 or x >= width - 1:
            return
        stdscr.addnstr(y, x, text, max(1, width - 1 - x), attr)

    y = start_y

    put(y, 0, "### resumen cluster", curses.color_pair(4) | curses.A_BOLD)
    y += 2
    put(
        y,
        0,
        "- leader esperado: "
        + ", ".join(
            f"{node}: {api_snapshots.get(node, {}).get('dashboard', {}).get('cluster', {}).get('leader', '?')}"
            for node in source_order
        ),
        curses.color_pair(4),
    )
    y += 2

    header = (
        f"- {'nodo':<{NODE_W}}  {'health':<{HEALTH_W}}  {'state':<{STATE_W}}  {'t_state':>{TSTATE_W}}  "
        f"{'pres':>{PRES_W}}  {'wdog':>{WDOG_W}}  {'busy':<{BUSY_W}}  "
        f"{'stage':<{STAGE_W}}  {'prog':>{PROG_W}}  {'p_age':>{PAGE_W}}  {'stall':<{STALL_W}}  "
        f"{'local_size':>{SIZE_W}}  {'local_events':>{EVENTS_W}}  "
        f"{'created':>{COUNT_W}}  {'executing':>{COUNT_W}}  {'completed':>{COUNT_W}}  {'dirty':<{DIRTY_W}}"
    )
    put(y, 0, header, curses.color_pair(4) | curses.A_BOLD)
    y += 1

    for node_name in source_order:
        view = _node_runtime_view(api_snapshots, node_name)
        health_value = cut(view["health"], HEALTH_W)
        state_value = cut(view["state"], STATE_W)
        stale_state = str(health_value).lower() == "stale"

        cols = [
            (f"- {node_name:<{NODE_W}}  ", curses.color_pair(5)),
            (f"{health_value:<{HEALTH_W}}  ", color_for_health(health_value)),
            (f"{state_value:<{STATE_W}}  ", color_for_state(state_value, stale=stale_state)),
            (f"{fmt_age(view['state_age_s']):>{TSTATE_W}}  ", curses.color_pair(5)),
            (f"{fmt_age(view['presence_age_s']):>{PRES_W}}  ", color_for_age(view["presence_age_s"], warn_s=1.5, stale_s=3.0)),
            (f"{fmt_age(view['watchdog_age_s']):>{WDOG_W}}  ", color_for_age(view["watchdog_age_s"], warn_s=1.5, stale_s=3.0)),
            (f"{fmt_busy(view['watchdog_busy']):<{BUSY_W}}  ", color_for_busy(view["watchdog_busy"])),
            (f"{cut(view['progress_stage'], STAGE_W):<{STAGE_W}}  ", color_for_progress_stage(view["progress_stage"])),
            (
                f"{cut(fmt_progress(view['progress_current'], view['progress_total'], view['progress_pct']), PROG_W):>{PROG_W}}  ",
                color_for_progress_active(view["progress_active"]),
            ),
            (
                f"{fmt_age(view['progress_age_s']):>{PAGE_W}}  ",
                color_for_age(view["progress_age_s"], warn_s=1.5, stale_s=3.0),
            ),
            (
                f"{('Y' if view['progress_stalled'] else 'N'):<{STALL_W}}  ",
                color_for_progress_stalled(view["progress_stalled"]),
            ),
            (f"{view['local_size']:>{SIZE_W}}  ", curses.color_pair(5)),
            (f"{view['local_events']:>{EVENTS_W}}  ", curses.color_pair(5)),
            (f"{view['created']:>{COUNT_W}}  ", color_for_count("created", view["created"])),
            (f"{view['executing']:>{COUNT_W}}  ", color_for_count("executing", view["executing"])),
            (f"{view['completed']:>{COUNT_W}}  ", color_for_count("completed", view["completed"])),
            (f"{cut(view['dirty'], DIRTY_W):<{DIRTY_W}}", color_for_dirty(view["dirty"])),
        ]

        x = 0
        for text, attr in cols:
            put(y, x, text, attr)
            x += len(text)

        y += 1

    return y + 1


def render_file_inventory(groups):
    source_order = ["lnx200nas", "lnx202pc", "lnx203hp"]
    NODE_WIDTH = 16
    FILE_WIDTH = 30
    SIZE_WIDTH = 10
    MTIME_WIDTH = 30
    lines = []

    for source in source_order:
        if source not in groups:
            continue
        entries = groups[source]
        lines.append(f"### log de {source}:")
        lines.append("")

        local = next((e for e in entries if e["node"] == source and "local" in e["file"]), None)
        local_replica = next(
            (e for e in entries if e["node"] == source and e["file"] == f"event_log.{source}.jsonl"),
            None,
        )
        remotes = [
            e for e in entries if e["file"] == f"event_log.{source}.jsonl" and e["node"] != source
        ]
        remotes.sort(key=lambda x: x["node"])

        for e in [local, local_replica, *remotes]:
            if not e:
                continue
            node = (e["node"] + " " * NODE_WIDTH)[:NODE_WIDTH]
            file = (e["file"] + " " * FILE_WIDTH)[:FILE_WIDTH]
            size = (f"{e['size']}" + " " * SIZE_WIDTH)[:SIZE_WIDTH]
            mtime = (e["mtime_date"] + "T" + e["mtime_time"] + e["mtime_tz"] + " " * MTIME_WIDTH)[:MTIME_WIDTH]
            lines.append(f"- {node}  {file}  {size}  {mtime}")

        lines.append("")

    return lines


def render_markdown(groups, api_snapshots):
    lines = []
    lines.extend(render_top_summary_1(api_snapshots, groups))
    lines.extend(render_file_inventory(groups))
    return "\n".join(lines).strip() + "\n"


def collect_snapshot():
    all_rows = []
    api_snapshots = {}
    errors = []

    for node in NODES:
        try:
            text = ssh_ls(node)
            rows = parse_ls_output(node["name"], text)
            all_rows.extend(rows)
        except Exception as e:
            errors.append(f"SSH {node['name']}: {e}")

        try:
            api_snapshots[node["name"]] = fetch_api_snapshot(node)
        except Exception as e:
            errors.append(f"API {node['name']}: {e}")
            api_snapshots[node["name"]] = {"node": node["name"], "error": str(e)}

    groups = build_groups(all_rows)
    return groups, api_snapshots, errors


def write_outputs(groups, api_snapshots):
    all_rows = []
    for entries in groups.values():
        all_rows.extend(entries)

    md = render_markdown(groups, api_snapshots)
    OUT_MD.write_text(md, encoding="utf-8")

    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["node", "file", "source", "mtime_date", "mtime_time", "mtime_tz", "size"],
        )
        writer.writeheader()
        writer.writerows(all_rows)

    OUT_API_JSON.write_text(json.dumps(api_snapshots, ensure_ascii=False, indent=2), encoding="utf-8")


def save_snapshot(lines, groups, api_snapshots, errors, started_at, refresh_seconds):
    OUT_SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    ts_file = datetime.now().strftime("%Y%m%d_%H%M%S")

    md_path = OUT_SNAPSHOT_DIR / f"cluster_live_snapshot_{ts_file}.md"
    json_path = OUT_SNAPSHOT_DIR / f"cluster_live_snapshot_{ts_file}.json"

    md_content = "\n".join(lines).strip() + "\n"
    md_path.write_text(md_content, encoding="utf-8")

    snapshot_payload = {
        "captured_at": datetime.now().isoformat(),
        "refresh_seconds": refresh_seconds,
        "monitor_uptime_s": round(time.time() - started_at, 3),
        "errors": errors,
        "groups": groups,
        "api_snapshots": api_snapshots,
        "rendered_lines": lines,
    }
    json_path.write_text(json.dumps(snapshot_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return md_path, json_path


def build_screen_lines(groups, api_snapshots, errors, started_at, refresh_seconds):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = []
    lines.append(
        f"cluster_live.py  actualizado: {ts}  refresh={refresh_seconds:.1f}s  "
        f"[s]=snapshot md+json  [q]=salir"
    )
    lines.append("")
    if errors:
        lines.append("errores:")
        for err in errors:
            lines.append(f"- {err}")
        lines.append("")
    lines.extend(render_top_summary_1(api_snapshots, groups))
    lines.extend(render_file_inventory(groups))
    lines.append(f"uptime monitor: {time.time() - started_at:.1f}s")
    if LAST_STATUS_LINE:
        lines.append("")
        lines.append(LAST_STATUS_LINE)
    return lines


def ui_loop(stdscr, refresh_seconds=1.5):
    global LAST_STATUS_LINE

    curses.curs_set(0)
    curses.noecho()
    curses.cbreak()
    stdscr.nodelay(True)
    stdscr.keypad(True)
    setup_colors()
    started_at = time.time()

    while True:
        cycle_start = time.time()
        groups, api_snapshots, errors = collect_snapshot()
        write_outputs(groups, api_snapshots)
        lines = build_screen_lines(groups, api_snapshots, errors, started_at, refresh_seconds)

        stdscr.erase()
        height, width = stdscr.getmaxyx()
        usable_height = max(1, height - 1)

        stdscr.addnstr(
            0,
            0,
            f"cluster_live.py  actualizado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  refresh={refresh_seconds:.1f}s  [s]=snapshot md+json  [q]=salir",
            max(1, width - 1),
            curses.color_pair(4) | curses.A_BOLD,
        )

        y = 2

        if errors:
            stdscr.addnstr(y, 0, "errores:", max(1, width - 1), curses.color_pair(3) | curses.A_BOLD)
            y += 1
            for err in errors:
                if y >= usable_height:
                    break
                stdscr.addnstr(y, 0, f"- {err}", max(1, width - 1), curses.color_pair(3))
                y += 1
            y += 1

        if y < usable_height:
            y = draw_top_summary_curses(stdscr, y, api_snapshots, width)

        plain_lines = render_file_inventory(groups)
        plain_lines.append(f"uptime monitor: {time.time() - started_at:.1f}s")
        if LAST_STATUS_LINE:
            plain_lines.append("")
            plain_lines.append(LAST_STATUS_LINE)

        for line in plain_lines:
            if y >= usable_height:
                break
            stdscr.addnstr(y, 0, line, max(1, width - 1))
            y += 1

        stdscr.refresh()

        while True:
            key = stdscr.getch()

            if key in (ord("q"), ord("Q")):
                return

            if key in (ord("s"), ord("S")):
                try:
                    md_path, json_path = save_snapshot(
                        lines=lines,
                        groups=groups,
                        api_snapshots=api_snapshots,
                        errors=errors,
                        started_at=started_at,
                        refresh_seconds=refresh_seconds,
                    )
                    LAST_STATUS_LINE = f"[snapshot] guardado md={md_path} json={json_path}"
                except Exception as e:
                    LAST_STATUS_LINE = f"[snapshot] error: {e}"
                break

            if key == -1:
                pass
            else:
                continue

            if time.time() - cycle_start >= refresh_seconds:
                break

            time.sleep(0.05)


def run_live_monitor(refresh_seconds=1.5):
    curses.wrapper(lambda stdscr: ui_loop(stdscr, refresh_seconds=refresh_seconds))


def run_once():
    all_rows = []
    api_snapshots = {}

    for node in NODES:
        print(f"[INFO] Consultando SSH {node['name']} ({node['host']})...")
        try:
            text = ssh_ls(node)
            rows = parse_ls_output(node["name"], text)
            all_rows.extend(rows)
        except Exception as e:
            print(f"[ERROR] SSH {node['name']}: {e}")

        print(f"[INFO] Consultando API {node['name']} ({node['host']})...")
        api_snapshots[node["name"]] = fetch_api_snapshot(node)

    groups = build_groups(all_rows)
    check_consistency(groups)
    write_outputs(groups, api_snapshots)

    print(f"[OK] Markdown: {OUT_MD}")
    print(f"[OK] CSV: {OUT_CSV}")
    print(f"[OK] API JSON: {OUT_API_JSON}")


if __name__ == "__main__":
    run_live_monitor()

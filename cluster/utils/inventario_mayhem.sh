#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
import json, subprocess, os, time, platform

def run(cmd):
    try:
        return subprocess.check_output(cmd, text=True).strip()
    except Exception:
        return ""

def run_json(cmd):
    try:
        return json.loads(subprocess.check_output(cmd, text=True))
    except Exception:
        return None

def try_int(s):
    try:
        return int(s)
    except Exception:
        return None

host = platform.node() or run(["/usr/bin/hostname"]) or run(["hostname"]) or "unknown"
now = time.strftime("%Y-%m-%dT%H:%M:%S%z")

os_release = ""
try:
    with open("/etc/os-release", "r", encoding="utf-8") as f:
        for line in f:
            if line.startswith("PRETTY_NAME="):
                os_release = line.split("=",1)[1].strip().strip('"')
                break
except Exception:
    pass

lscpu_txt = run(["lscpu"])
cpu_model = ""
cores = None
threads_per_core = None
for line in lscpu_txt.splitlines():
    if "Model name:" in line and not cpu_model:
        cpu_model = line.split(":",1)[1].strip()
    elif line.startswith("CPU(s):") and cores is None:
        cores = try_int(line.split(":",1)[1].strip())
    elif line.startswith("Thread(s) per core:") and threads_per_core is None:
        threads_per_core = try_int(line.split(":",1)[1].strip())

free_txt = run(["free", "-h"])
mem_total = mem_used = mem_avail = ""
for line in free_txt.splitlines():
    if line.startswith("Mem:"):
        parts = line.split()
        if len(parts) >= 7:
            mem_total, mem_used, mem_avail = parts[1], parts[2], parts[6]
        break

storage = run_json(["lsblk", "-J", "-o", "NAME,SIZE,FSTYPE,MOUNTPOINT,MODEL,TYPE"])
ips = run_json(["ip", "-j", "addr", "show"])
routes = run_json(["ip", "-j", "route", "show"])

loadavg = ""
try:
    with open("/proc/loadavg", "r", encoding="utf-8") as f:
        loadavg = f.read().strip()
except Exception:
    pass

data = {
    "host": host,
    "timestamp": now,
    "os": os_release,
    "kernel": run(["uname", "-r"]),
    "arch": run(["uname", "-m"]),
    "uptime": run(["uptime", "-p"]),
    "cpu": {
        "model": cpu_model,
        "cores": cores,
        "threads_per_core": threads_per_core
    },
    "memory": {
        "total": mem_total,
        "used": mem_used,
        "available": mem_avail
    },
    "loadavg": loadavg,
    "storage": storage,
    "network": {
        "addresses": ips,
        "routes": routes
    }
}

print(json.dumps(data, indent=2, ensure_ascii=False))
PY

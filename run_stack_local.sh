
#!/usr/bin/env bash
set -euo pipefail


BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$BASE_DIR/logs"
PID_DIR="$BASE_DIR/pids"

mkdir -p "$LOG_DIR" "$PID_DIR"

LOG_FILE="$LOG_DIR/run_stack_local.log"
exec > >(tee -a "$LOG_FILE") 2>&1

HOST_SHORT="$(uname -n)"
case "$HOST_SHORT" in
  lnx200nas) CLUSTER_HOST="100.100.1.200" ;;
  lnx202pc)  CLUSTER_HOST="100.100.1.202" ;;
  lnx203hp)  CLUSTER_HOST="100.100.1.203" ;;
  *)
    echo "[fail] unknown host: $HOST_SHORT"
    exit 1
    ;;
esac

PIDS=()

port_in_use() {
  local port="$1"
  if command -v ss >/dev/null 2>&1; then
    ss -ltn "( sport = :$port )" | tail -n +2 | grep -q .
  elif command -v lsof >/dev/null 2>&1; then
    lsof -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
  else
    return 1
  fi
}

die_if_port_busy() {
  local port="$1"
  local name="$2"
  if port_in_use "$port"; then
    echo "[fail] port $port is already in use ($name)"
    exit 1
  fi
}

ensure_venv() {
  local dir="$1"
  if [[ ! -x "$dir/.venv/bin/python" ]]; then
    echo "[fail] missing venv in $dir (.venv/bin/python)"
    exit 1
  fi
}

start_bg() {
  local name="$1"
  shift
  local logfile="$LOG_DIR/${name}.log"
  local pidfile="$PID_DIR/${name}.pid"

  echo "[start] $name"
  "$@" >"$logfile" 2>&1 &
  local pid=$!
  echo "$pid" >"$pidfile"
  PIDS+=("$pid")
  echo "[ok] $name pid=$pid log=$logfile"
}

wait_http() {
  local url="$1"
  local name="$2"
  local tries="${3:-60}"

  echo "[wait_http] $name $url tries=$tries"

  for i in $(seq 1 "$tries"); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      echo "[ready] $name"
      return 0
    fi
    echo "[wait_http] attempt=$i not ready yet"
    sleep 1
  done

  echo "[fail] $name not ready: $url"
  return 1
}

stop_all() {
  echo "[stop] shutting down..."

  for pid in "${PIDS[@]:-}"; do
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
    fi
  done

  sleep 2

  for pid in "${PIDS[@]:-}"; do
    if kill -0 "$pid" 2>/dev/null; then
      kill -9 "$pid" 2>/dev/null || true
    fi
  done

  if [[ -d "$BASE_DIR/AuthMayhem" ]]; then
    (cd "$BASE_DIR/AuthMayhem" && docker compose down) || true
  fi
}

trap stop_all EXIT INT TERM

CLUSTER_DIR="$BASE_DIR/ClusterMayhem"
GEO_DIR="$BASE_DIR/GeoMayhem"
AUTH_DIR="$BASE_DIR/AuthMayhem"

CLUSTER_PY="$CLUSTER_DIR/.venv/bin/python"
GEO_PY="$GEO_DIR/.venv/bin/python"
GEO_UVICORN="$GEO_DIR/.venv/bin/uvicorn"

die_if_port_busy 5000 "GeoMayhem"
die_if_port_busy 7000 "ClusterMayhem"

ensure_venv "$CLUSTER_DIR"
ensure_venv "$GEO_DIR"

echo "[info] host=$HOST_SHORT cluster_host=$CLUSTER_HOST"

echo "[info] launching ClusterMayhem on $CLUSTER_HOST:7000"
start_bg "clustermayhem" bash -lc "cd '$CLUSTER_DIR' && '$CLUSTER_PY' -m cluster.runtime.node_boot"
wait_http "http://$CLUSTER_HOST:7000/health" "ClusterMayhem" 120

echo "[info] launching GeoMayhem worker"
start_bg "geomayhem-worker" bash -lc "cd '$GEO_DIR' && '$GEO_PY' -m backend.worker.distributor"

echo "[info] launching GeoMayhem api"
start_bg "geomayhem-api" bash -lc "cd '$GEO_DIR' && '$GEO_UVICORN' backend.main:app --host 0.0.0.0 --port 5000"
wait_http "http://$CLUSTER_HOST:5000/api/health" "GeoMayhem" 120

echo "[info] launching AuthMayhem"
(
  cd "$AUTH_DIR"
  docker compose up -d --build
) | tee "$LOG_DIR/authmayhem-compose.log"

echo "[ready] stack up"
wait

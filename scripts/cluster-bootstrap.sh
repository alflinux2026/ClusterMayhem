# File: scripts/cluster-bootstrap.sh
# Previous: none
# Author: alftorres
# Date: 2026-05-13T16:43:32+0200
# Version: 0.0.0
# Genealogy:
#   scripts/cluster-bootstrap.sh 0.0.0 2026-05-13T16:43:32+0200
#   God
#
# Purpose:
# Notes:
#
# FRV-ID: befeb247ebd54406
# Header_End

#!/usr/bin/env bash
# ============================================================================
# File: scripts/bootstrap_repo.sh
# Version: 0.1.0
# Purpose:
#   Bootstrap limpio de mayhem-cluster
# ============================================================================

set -euo pipefail

PROJECT="mayhem-cluster"

echo
echo "============================================================"
echo "BOOTSTRAP :: ${PROJECT}"
echo "============================================================"
echo

# ----------------------------------------------------------------------------
# DIRECTORIOS
# ----------------------------------------------------------------------------

mkdir -p \
    contracts \
    docs \
    spec \
    state \
    scripts \
    tests \
    cluster/config \
    cluster/node \
    cluster/election \
    cluster/watchdog \
    cluster/replication \
    cluster/datasets \
    cluster/storage \
    cluster/api \
    cluster/runtime \
    cluster/network \
    cluster/logging \
    cluster/workers \
    cluster/models

# ----------------------------------------------------------------------------
# PYTHON PACKAGE MARKERS
# ----------------------------------------------------------------------------

find cluster -type d -exec touch {}/__init__.py \;

# ----------------------------------------------------------------------------
# GITIGNORE
# ----------------------------------------------------------------------------

cat > .gitignore << 'EOF'
# Python
__pycache__/
*.pyc
*.pyo
*.pyd
.venv/
venv/

# Runtime
state/runtime/
state/cache/
state/tmp/
logs/

# Editors
.vscode/
.idea/

# OS
.DS_Store
Thumbs.db

# Local overrides
*.local.json
EOF

# ----------------------------------------------------------------------------
# README
# ----------------------------------------------------------------------------

cat > README.md << 'EOF'
# mayhem-cluster

Distributed autonomous failover cluster for LAN services.

## Goals

- autonomous election
- watchdog
- leases
- replication
- failover
- dataset consistency
- split-brain minimization

## Status

Experimental.
EOF

# ----------------------------------------------------------------------------
# PYPROJECT
# ----------------------------------------------------------------------------

cat > pyproject.toml << 'EOF'
[project]
name = "mayhem-cluster"
version = "0.1.0"
description = "Distributed autonomous failover cluster"
requires-python = ">=3.11"

dependencies = [
    "flask",
    "requests"
]
EOF

# ----------------------------------------------------------------------------
# EMPTY MODULES
# ----------------------------------------------------------------------------

touch \
    cluster/runtime/state.py \
    cluster/runtime/locks.py \
    cluster/models/host.py \
    cluster/models/lease.py \
    cluster/models/dataset.py \
    cluster/storage/backend.py \
    cluster/storage/json_backend.py \
    cluster/election/election_engine.py \
    cluster/election/lease_validation.py \
    cluster/watchdog/watchdog.py \
    cluster/watchdog/healthcheck.py \
    cluster/replication/replication_engine.py \
    cluster/replication/pull_sync.py \
    cluster/datasets/dataset_manager.py \
    cluster/datasets/revisioning.py \
    cluster/api/routes_health.py \
    cluster/api/routes_cluster.py \
    cluster/network/http_client.py \
    cluster/logging/cluster_logger.py \
    cluster/workers/watchdog_worker.py \
    cluster/workers/replication_worker.py \
    cluster/workers/lease_worker.py

# ----------------------------------------------------------------------------
# RUNTIME STRUCTURE
# ----------------------------------------------------------------------------

mkdir -p \
    state/snapshots \
    state/history \
    state/runtime \
    state/leases \
    state/datasets

# ----------------------------------------------------------------------------
# INITIAL JSON DATASETS
# ----------------------------------------------------------------------------

cat > state/datasets/hosts.json << 'EOF'
{
  "dataset": "hosts",
  "revision": 0,
  "updated_at": null,
  "source_node": null,
  "lease_owner": null,
  "checksum": null,
  "items": []
}
EOF

cat > state/datasets/cluster.json << 'EOF'
{
  "cluster": "mayhem-cluster",
  "version": "0.1.0",
  "active_node": null,
  "lease_owner": null,
  "updated_at": null
}
EOF

# ----------------------------------------------------------------------------
# GIT INIT
# ----------------------------------------------------------------------------

if [ ! -d .git ]; then
    git init
    git branch -M main
fi

# ----------------------------------------------------------------------------
# FINAL
# ----------------------------------------------------------------------------

echo
echo "Bootstrap completed."
echo
echo "Suggested next steps:"
echo
echo "  python3 -m venv .venv"
echo "  source .venv/bin/activate"
echo "  pip install -e ."
echo
echo "Repository ready."
echo

#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
.venv/bin/python scripts/edge_init.py "${@}"
docker build -f deployment/edge/Dockerfile.api -t twinguard-edge-api:local .
docker build -f deployment/edge/Dockerfile.worker -t twinguard-edge-worker:local .
docker build -f deployment/edge/Dockerfile.frontend -t twinguard-edge-frontend:local .

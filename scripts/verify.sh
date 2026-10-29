#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
.venv/bin/python -m pytest backend/tests -q
.venv/bin/python scripts/export_api.py
npm --prefix frontend run types:api
npm --prefix frontend run typecheck
npm --prefix frontend run build
npm --prefix frontend run e2e

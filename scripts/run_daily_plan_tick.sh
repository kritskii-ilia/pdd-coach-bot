#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="/home/user/pdd-coach-bot"

cd "$PROJECT_ROOT"

set -a
source "$PROJECT_ROOT/.env"
set +a

source "$PROJECT_ROOT/.venv/bin/activate"

exec python scripts/send_daily_plans.py

#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="/home/user/pdd-coach-bot"
SERVICE_NAME="pdd-coach-bot.service"
DAILY_PLAN_SERVICE_NAME="pdd-coach-daily-plan.service"
DAILY_PLAN_TIMER_NAME="pdd-coach-daily-plan.timer"
UNIT_SOURCE="$PROJECT_ROOT/deploy/systemd/$SERVICE_NAME"
UNIT_TARGET="/etc/systemd/system/$SERVICE_NAME"
DAILY_PLAN_SERVICE_SOURCE="$PROJECT_ROOT/deploy/systemd/$DAILY_PLAN_SERVICE_NAME"
DAILY_PLAN_SERVICE_TARGET="/etc/systemd/system/$DAILY_PLAN_SERVICE_NAME"
DAILY_PLAN_TIMER_SOURCE="$PROJECT_ROOT/deploy/systemd/$DAILY_PLAN_TIMER_NAME"
DAILY_PLAN_TIMER_TARGET="/etc/systemd/system/$DAILY_PLAN_TIMER_NAME"

if [[ ! -f "$UNIT_SOURCE" ]]; then
  echo "Unit file not found: $UNIT_SOURCE" >&2
  exit 1
fi
if [[ ! -f "$DAILY_PLAN_SERVICE_SOURCE" || ! -f "$DAILY_PLAN_TIMER_SOURCE" ]]; then
  echo "Daily plan units not found in $PROJECT_ROOT/deploy/systemd" >&2
  exit 1
fi

chmod +x "$PROJECT_ROOT/scripts/run_bot.sh"
chmod +x "$PROJECT_ROOT/scripts/run_daily_plan_tick.sh"
cp "$UNIT_SOURCE" "$UNIT_TARGET"
cp "$DAILY_PLAN_SERVICE_SOURCE" "$DAILY_PLAN_SERVICE_TARGET"
cp "$DAILY_PLAN_TIMER_SOURCE" "$DAILY_PLAN_TIMER_TARGET"
systemctl daemon-reload
systemctl enable --now "$SERVICE_NAME"
systemctl enable --now "$DAILY_PLAN_TIMER_NAME"
systemctl status "$SERVICE_NAME" --no-pager
systemctl status "$DAILY_PLAN_TIMER_NAME" --no-pager

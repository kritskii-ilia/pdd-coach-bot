#!/usr/bin/env bash
set -euo pipefail

journalctl -u pdd-coach-bot.service -n 100 --no-pager

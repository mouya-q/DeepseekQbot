#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$ROOT/bot/data" "$ROOT/bot/logs"
PID_FILE="$ROOT/bot/data/panel.pid"
if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE" 2>/dev/null || echo 0)" 2>/dev/null; then
  echo "DeepseekQbot 面板已经运行：http://127.0.0.1:${QBOT_PANEL_PORT:-3108}"
  exit 0
fi
cd "$ROOT"
nohup python3 -u "$ROOT/panel_server.py" >> "$ROOT/bot/logs/panel.log" 2>&1 < /dev/null &
PID=$!
echo "$PID" > "$PID_FILE"
chmod 600 "$PID_FILE" 2>/dev/null || true
sleep 0.5
if kill -0 "$PID" 2>/dev/null; then
  echo "DeepseekQbot 面板已启动：http://127.0.0.1:${QBOT_PANEL_PORT:-3108}"
  echo "在 DeepseekQbot App 或手机浏览器打开上方地址。"
  echo "机器人可在面板中启动；日志：$ROOT/bot/logs/panel.log"
else
  echo "面板启动失败，请检查 $ROOT/bot/logs/panel.log" >&2
  exit 1
fi

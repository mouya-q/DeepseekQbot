#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$ROOT/bot/data/panel.pid"
python3 - "$ROOT" <<'PY'
import os, signal, sys, time
from pathlib import Path
root = str(Path(sys.argv[1]).resolve())
targets = []
for ent in Path('/proc').iterdir():
    if not ent.name.isdigit():
        continue
    try:
        cmd = (ent / 'cmdline').read_bytes().replace(b'\0', b' ').decode('utf-8', 'ignore')
        if root in cmd and (root + '/bot/main.py') in cmd and 'stop.sh' not in cmd:
            targets.append(int(ent.name))
    except OSError:
        pass
for pid in targets:
    try: os.kill(pid, signal.SIGTERM)
    except OSError: pass
for _ in range(20):
    if not any(Path(f'/proc/{p}').exists() for p in targets): break
    time.sleep(.1)
for pid in targets:
    if Path(f'/proc/{pid}').exists():
        try: os.kill(pid, signal.SIGKILL)
        except OSError: pass
PY
if [[ -f "$PID_FILE" ]]; then
  PID="$(cat "$PID_FILE" 2>/dev/null || echo 0)"
  if kill -0 "$PID" 2>/dev/null; then kill "$PID" 2>/dev/null || true; fi
  rm -f "$PID_FILE"
fi
echo "DeepseekQbot 面板与本项目机器人进程已发送停止信号。"

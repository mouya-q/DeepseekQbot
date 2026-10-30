#!/usr/bin/env python3
"""Watchdog (supervisor) for 大肥鱼 QQ bot — pure Python stdlib.

Node.js cannot run in this proot container (uv_thread_create fails),
so the original supervisor.mjs is rewritten in Python.

Checks every 30s:
  - QQ/NapCat alive (HTTP 3000 get_login_info) → restart QQ if dead
  - Bot alive (pgrep main.py) → restart bot if dead
Every 60s:
  - Session stall detection (10 min no progress → restart bot)
Every 5 min:
  - Memory warning (< 2GB free)
  - Log rotation (> 5MB)
Every hour:
  - Backup to /sdcard/DSHA_backup/ (phone storage survives app data clear)
"""

import json
import os
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import DATA_DIR, LOG_DIR, ROOT_DIR, LOG_FILE, STATE_FILE, load_json, save_json, get_app_config

BOT_DIR = os.path.dirname(os.path.abspath(__file__))
SUP_DIR = os.path.dirname(os.path.abspath(__file__))
BACKUP_DIR = os.environ.get("QBOT_BACKUP_DIR", os.path.join(ROOT_DIR, "backups"))
QQ_DIR = os.environ.get("NAPCAT_QQ_DIR", "/root/Napcat/opt/QQ")

CHECK_INTERVAL = 30
STALL_INTERVAL = 60
MEM_INTERVAL = 300
LOG_INTERVAL = 300
BACKUP_INTERVAL = 3600

LOG_MAX_BYTES = 5 * 1024 * 1024
MEM_WARN_BYTES = 2 * 1024 * 1024 * 1024


def log(msg):
    print(f"[supervisor] {time.strftime('%H:%M:%S')} {msg}", flush=True)


def run_shell(cmd: str, timeout: int = 10) -> tuple:
    """Run a shell command, return (returncode, stdout, stderr). Never raises."""
    try:
        p = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except Exception as e:
        return -1, "", str(e)


def pgrep(pattern: str) -> bool:
    rc, out, _ = run_shell(f"pgrep -f '{pattern}'")
    return rc == 0 and bool(out)


def napcat_alive() -> bool:
    try:
        import urllib.request

        url = get_app_config()["napcat_http_url"].rstrip("/") + "/get_login_info"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "DeepseekQbot/1.0"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("status") == "ok"
    except Exception:
        return False


def start_qq():
    """QQ cannot run inside proot (pthread_create: Invalid argument).
    Remind the user to start QQ on the Android side instead."""
    log("⚠️ QQ 客户端无法在 proot 内启动（pthread_create: Invalid argument）")
    log("  请在 Android 侧启动 QQ + NapCat，面板会自动检测连接状态。")
    return False


def start_bot():
    log("🔄 重启大肥鱼 Bot…")
    target = os.path.realpath(os.path.join(BOT_DIR, "main.py"))
    pids = []
    for ent in os.scandir("/proc"):
        if not ent.name.isdigit():
            continue
        try:
            cmd = open(os.path.join(ent.path, "cmdline"), "rb").read().replace(b"\0", b" ").decode("utf-8", "ignore")
            if target in cmd and "supervisor.py" not in cmd:
                pids.append(int(ent.name))
        except OSError:
            continue
    for pid in pids:
        try: os.kill(pid, 15)
        except OSError: pass
    time.sleep(1)
    os.makedirs(LOG_DIR, exist_ok=True)
    out = open(LOG_FILE, "a", encoding="utf-8")
    try:
        proc = subprocess.Popen(
            [sys.executable, target], cwd=BOT_DIR, stdin=subprocess.DEVNULL,
            stdout=out, stderr=subprocess.STDOUT, start_new_session=True, close_fds=True,
        )
    finally:
        out.close()
    time.sleep(0.5)
    if proc.poll() is None:
        log(f"✓ Bot 已启动 (PID {proc.pid})")
        return True
    log(f"❌ Bot 启动失败，退出码 {proc.returncode}")
    return False


def free_memory_bytes() -> int:
    try:
        with open("/proc/meminfo") as f:
            info = {}
            for line in f:
                if ":" in line:
                    k, v = line.split(":", 1)
                    info[k.strip()] = int(v.split()[0]) * 1024
            return info.get("MemAvailable", 0)
    except Exception:
        return 0


def rotate_logs():
    if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > LOG_MAX_BYTES:
        ts = time.strftime("%Y%m%d-%H%M%S")
        backup = f"{LOG_FILE}.{ts}.gz"
        import gzip

        with open(LOG_FILE, "rb") as f_in:
            with gzip.open(backup, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
        open(LOG_FILE, "w").close()
        log(f"📄 日志已轮转: {backup}")


def do_backup():
    os.makedirs(BACKUP_DIR, exist_ok=True)
    files = [
        (os.path.join(BOT_DIR, "persona", "大肥鱼.md"), "persona_大肥鱼.md"),
        (os.path.join(BOT_DIR, "config.py"), "bot-config.py"),
        (os.path.join(BOT_DIR, "main.py"), "bot-main.py"),
        (os.path.join(BOT_DIR, "onebot.py"), "bot-onebot.py"),
        (os.path.join(BOT_DIR, "ai_engine.py"), "bot-ai_engine.py"),
        (os.path.join(BOT_DIR, "ws_client.py"), "bot-ws_client.py"),
        (os.path.join(BOT_DIR, "supervisor.py"), "supervisor.py"),
        (os.path.join(BOT_DIR, "dsha-responder.py"), "dsha-responder.py"),
        (STATE_FILE, "state.json"),
    ]
    for src, dst in files:
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(BACKUP_DIR, dst))
    # Also back up chat logs (most recent 3 days)
    import datetime

    today = datetime.date.today()
    for offset in range(3):
        d = today - datetime.timedelta(days=offset)
        src = os.path.join(DATA_DIR, "chat_logs", f"chat_{d.strftime('%Y-%m-%d')}.json")
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(BACKUP_DIR, f"chat_{d.strftime('%Y-%m-%d')}.json"))
    log(f"💾 备份完成 → {BACKUP_DIR}")


def check_stall():
    """Detect if the bot is stuck (no progress in 10 minutes)."""
    state = load_json(STATE_FILE, {})
    last = state.get("last_message_ts", 0)
    now = time.time()
    if last > 0 and now - last > 600:
        log("⚠️ 检测到 Bot 可能卡死（10分钟无消息），准备重启…")
        start_bot()
        state["last_stall_ts"] = now
        state["stall_count"] = state.get("stall_count", 0) + 1
        save_json(STATE_FILE, state)


def main():
    log("看门狗启动")
    log(f"  检查间隔: {CHECK_INTERVAL}s | 卡死检测: {STALL_INTERVAL}s")
    log(f"  内存告警: <{MEM_WARN_BYTES/1024/1024:.0f}MB | 日志轮转: >{LOG_MAX_BYTES/1024/1024}MB")

    last_stall = time.time()
    last_mem = time.time()
    last_log = time.time()
    last_backup = time.time()

    # Initial state
    state = load_json(STATE_FILE, {})
    state["supervisor_started"] = time.time()
    save_json(STATE_FILE, state)

    while True:
        try:
            now = time.time()

            # ── Every CHECK_INTERVAL ──
            if not napcat_alive():
                log("❌ NapCat 无响应")
                start_qq()
            if not pgrep("bot/main.py"):
                log("❌ Bot 进程消失")
                start_bot()
            state["last_message_ts"] = max(state.get("last_message_ts", 0), now)

            # ── Stall detection ──
            if now - last_stall >= STALL_INTERVAL:
                check_stall()
                last_stall = now

            # ── Memory warning ──
            if now - last_mem >= MEM_INTERVAL:
                free = free_memory_bytes()
                if free < MEM_WARN_BYTES:
                    log(f"⚠️ 内存告警: 剩余 {free/1024/1024:.0f}MB")
                else:
                    log(f"✓ 内存正常: {free/1024/1024:.0f}MB 可用")
                last_mem = now

            # ── Log rotation ──
            if now - last_log >= LOG_INTERVAL:
                rotate_logs()
                last_log = now

            # ── Hourly backup ──
            if now - last_backup >= BACKUP_INTERVAL:
                do_backup()
                last_backup = now

        except Exception as e:
            log(f"❌ 看门狗内部错误: {e}")

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("看门狗退出")
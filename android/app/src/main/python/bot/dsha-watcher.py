#!/usr/bin/env python3
"""dsha watcher — executes technical commands from the owner's private messages.

Design: this watcher does NOT try to pull history (OneBot v11 has no such API).
Instead, main.py writes every incoming private message to a shared queue file
(private-inbox.json), and this watcher picks it up, answers, and writes the
reply to private-outbox.json which main.py then sends.

Pure stdlib.
"""

import json
import os
import signal
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import STATE_FILE, load_json, save_json, get_app_config

INBOX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state", "private-inbox.json")
OUTBOX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state", "private-outbox.json")


def log(msg):
    print(f"[dsha-watcher] {time.strftime('%H:%M:%S')} {msg}", flush=True)


def execute_command(cmd: str) -> str:
    """Execute a technical/administrative command."""
    c = cmd.strip().lower()

    if any(k in c for k in ["余额", "money", "balance"]):
        return "余额查询未接入支付系统。老大你自己看面板吧。"
    if any(k in c for k in ["状态", "status", "健康", "alive", "运行"]):
        out = os.popen("pgrep -x qq >/dev/null 2>&1 && echo 'QQ: running' || echo 'QQ: down'").read().strip()
        out2 = os.popen("pgrep -f 'bot/main.py' >/dev/null 2>&1 && echo 'Bot: running' || echo 'Bot: down'").read().strip()
        out3 = os.popen("curl -s --max-time 3 http://127.0.0.1:3000/get_login_info | head -c 80").read().strip()
        return f"{out}\n{out2}\nNapCat: {out3}"
    if any(k in c for k in ["重启", "restart"]):
        bot_path = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py"))
        try:
            import subprocess
            for ent in os.scandir("/proc"):
                if not ent.name.isdigit():
                    continue
                try:
                    args = [x.decode("utf-8", "ignore") for x in open(os.path.join(ent.path, "cmdline"), "rb").read().split(b"\0") if x]
                    if bot_path in args and "dsha-watcher.py" not in args:
                        os.kill(int(ent.name), signal.SIGTERM)
                except OSError:
                    pass
            time.sleep(1)
            os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs"), exist_ok=True)
            log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "bot.log")
            with open(log_path, "a", encoding="utf-8") as log_file:
                subprocess.Popen([sys.executable, bot_path], cwd=os.path.dirname(bot_path),
                                 stdin=subprocess.DEVNULL, stdout=log_file, stderr=subprocess.STDOUT,
                                 start_new_session=True, close_fds=True)
            time.sleep(1)
            return "已发送重启命令；如未响应，检查 bot/logs/bot.log。"
        except Exception as exc:
            return f"重启失败：{exc}"
    if any(k in c for k in ["天气", "weather"]):
        return "查天气用 wttr.in/城市名 或 wttr.in/纬度,经度。要我帮你查哪个城市？"
    if any(k in c for k in ["日志", "log"]):
        try:
            with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "bot.log"), "r", encoding="utf-8") as f:
                lines = f.readlines()[-15:]
            return "".join(lines)
        except Exception as e:
            return f"读日志失败: {e}"
    if any(k in c for k in ["内存", "memory", "free"]):
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemAvailable"):
                        kb = int(line.split()[1])
                        return f"可用内存: {kb/1024:.0f} MB"
        except Exception as e:
            return f"查内存失败: {e}"
    if any(k in c for k in ["帮助", "help", "能干啥"]):
        return "命令：查余额 / 查状态 / 重启 / 查天气 / 查日志 / 查内存"
    if any(k in c for k in ["群号", "group"]):
        return "群号在 bot/config.py 的 ALLOWED_GROUPS 里。"

    return f"我不理解这个命令: {cmd[:40]}"


def process_inbox():
    """Read the inbox, answer owner's commands, write replies to outbox."""
    # Read owner_qq dynamically so panel changes take effect without restart
    owner_qq = get_app_config().get("owner_qq") or 0

    if not os.path.exists(INBOX):
        return

    try:
        with open(INBOX, "r", encoding="utf-8") as f:
            entries = json.load(f)
    except Exception:
        return

    if not isinstance(entries, list):
        return

    new_entries = []
    answered = []

    if not owner_qq:
        log("未设置管理者 QQ；已拒绝处理 DSH 指令，请在面板「权限与个性」中填写管理者 QQ。")
        return

    for entry in entries:
        user_id = entry.get("user_id")
        text = entry.get("text", "").strip()

        # Only answer the configured owner; do not auto-trust the first sender.
        if str(user_id) != str(owner_qq):
            new_entries.append(entry)
            continue

        log(f"收到老大指令: {text[:80]}")
        reply = execute_command(text)
        answered.append({"user_id": user_id, "reply": reply, "ts": time.time()})
        log(f"→ 答复: {reply[:80]}")

    # Keep unprocessed messages
    if new_entries:
        save_json(INBOX, new_entries)
    else:
        try:
            os.remove(INBOX)
        except Exception:
            pass

    # Write replies
    if answered:
        existing = load_json(OUTBOX, [])
        existing.extend(answered)
        save_json(OUTBOX, existing)


def main():
    log("dsha 监听器启动")
    log("等待主 bot 写入私聊消息队列…")

    while True:
        try:
            process_inbox()
        except Exception as e:
            log(f"处理出错: {e}")

        time.sleep(3)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("退出")
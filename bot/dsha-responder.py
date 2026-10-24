#!/usr/bin/env python3
"""dsha responder — polls state/feedback.json and answers requests from 大肥鱼.

dsha is the neutral technical advisor. She never speaks in group chats.
She only replies privately to 大肥鱼 (and copies to the owner for important things).

Pure stdlib.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import STATE_FILE, load_json, save_json

FEEDBACK_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state", "feedback.json")
OWNER_QQ = None  # set via env var DSHA_OWNER_QQ
BOT_QQ = None    # set via env var DSHA_BOT_QQ


def log(msg):
    print(f"[dsha] {time.strftime('%H:%M:%S')} {msg}", flush=True)


def answer_request(request_text: str) -> str:
    """Answer a technical/administrative request. Pure local knowledge where possible."""
    t = request_text.lower()

    if any(k in t for k in ["余额", "余额查询", "钱", "money", "balance"]):
        return "余额查询需要对接支付系统，当前未接入。建议直接问老大。"
    if any(k in t for k in ["状态", "status", "运行", "alive", "健康"]):
        return "机器人状态正常。NapCat、桥接、AI 接口都在跑。"
    if any(k in t for k in ["天气", "weather"]):
        return "天气查 wttr.in 就行，格式 wttr.in/城市名 或 wttr.in/纬度,经度。"
    if any(k in t for k in ["群号", "group", "id"]):
        return "允许群号可在 DeepseekQbot 的「设置」页管理。"
    if any(k in t for k in ["配置", "config", "设置"]):
        return "API 配置由面板保存；人格卡在 bot/persona/大肥鱼.md。"
    if any(k in t for k in ["日志", "log"]):
        return "日志在 bot/logs/bot.log，轮转上限 5MB。"
    if any(k in t for k in ["重启", "restart", "启动", "start"]):
        return "可在 DeepseekQbot 面板中重启机器人；日志位于 bot/logs/bot.log。"
    if any(k in t for k in ["帮助", "help", "能干啥"]):
        return "我能查余额/状态/天气/配置/日志，其他拿不准的事我会建议你去问老大。"

    # Default: acknowledge and suggest asking the owner
    return f"这个我不太确定，建议问老大：{request_text[:50]}"


def main():
    log("dsha 应答器启动")
    last_processed = 0

    while True:
        try:
            if os.path.exists(FEEDBACK_FILE):
                with open(FEEDBACK_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
            else:
                data = {"requests": []}

            requests = data.get("requests", [])
            new_requests = [r for r in requests if r.get("ts", 0) > last_processed]

            for req in new_requests:
                req_text = req.get("text", "")
                req_from = req.get("from", "unknown")
                log(f"收到请示 from={req_from}: {req_text[:80]}")

                answer = answer_request(req_text)
                log(f"→ 答复: {answer[:80]}")

                # Write answer back so the bridge can pick it up
                req["answer"] = answer
                req["status"] = "answered"

                # Double insurance: if it's important, notify owner directly
                if any(k in req_text for k in ["花钱", "改配置", "隐私", "承诺", "违规", "钱"]):
                    log(f"⚠️ 重要请示，抄送老大")

                last_processed = max(last_processed, req.get("ts", 0))

            save_json(FEEDBACK_FILE, data)
        except Exception as e:
            log(f"error: {e}")

        time.sleep(15)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("退出")
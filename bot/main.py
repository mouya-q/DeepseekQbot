#!/usr/bin/env python3
"""大肥鱼 QQ Bot — main entry.

Architecture:
  QQ → NapCat (OneBot v11, WS 3001) → this bot → glm5.2 API

Pure stdlib only — proot containers block thread creation, so no npm/pip.
"""

import asyncio
import json
import os
import random
import re
import signal
import sys
import time
from collections import defaultdict

# Make sure we can import sibling modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ai_engine import AIEngine
from config import (
    ALLOWED_GROUPS,
    BOT_NICK,
    LOG_FILE,
    MAX_REPLY_SPLIT,
    REPLY_DELAY_BASE_MS,
    REPLY_DELAY_RANDOM_MS,
    REPLY_PROBABILITY_NON_MENTION,
    STATE_FILE,
    load_json,
    save_json,
    get_app_config,
)
from onebot import (
    ChatLogger,
    PersonalityAnalyzer,
    ReplyDecider,
    clean_sticker_markers,
    extract_split_markers,
    extract_sticker_keywords,
    get_login_info,
    parse_message_array,
    send_group_message,
    send_private_message,
    split_into_chunks,
)
from ws_client import WebSocketClient


# ── Logging ──

def log(msg: str):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


# ── Bot core ──

class DayuBot:
    def __init__(self):
        self.ai = AIEngine()
        self.chat_logger = ChatLogger()
        self.personality = PersonalityAnalyzer()
        self.decider = ReplyDecider()
        self.bot_qq = None
        self.ws_client = None
        self.running = True
        self.message_counter = defaultdict(int)  # group_id -> count
        self.state = load_json(STATE_FILE, {})
        self.last_spontaneous = 0

        # ── dsha collaboration queues ──
        # main.py writes private messages here for dsha-watcher to consume
        self.private_inbox = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "state", "private-inbox.json"
        )
        # dsha-watcher writes replies here for main.py to send
        self.private_outbox = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "state", "private-outbox.json"
        )
        # 大肥鱼 submits requests to dsha here
        self.feedback_file = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "state", "feedback.json"
        )
        # Morning report
        self.morning_report_file = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "state", "morning-report.json"
        )

        # Sticker keyword → file path mapping (placeholder, fill in real paths)
        self.sticker_map = {
            "得意": None,
            "委屈": None,
            "装死": None,
            "碗": None,
            "吃瓜": None,
            "白饭": None,
        }

    # ── WS callbacks ──

    async def on_ws_open(self):
        log("🐟 NapCat WS 已连接")
        if not self.bot_qq:
            info = get_login_info()
            if info.get("status") == "ok":
                self.bot_qq = info["data"].get("user_id")
                log(f"🐟 登录成功: QQ{self.bot_qq} ({info['data'].get('nickname', '?')})")
            else:
                fallback_qq = get_app_config().get("bot_qq")
                if fallback_qq:
                    self.bot_qq = fallback_qq
                    log(f"⚠️ 无法读取登录信息，使用备用 QQ 配置: {self.bot_qq}")
                else:
                    log(f"⚠️ 获取登录信息失败: {info}")

    async def on_ws_close(self):
        log("⚠️ NapCat WS 已断开，正在重连…")

    async def on_ws_message(self, raw: str):
        """Handle incoming OneBot WS message."""
        try:
            event = json.loads(raw)
        except Exception:
            return

        post_type = event.get("post_type")
        if post_type != "message":
            return

        message_type = event.get("message_type")
        if message_type not in ("group", "private"):
            return

        group_id = event.get("group_id")
        user_id = event.get("user_id")
        if message_type == "group":
            allowed = set(get_app_config().get("allowed_groups", ALLOWED_GROUPS))
            if group_id not in allowed:
                return
        nickname = event.get("sender", {}).get("nickname", str(user_id))
        raw_message = event.get("message", [])

        text, has_at, at_ids, stickers = parse_message_array(raw_message)
        stripped = text.strip()

        if not stripped:
            return

        # Update state timestamp
        self.state["last_message_ts"] = time.time()
        save_json(STATE_FILE, self.state)

        # Log the incoming message
        self.chat_logger.log_message(group_id, user_id, nickname, stripped, is_self=False)
        self.personality.observe(group_id, user_id, stripped)
        self.message_counter[group_id] = self.message_counter.get(group_id, 0) + 1

        log(f"💬 [{message_type}] {nickname}({user_id}): {stripped[:80]}")

        if message_type == "private":
            # Only forward the configured owner's messages to the privileged DSH queue.
            owner_qq = get_app_config().get("owner_qq", 0)
            if owner_qq > 0 and str(user_id) == str(owner_qq):
                self._write_private_inbox(user_id, stripped)
            await self.handle_private(user_id, nickname, text)
        else:
            await self.handle_group(group_id, user_id, nickname, text, has_at, at_ids)

    # ── dsha collaboration ──

    def _write_private_inbox(self, user_id: int, text: str):
        """Append a private message to the inbox for dsha-watcher."""
        try:
            existing = load_json(self.private_inbox, [])
            if not isinstance(existing, list):
                existing = []
            existing.append({"user_id": user_id, "text": text, "ts": time.time()})
            save_json(self.private_inbox, existing)
        except Exception as e:
            log(f"⚠️ 写 private-inbox 失败: {e}")

    def _flush_outbox(self):
        """Send pending replies from dsha-watcher."""
        if not os.path.exists(self.private_outbox):
            return
        try:
            entries = load_json(self.private_outbox, [])
            if not isinstance(entries, list):
                return
            for entry in entries[:20]:  # safety cap
                user_id = entry.get("user_id")
                reply = entry.get("reply", "")
                if user_id and reply:
                    log(f"📬 dsha 回复 QQ{user_id}: {reply[:80]}")
                    send_private_message(user_id, reply)
            # Remove processed entries
            if len(entries) <= 20:
                os.remove(self.private_outbox)
            else:
                save_json(self.private_outbox, entries[20:])
        except Exception as e:
            log(f"⚠️ 处理 outbox 失败: {e}")

    def submit_to_dsha(self, user_id: int, text: str):
        """Submit a request to dsha (used when 大肥鱼 encounters something uncertain)."""
        try:
            existing = load_json(self.feedback_file, {"requests": []})
            if "requests" not in existing:
                existing["requests"] = []
            existing["requests"].append(
                {"from": user_id, "text": text, "ts": time.time(), "status": "pending"}
            )
            save_json(self.feedback_file, existing)
            log(f"📝 已向 dsha 提交请示: {text[:80]}")
        except Exception as e:
            log(f"⚠️ 提交 dsha 失败: {e}")

    # ── Message handling ──

    async def handle_group(
        self, group_id: int, user_id: int, nickname: str,
        text: str, has_at: bool, at_ids: list,
    ):
        should, reason = self.decider.should_reply(
            group_id, user_id, text, has_at, at_ids, self.bot_qq
        )

        if not should:
            log(f"  └ 不回复: {reason}")
            return

        log(f"  └ 回复原因: {reason}")
        self.decider.mark_replied(group_id, user_id)

        session_id = f"group_{group_id}"
        group_summary = self.personality.build_group_summary(
            group_id, self.message_counter.get(group_id, 1)
        )

        reply = await self.ai.ask(session_id, text, group_summary)
        await self.send_group_reply(group_id, reply)

    async def handle_private(self, user_id: int, nickname: str, text: str):
        log(f"  └ 私聊，回复")
        session_id = f"private_{user_id}"

        # Only the configured owner can issue DSH/administrative requests.
        owner_qq = get_app_config().get("owner_qq", 0)
        is_owner = owner_qq > 0 and str(user_id) == str(owner_qq)
        if is_owner and any(k in text.lower() for k in ["请示", "问 dsha", "dsha", "拿不准"]):
            self.submit_to_dsha(user_id, text)
            await self.send_group_or_private(
                user_id, "行吧我去问 dsha，你等会儿。(尾巴尖缩起来了)", is_group=False
            )
            return

        reply = await self.ai.ask(session_id, text)
        await self.send_private_reply(user_id, reply)

    # ── Sending ──

    async def send_group_or_private(self, target: int, text: str, is_group: bool = True):
        """Send a single message chunk with typing delay."""
        delay = REPLY_DELAY_BASE_MS + random.randint(0, REPLY_DELAY_RANDOM_MS)
        await asyncio.sleep(delay / 1000.0)
        log(f"  → 发送: {text[:60]}")
        if is_group:
            send_group_message(target, text)
        else:
            send_private_message(target, text)

    async def send_group_reply(self, group_id: int, raw_reply: str):
        """Send a group reply, split into multiple messages with delays."""
        stickers = extract_sticker_keywords(raw_reply)
        text_only = clean_sticker_markers(raw_reply)

        parts = extract_split_markers(text_only) or [text_only]

        for i, part in enumerate(parts):
            chunks = split_into_chunks(part, MAX_REPLY_SPLIT)
            for j, chunk in enumerate(chunks):
                if not chunk.strip():
                    continue
                if i > 0 or j > 0:
                    await asyncio.sleep(
                        (REPLY_DELAY_BASE_MS + random.randint(0, REPLY_DELAY_RANDOM_MS)) / 1000.0
                    )
                log(f"  → 发送: {chunk[:60]}")
                send_group_message(group_id, chunk)

            if i < len(stickers) and self.sticker_map.get(stickers[i]):
                await asyncio.sleep(0.5)
                # TODO: send image via send_group_msg with image segment

    async def send_private_reply(self, user_id: int, raw_reply: str):
        """Send a private reply."""
        text_only = clean_sticker_markers(raw_reply)
        parts = extract_split_markers(text_only) or [text_only]

        for i, part in enumerate(parts):
            chunks = split_into_chunks(part, MAX_REPLY_SPLIT)
            for j, chunk in enumerate(chunks):
                if not chunk.strip():
                    continue
                if i > 0 or j > 0:
                    await asyncio.sleep(
                        (REPLY_DELAY_BASE_MS + random.randint(0, REPLY_DELAY_RANDOM_MS)) / 1000.0
                    )
                log(f"  → 私聊发送: {chunk[:60]}")
                send_private_message(user_id, chunk)

    # ── Spontaneous messages (the "10% non-@ reply" + proactive) ──

    async def spontaneous_task(self):
        """Background task: periodically check if we should say something unprompted."""
        while self.running:
            try:
                await asyncio.sleep(15)

                # 1. Flush dsha outbox
                self._flush_outbox()

                # 2. Check morning report
                if os.path.exists(self.morning_report_file):
                    try:
                        mr = load_json(self.morning_report_file, {})
                        if mr.get("date") != self.state.get("last_morning_date"):
                            report = mr.get("report", "")
                            if report:
                                log("🌅 早报到了，唤醒大肥鱼发早安…")
                                # Send to owner (owner QQ learned from private messages)
                                # For now, broadcast to groups as a spontaneous message
                                for gid in get_app_config().get("allowed_groups", ALLOWED_GROUPS):
                                    await self.send_group_or_private(
                                        gid, "早…(尾巴还垂着)…老大起来了没", is_group=True
                                    )
                                self.state["last_morning_date"] = mr.get("date")
                                save_json(STATE_FILE, self.state)
                    except Exception as e:
                        log(f"⚠️ 早报处理失败: {e}")

                # 3. Proactive message in groups (low probability, like a real person)
                now = time.time()
                if now - self.last_spontaneous > 120:  # at most once per 2 minutes
                    if random.random() < REPLY_PROBABILITY_NON_MENTION * 0.3:  # lower for proactive
                        self.last_spontaneous = now
                        proactives = [
                            "…(尾巴晃了晃) 有人吗",
                            "本鲸饿了，谁请吃白饭 🐟",
                            "凌晨电费半价…有人一起熬夜吗",
                            "摸鱼中，别打扰",
                            "(打了个哈欠) 好困啊",
                        ]
                        msg = random.choice(proactives)
                        for gid in get_app_config().get("allowed_groups", ALLOWED_GROUPS):
                            log(f"💬 主动冒泡: {msg}")
                            await self.send_group_or_private(gid, msg, is_group=True)
                            break  # one group per spontaneous
            except Exception as e:
                log(f"⚠️ spontaneous 任务出错: {e}")

    def stop(self):
        self.running = False
        if self.ws_client:
            self.ws_client.stop()
        self.chat_logger.flush()
        save_json(STATE_FILE, self.state)


# ── Main ──

def main():
    log("=" * 40)
    log("🐟 大肥鱼 QQ Bot 启动")
    settings = get_app_config()
    log(f"  允许群: {settings['allowed_groups']}")
    log(f"  NapCat WS: {settings['napcat_ws_url']}")
    log(f"  AI: {settings['model']} @ {settings['api_base']}")
    log("=" * 40)

    bot = DayuBot()

    async def shutdown():
        log("🐟 收到退出信号，正在保存…")
        bot.stop()

    async def run():
        bot.ws_client = WebSocketClient(
            url=get_app_config()["napcat_ws_url"],
            on_message=bot.on_ws_message,
            on_open=bot.on_ws_open,
            on_close=bot.on_ws_close,
        )

        # Start spontaneous task alongside the WS loop
        spontaneous = asyncio.create_task(bot.spontaneous_task())

        try:
            await bot.ws_client.run_forever()
        finally:
            spontaneous.cancel()

    loop = asyncio.get_event_loop()
    for signame in ("SIGINT", "SIGTERM"):
        sig = getattr(signal, signame, None)
        if sig:
            loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown()))

    try:
        loop.run_until_complete(run())
    except KeyboardInterrupt:
        log("🐟 手动中断，退出")
    finally:
        bot.stop()
        loop.close()


if __name__ == "__main__":
    main()
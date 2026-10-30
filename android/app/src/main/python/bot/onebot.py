#!/usr/bin/env python3
"""OneBot v11 protocol layer + group personality analysis + chat persistence.

Pure stdlib: urllib.request for HTTP API, asyncio for WS.
"""

import asyncio
import json
import os
import random
import re
import time
from collections import defaultdict

from config import (
    ALLOWED_GROUPS,
    ALT_NICKS,
    ANALYZE_EVERY_N_MESSAGES,
    ANALYSIS_MIN_MESSAGES,
    BOT_NICK,
    CHAT_LOG_DIR,
    PERSONALITY_DIR,
    REPLY_COOLDOWN_S,
    REPLY_DELAY_BASE_MS,
    REPLY_DELAY_RANDOM_MS,
    REPLY_PROBABILITY_NON_MENTION,
    in_quiet_hours,
    load_json,
    save_json,
    get_app_config,
)
from ws_client import http_post_json_sync


# ── OneBot HTTP API wrappers ──

def _api_call(action: str, params: dict = None) -> dict:
    """Call NapCat HTTP API synchronously."""
    url = f"{get_app_config()['napcat_http_url']}/{action}"
    payload = params or {}
    status, text = http_post_json_sync(url, payload, timeout=10.0)
    if status != 200:
        return {"status": "failed", "retcode": status, "message": text}
    try:
        return json.loads(text)
    except Exception:
        return {"status": "failed", "message": text[:200]}


def send_group_message(group_id: int, message, auto_escape: bool = False) -> dict:
    """Send a group message."""
    return _api_call(
        "send_group_msg",
        {
            "group_id": group_id,
            "message": message,
            "auto_escape": auto_escape,
        },
    )


def send_private_message(user_id: int, message, auto_escape: bool = False) -> dict:
    """Send a private message."""
    return _api_call(
        "send_private_msg",
        {
            "user_id": user_id,
            "message": message,
            "auto_escape": auto_escape,
        },
    )


def send_group_message_with_bubble(group_id: int, message) -> dict:
    """Try to send without bubble (go_bubble) if supported."""
    return _api_call(
        "send_group_msg",
        {
            "group_id": group_id,
            "message": message,
            "auto_escape": False,
        },
    )


def get_login_info() -> dict:
    return _api_call("get_login_info")


def get_group_member_info(group_id: int, user_id: int) -> dict:
    return _api_call(
        "get_group_member_info",
        {"group_id": group_id, "user_id": user_id, "no_cache": True},
    )


def get_group_list() -> dict:
    return _api_call("get_group_list")


# ── Message parsing helpers ──

def parse_message_array(msg) -> tuple:
    """Parse OneBot message array into (plain_text, has_at_mention, at_user_ids, sticker_keywords)."""
    texts = []
    has_at = False
    at_ids = []
    stickers = []

    if isinstance(msg, str):
        return msg, False, [], []

    if isinstance(msg, list):
        for seg in msg:
            if not isinstance(seg, dict):
                continue
            seg_type = seg.get("type", "")
            data = seg.get("data", {})

            if seg_type == "text":
                texts.append(data.get("text", ""))
            elif seg_type == "at":
                has_at = True
                at_ids.append(str(data.get("qq", "")) or str(data.get("user_id", "")))
            elif seg_type == "image":
                stickers.append("image")
            elif seg_type == "face":
                stickers.append("face")

        full_text = "".join(texts)
        return full_text, has_at, at_ids, stickers

    return str(msg), False, [], []


def split_into_chunks(text: str, max_len: int = 300) -> list:
    """Split a long reply into multiple short messages like a real person."""
    # First try splitting on sentence boundaries
    if len(text) <= max_len:
        return [text]

    chunks = []
    # Split on Chinese sentence enders
    parts = re.split(r"(?<=[。！？！？……])", text)
    current = ""
    for part in parts:
        if len(current) + len(part) > max_len and current:
            chunks.append(current.strip())
            current = part
        else:
            current += part
    if current.strip():
        chunks.append(current.strip())

    # Fallback: hard split
    if not chunks:
        for i in range(0, len(text), max_len):
            chunks.append(text[i : i + max_len])

    return chunks[:10]  # safety cap


def extract_sticker_keywords(text: str) -> list:
    """Extract [sticker: keyword] markers from AI reply."""
    return re.findall(r"\[sticker:\s*([^\]]+)\]", text)


def clean_sticker_markers(text: str) -> str:
    """Remove [sticker: ...] markers from the message text."""
    return re.sub(r"\[sticker:[^\]]*\]", "", text).strip()


def extract_split_markers(text: str) -> list:
    """Split AI reply on [split] markers."""
    parts = re.split(r"\[split\]", text)
    return [p.strip() for p in parts if p.strip()]


# ── Chat log persistence ──

class ChatLogger:
    """Persist every message to JSON files, grouped by date."""

    def __init__(self):
        self.current_date = None
        self.current_file = None
        self.current_log = []

    def _get_file(self, date_str: str) -> str:
        return os.path.join(CHAT_LOG_DIR, f"chat_{date_str}.json")

    def log_message(self, group_id: int, user_id: int, nickname: str, content: str, is_self: bool = False):
        """Append a message to today's log."""
        import datetime

        now = datetime.datetime.now()
        date_str = now.strftime("%Y-%m-%d")

        if date_str != self.current_date:
            # Save previous day's log
            if self.current_file:
                save_json(self.current_file, self.current_log)
            self.current_date = date_str
            self.current_file = self._get_file(date_str)
            self.current_log = load_json(self.current_file, [])

        entry = {
            "time": now.strftime("%H:%M:%S"),
            "group_id": group_id,
            "user_id": user_id,
            "nickname": nickname,
            "self": is_self,
            "content": content,
        }
        self.current_log.append(entry)

        # Flush every 20 messages
        if len(self.current_log) % 20 == 0:
            save_json(self.current_file, self.current_log)

    def flush(self):
        if self.current_file:
            save_json(self.current_file, self.current_log)

    def get_recent_messages(self, group_id: int, limit: int = 100) -> list:
        """Get recent messages for a group across recent days."""
        import datetime

        result = []
        today = datetime.date.today()
        for offset in range(7):  # last 7 days
            d = today - datetime.timedelta(days=offset)
            f = self._get_file(d.strftime("%Y-%m-%d"))
            if os.path.exists(f):
                logs = load_json(f, [])
                for entry in logs:
                    if entry.get("group_id") == group_id:
                        result.append(entry)
                if len(result) >= limit:
                    break
        return result[-limit:]


# ── Group personality analysis ──

class PersonalityAnalyzer:
    """Analyze group members' personalities from chat history."""

    PERSONALITY_TRAITS = [
        "话痨", "高冷", "沙雕", "认真", "暴躁", "温柔", "杠精", "潜水",
        "爱分享", "技术宅", "吃货", "夜猫子", "早起鸟", "爱哭", "乐观",
    ]

    def __init__(self):
        self.message_counts = defaultdict(int)  # (group_id, user_id) -> count
        self.night_counts = defaultdict(int)    # messages between 0-6am
        self.word_counts = defaultdict(lambda: defaultdict(int))
        self.last_active = {}

    def observe(self, group_id: int, user_id: int, content: str, timestamp=None):
        """Record a message for analysis."""
        key = (group_id, user_id)
        self.message_counts[key] += 1
        self.last_active[key] = time.time()

        # Track certain words
        for w in ["哈哈", "笑", "草", "6", "牛逼", "傻逼", "滚", "谢谢", "在吗"]:
            if w in content:
                self.word_counts[key][w] += 1

        # Track night owl
        if timestamp is None:
            import datetime
            hour = datetime.datetime.now().hour
        else:
            hour = timestamp.hour if hasattr(timestamp, "hour") else 0
        if 0 <= hour < 6:
            self.night_counts[key] += 1

    def analyze(self, group_id: int, user_id: int, total_messages: int) -> dict:
        """Generate a personality profile for a user in a group."""
        key = (group_id, user_id)
        count = self.message_counts.get(key, 0)

        if count < ANALYSIS_MIN_MESSAGES:
            return None

        ratio = count / max(total_messages, 1)

        traits = []
        if ratio > 0.15:
            traits.append("话痨")
        elif ratio < 0.01:
            traits.append("潜水")

        if self.night_counts.get(key, 0) > 5:
            traits.append("夜猫子")

        words = self.word_counts.get(key, {})
        if words.get("哈哈", 0) + words.get("笑", 0) > count * 0.1:
            traits.append("乐观")
        if words.get("草", 0) + words.get("6", 0) > count * 0.05:
            traits.append("沙雕")
        if words.get("牛逼", 0) + words.get("傻逼", 0) > 0:
            traits.append("暴躁")
        if words.get("谢谢", 0) > count * 0.05:
            traits.append("温柔")

        return {
            "user_id": user_id,
            "message_count": count,
            "activity_ratio": round(ratio, 3),
            "traits": traits,
            "last_active": self.last_active.get(key),
        }

    def build_group_summary(self, group_id: int, total_messages: int) -> str:
        """Build a readable summary of group personalities."""
        profiles = []
        for (gid, uid), count in self.message_counts.items():
            if gid != group_id:
                continue
            profile = self.analyze(group_id, uid, total_messages)
            if profile and len(profile["traits"]) > 0:
                profiles.append(profile)

        if not profiles:
            return ""

        lines = ["【群友个性】"]
        for p in sorted(profiles, key=lambda x: -x["message_count"])[:8]:
            lines.append(f"QQ{p['user_id']}: {','.join(p['traits'])}（发了{p['message_count']}条）")
        return "\n".join(lines)


# ── Reply decision engine ──

class ReplyDecider:
    """Decide whether to reply to a message."""

    def __init__(self):
        self.last_reply = {}  # (group_id, user_id) -> timestamp

    def should_reply(
        self,
        group_id: int,
        user_id: int,
        text: str,
        has_at: bool,
        at_ids: list,
        bot_qq: int,
    ) -> tuple:
        """Returns (should_reply: bool, reason: str).

        Settings are read from the live config on every call so edits made in
        the app take effect immediately instead of at the next restart.
        """
        now = time.time()
        cfg = get_app_config()

        # 1. Not our group
        allowed_groups = set(cfg.get("allowed_groups", ALLOWED_GROUPS))
        if group_id not in allowed_groups:
            return False, "不在允许的群"

        # 2. Self message
        if user_id == bot_qq:
            return False, "自己的消息"

        # 3. @ mention → must reply (always, even during quiet hours)
        if has_at and str(bot_qq) in [str(a) for a in at_ids]:
            return True, "被@了"

        # 4. Mention by nickname → must reply
        nick_patterns = [cfg.get("bot_nick", BOT_NICK)] + list(ALT_NICKS)
        for n in nick_patterns:
            if n and n in text:
                return True, f"被提到名字({n})"

        # 5. Quiet hours: only direct address gets through.
        if in_quiet_hours(now):
            return False, "安静时段"

        # 6. Cooldown
        key = (group_id, user_id)
        cooldown = cfg.get("reply_cooldown_s", REPLY_COOLDOWN_S)
        if key in self.last_reply and now - self.last_reply[key] < cooldown:
            return False, "冷却中"

        # 7. Random probability for non-mentioned messages
        probability = cfg.get("reply_probability", REPLY_PROBABILITY_NON_MENTION)
        if random.random() < probability:
            return True, f"随机({probability:.0%})"

        return False, "概率未命中"

    def mark_replied(self, group_id: int, user_id: int):
        self.last_reply[(group_id, user_id)] = time.time()
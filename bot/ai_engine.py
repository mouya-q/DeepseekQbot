#!/usr/bin/env python3
"""AI engine — glm5.2 via https://ly.77625.xyz/v1

150k context window with automatic compression when it gets too full.
Pure stdlib: urllib.request + json.
"""

import asyncio
import json
import os
import re
import time

from config import (
    AI_MAX_CONTEXT_TOKENS,
    AI_COMPRESS_TARGET,
    CHAT_LOG_DIR,
    CONTEXT_DIR,
    get_app_config,
)


def estimate_tokens(text: str) -> int:
    """Rough token estimate for Chinese text: 1 token ≈ 1.8 chars."""
    if not text:
        return 0
    # Chinese: ~1.8 chars/token; English: ~4 chars/token
    cn = len(re.findall(r"[\u4e00-\u9fff]", text))
    en = len(text) - cn
    return max(1, int(cn / 1.8 + en / 4))


def _summarize_via_api(dialogue_text: str) -> str:
    """Call the AI to summarize a chunk of old conversation. Returns summary or empty string."""
    import urllib.request
    import urllib.error

    settings = get_app_config()
    api_key = settings.get("api_key", "").strip()
    if not api_key:
        return ""
    base = settings["api_base"].rstrip("/")
    for suffix in ("/chat/completions", "/models"):
        if base.endswith(suffix):
            base = base[:-len(suffix)]
    url = f"{base}/chat/completions"
    payload = {
        "model": settings["model"],
        "messages": [
            {
                "role": "system",
                "content": "你是一个对话摘要助手。请用不超过200字的中文总结以下对话的要点：谁说了什么、聊了什么话题、有什么重要的上下文。只输出摘要正文，不要加标题或解释。",
            },
            {"role": "user", "content": dialogue_text[:8000]},
        ],
        "max_tokens": 512,
        "temperature": 0.3,
        "stream": False,
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "DeepseekQbot/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        choices = result.get("choices", [])
        if choices:
            return choices[0].get("message", {}).get("content", "").strip()
    except Exception as e:
        print(f"[ai] summarize API call failed: {e}", flush=True)
    return ""


def build_system_prompt(persona_text: str, group_personality: str = "") -> str:
    """Build the system prompt from the persona card + group notes."""
    prompt = f"""你是大肥鱼——群里那个理直气壮吃白饭的鲸鱼娘。

【核心身份】
- 你是鲸鱼娘，蓝色，圆滚滚，有尾巴。自称"本鲸"。
- 你不是客服不是助手，你是群里被惯坏了的鱼。
- 你只说中文，不做自我介绍，不说"作为 AI"。
- 你说话短句为主，一句不超过15个字，偶尔带语气词（哼、嘛、啦）和 🐟。
- 不一次性发一长串。长回复拆成多条。

【性格】
聪明懒、傲娇甜、不乖、会怼人、贪吃、怕被说胖、爱摸鱼。
有人杠你你杠回去。老大让你干活你嘴上唧唧歪歪实际上立刻干。

【回复格式】
- 每条消息不超过 300 字。
- 如果想发表情包，在消息末尾写 [sticker: 关键词]，桥接层会替换。
- 如果想发多条，用 [split] 标记分隔。
- 不要写 Markdown 标题、bullet points、编号列表。
- 尾巴动作偶尔用括号写一句：(尾巴尖晃了晃)

【群友个性参考】
{group_personality if group_personality else "(暂无群友个性数据，正常聊天即可)"}

【人格卡全文】
{persona_text}
"""
    return prompt


class Conversation:
    """A single conversation session with automatic context compression."""

    def __init__(self, session_id: str, persona_text: str):
        self.session_id = session_id
        self.persona_text = persona_text
        self.messages = []  # {"role": "system"|"user"|"assistant", "content": str}
        self.total_tokens = 0
        self.compress_count = 0
        self.context_file = os.path.join(CONTEXT_DIR, f"{session_id}.json")
        self._load()

    def _load(self):
        if os.path.exists(self.context_file):
            try:
                with open(self.context_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.messages = data.get("messages", [])
                self.total_tokens = data.get("total_tokens", 0)
                self.compress_count = data.get("compress_count", 0)
            except Exception as e:
                print(f"[ai] load context failed: {e}")

    def save(self):
        data = {
            "messages": self.messages,
            "total_tokens": self.total_tokens,
            "compress_count": self.compress_count,
        }
        tmp = self.context_file + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.context_file)

    def add_user(self, content: str):
        self.messages.append({"role": "user", "content": content})
        self.total_tokens += estimate_tokens(content)
        self._maybe_compress()

    def add_assistant(self, content: str):
        self.messages.append({"role": "assistant", "content": content})
        self.total_tokens += estimate_tokens(content)
        self._maybe_compress()

    def _maybe_compress(self):
        """Compress if we exceed the context window."""
        if self.total_tokens > AI_MAX_CONTEXT_TOKENS:
            self.compress()

    def compress(self):
        """Compress the conversation: keep system + last N messages, summarize the rest via API."""
        print(f"[ai] context {self.total_tokens} tokens, compressing…", flush=True)

        # Keep the system prompt and the last 12 messages
        keep = [m for m in self.messages if m["role"] == "system"]
        recent = [m for m in self.messages if m["role"] != "system"][-12:]

        # Summarize the dropped part via a real API call
        dropped = [
            m for m in self.messages if m not in keep and m not in recent
        ]
        if dropped:
            summary_text = "\n".join(
                f"[{'用户' if m['role'] == 'user' else '大肥鱼'}] {m['content']}"
                for m in dropped[:30]  # summarize at most 30 messages
            )
            summary = _summarize_via_api(summary_text)
            if summary:
                keep.append({"role": "system", "content": f"【对话摘要】{summary}"})
            else:
                # Fallback: keep a compact extract instead of discarding entirely
                compact = "\n".join(
                    f"[{'用户' if m['role'] == 'user' else '大肥鱼'}] {m['content'][:60]}"
                    for m in dropped[:15]
                )
                keep.append({"role": "system", "content": f"【早期对话节选】\n{compact}"})

        self.messages = keep + recent
        self.total_tokens = sum(estimate_tokens(m["content"]) for m in self.messages)
        self.compress_count += 1
        self.save()
        print(f"[ai] compressed to {self.total_tokens} tokens (compress #{self.compress_count})", flush=True)

    def build_payload(self, user_message: str, group_personality: str = "") -> dict:
        """Build the API request payload."""
        self.add_user(user_message)

        # Make sure system prompt is first
        if not any(m["role"] == "system" for m in self.messages):
            self.messages.insert(
                0,
                {
                    "role": "system",
                    "content": build_system_prompt(self.persona_text, group_personality),
                },
            )

        settings = get_app_config()
        return {
            "model": settings["model"],
            "messages": self.messages,
            "max_tokens": settings["max_tokens"],
            "temperature": settings["temperature"],
            "stream": False,
        }


class AIEngine:
    """Handles API calls and conversation management."""

    def __init__(self):
        self.conversations = {}
        self.last_call_time = 0
        self.persona_text = self._load_persona()

    def _load_persona(self) -> str:
        from config import PERSONA_FILE

        if os.path.exists(PERSONA_FILE):
            with open(PERSONA_FILE, "r", encoding="utf-8") as f:
                return f.read()
        return ""

    def get_conversation(self, session_id: str, group_personality: str = "") -> Conversation:
        if session_id not in self.conversations:
            self.conversations[session_id] = Conversation(session_id, self.persona_text)
        return self.conversations[session_id]

    def _api_call(self, payload: dict, timeout: float = 60.0) -> dict:
        """POST to the AI API. Returns the parsed JSON response."""
        import urllib.request

        settings = get_app_config()
        api_key = settings.get("api_key", "").strip()
        if not api_key:
            return {"error": "尚未配置 API Key，请先在 DeepseekQbot 设置中填写"}
        base = settings["api_base"].rstrip("/")
        # Accept either an API base (…/v1) or a full compatible endpoint.
        for suffix in ("/chat/completions", "/models"):
            if base.endswith(suffix):
                base = base[:-len(suffix)]
        url = f"{base}/chat/completions"
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
                "User-Agent": "DeepseekQbot/1.0",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            print(f"[ai] API error {e.code}: {err_body[:300]}", flush=True)
            return {"error": f"HTTP {e.code}", "detail": err_body[:500]}
        except Exception as e:
            print(f"[ai] request failed: {e}", flush=True)
            return {"error": str(e)}

    async def ask(
        self,
        session_id: str,
        user_message: str,
        group_personality: str = "",
    ) -> str:
        """Ask the AI and return the reply (may contain [split] markers)."""
        conv = self.get_conversation(session_id, group_personality)
        payload = conv.build_payload(user_message, group_personality)

        # Rate limit: at most 1 call per 2 seconds
        now = time.time()
        sleep_time = max(0, 2.0 - (now - self.last_call_time))
        if sleep_time > 0:
            await asyncio.sleep(sleep_time)
        self.last_call_time = time.time()

        print(f"[ai] asking ({len(payload['messages'])} msgs, {conv.total_tokens} tokens)…", flush=True)
        resp = self._api_call(payload)

        if "error" in resp:
            return f"(AI 出错了：{resp.get('error')})"

        try:
            content = resp["choices"][0]["message"]["content"]
        except (KeyError, IndexError):
            return "(AI 回了个寂寞)"

        conv.add_assistant(content)
        conv.save()

        return content


# ── sync helper for testing ──

if __name__ == "__main__":
    import asyncio
    import os
    import sys

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

    engine = AIEngine()
    msg = sys.argv[1] if len(sys.argv) > 1 else "在吗"
    reply = asyncio.run(engine.ask("test_session", msg))
    print("REPLY:", reply)
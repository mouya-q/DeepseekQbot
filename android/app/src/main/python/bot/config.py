#!/usr/bin/env python3
"""Runtime configuration for DeepseekQbot; standard-library only.

Two layers:

* ``DEFAULT_APP_CONFIG`` holds every tunable. Anything the user can change in
  the app lives here, so new settings only need one entry.
* ``get_app_config()`` merges the persisted file over those defaults and
  normalises types, so callers can trust the shape.

Modules that need a tunable should call ``get_app_config()`` at use time
rather than importing a module-level constant: constants are read once at
import and would ignore later edits from the UI.
"""
import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)
DATA_DIR = os.path.join(BASE_DIR, "data")
LOG_DIR = os.path.join(BASE_DIR, "logs")
PERSONA_DIR = os.path.join(BASE_DIR, "persona")
PERSONA_FILE = os.path.join(PERSONA_DIR, "大肥鱼.md")
APP_CONFIG_FILE = os.path.join(DATA_DIR, "app_config.json")

for d in (DATA_DIR, LOG_DIR, PERSONA_DIR):
    os.makedirs(d, exist_ok=True)

# ── Identity defaults ────────────────────────────────────────────────────────

BOT_QQ = 3086657739
BOT_NICK = "大肥鱼"
ALT_NICKS = ["本鲸", "肥鱼", "鲸鱼娘"]
ALLOWED_GROUPS = [960636357]
NAPCAT_HTTP_URL = "http://127.0.0.1:3000"
NAPCAT_WS_URL = "ws://127.0.0.1:3001"

# ── AI defaults ──────────────────────────────────────────────────────────────

# API key is intentionally blank; enter your own key in the app.
AI_API_BASE = "https://ly.77625.xyz/v1"
AI_API_KEY = ""
AI_MODEL = "glm-5.2"
AI_MAX_CONTEXT_TOKENS = 130000
AI_COMPRESS_TARGET = 90000
AI_TEMPERATURE = 0.85
AI_MAX_TOKENS = 2048
AI_TIMEOUT_S = 60

# ── Behaviour defaults (all user-tunable) ────────────────────────────────────

REPLY_PROBABILITY_NON_MENTION = 0.10
REPLY_DELAY_BASE_MS = 800
REPLY_DELAY_RANDOM_MS = 1500
MAX_REPLY_SPLIT = 300
REPLY_COOLDOWN_S = 3
ANALYZE_EVERY_N_MESSAGES = 50
ANALYSIS_MIN_MESSAGES = 10

# Feature switches, all on by default except where noted.
FEATURE_PROACTIVE = True          # 主动冒泡
FEATURE_SPLIT_REPLY = True        # 长回复分段发送
FEATURE_TYPING_DELAY = True       # 模拟打字延迟
FEATURE_STICKER = True            # 解析并发送表情包
FEATURE_QUIET_HOURS = True        # 深夜安静时段
FEATURE_OWNER_COMMANDS = True     # 主人私聊指令
FEATURE_GROUP_ANALYSIS = True     # 群友个性分析

QUIET_HOURS_START = 2             # 凌晨 2 点
QUIET_HOURS_END = 7               # 到早上 7 点
PROACTIVE_MIN_INTERVAL_S = 120    # 主动冒泡最短间隔

LOG_FILE = os.path.join(LOG_DIR, "bot.log")
CHAT_LOG_DIR = os.path.join(DATA_DIR, "chat_logs")
PERSONALITY_DIR = os.path.join(DATA_DIR, "personalities")
CONTEXT_DIR = os.path.join(DATA_DIR, "contexts")
STATE_FILE = os.path.join(DATA_DIR, "state.json")
for d in (CHAT_LOG_DIR, PERSONALITY_DIR, CONTEXT_DIR):
    os.makedirs(d, exist_ok=True)


DEFAULT_APP_CONFIG = {
    # AI
    "api_base": AI_API_BASE,
    "api_key": "",
    "model": AI_MODEL,
    "max_tokens": AI_MAX_TOKENS,
    "temperature": AI_TEMPERATURE,
    "ai_timeout_s": AI_TIMEOUT_S,
    # OneBot
    "napcat_http_url": NAPCAT_HTTP_URL,
    "napcat_ws_url": NAPCAT_WS_URL,
    "napcat_qr_path": "",
    # Identity
    "bot_qq": BOT_QQ,
    "owner_qq": 3523172449,
    "bot_nick": BOT_NICK,
    "allowed_groups": ALLOWED_GROUPS,
    # Behaviour
    "reply_probability": REPLY_PROBABILITY_NON_MENTION,
    "reply_cooldown_s": REPLY_COOLDOWN_S,
    "reply_delay_base_ms": REPLY_DELAY_BASE_MS,
    "reply_delay_random_ms": REPLY_DELAY_RANDOM_MS,
    "max_reply_split": MAX_REPLY_SPLIT,
    "analyze_every_n": ANALYZE_EVERY_N_MESSAGES,
    "quiet_hours_start": QUIET_HOURS_START,
    "quiet_hours_end": QUIET_HOURS_END,
    "proactive_min_interval_s": PROACTIVE_MIN_INTERVAL_S,
    # Feature switches
    "feature_proactive": FEATURE_PROACTIVE,
    "feature_split_reply": FEATURE_SPLIT_REPLY,
    "feature_typing_delay": FEATURE_TYPING_DELAY,
    "feature_sticker": FEATURE_STICKER,
    "feature_quiet_hours": FEATURE_QUIET_HOURS,
    "feature_owner_commands": FEATURE_OWNER_COMMANDS,
    "feature_group_analysis": FEATURE_GROUP_ANALYSIS,
    # Custom persona additions (appended to the built-in card)
    "extra_persona": "",
    "sticker_keywords": {},
}

_BOOL_KEYS = (
    "feature_proactive",
    "feature_split_reply",
    "feature_typing_delay",
    "feature_sticker",
    "feature_quiet_hours",
    "feature_owner_commands",
    "feature_group_analysis",
)

_INT_KEYS = {
    "max_tokens": (1, 32768, AI_MAX_TOKENS),
    "ai_timeout_s": (5, 300, AI_TIMEOUT_S),
    "reply_cooldown_s": (0, 600, REPLY_COOLDOWN_S),
    "reply_delay_base_ms": (0, 20000, REPLY_DELAY_BASE_MS),
    "reply_delay_random_ms": (0, 20000, REPLY_DELAY_RANDOM_MS),
    "max_reply_split": (50, 2000, MAX_REPLY_SPLIT),
    "analyze_every_n": (5, 5000, ANALYZE_EVERY_N_MESSAGES),
    "quiet_hours_start": (0, 23, QUIET_HOURS_START),
    "quiet_hours_end": (0, 23, QUIET_HOURS_END),
    "proactive_min_interval_s": (30, 7200, PROACTIVE_MIN_INTERVAL_S),
}

_FLOAT_KEYS = {
    "temperature": (0.0, 2.0, AI_TEMPERATURE),
    "reply_probability": (0.0, 1.0, REPLY_PROBABILITY_NON_MENTION),
}


def load_persona_text():
    """Load the persona card.

    Order of preference:
    1. ``bot/data/persona_override.md`` — user-edited copy in writable storage.
    2. ``bot/persona/大肥鱼.md`` — checked-in card next to the sources.
    3. ``persona_builtin.PERSONA_TEXT`` — compiled into the APK so Android
       builds never lose the card when non-.py assets are not packaged.

    Any user-supplied ``extra_persona`` from the app is appended.
    """
    text = ""
    override = os.path.join(DATA_DIR, "persona_override.md")
    for path in (override, PERSONA_FILE):
        try:
            if os.path.isfile(path):
                with open(path, "r", encoding="utf-8") as fh:
                    candidate = fh.read().strip()
                if candidate:
                    text = candidate
                    break
        except OSError:
            continue

    if not text:
        try:
            from persona_builtin import PERSONA_TEXT

            text = PERSONA_TEXT
        except Exception:
            text = ""

    extra = str(get_app_config().get("extra_persona") or "").strip()
    if extra:
        text = f"{text}\n\n## 老大追加的要求\n\n{extra}"
    return text


def load_json(path, default=None):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return default if default is not None else {}


def save_json(path, data):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _coerce_int(value, fallback, low, high):
    try:
        return min(high, max(low, int(float(value))))
    except (ValueError, TypeError):
        return fallback


def _coerce_float(value, fallback, low, high):
    try:
        return min(high, max(low, float(value)))
    except (ValueError, TypeError):
        return fallback


def _coerce_bool(value, fallback):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("1", "true", "yes", "on"):
            return True
        if lowered in ("0", "false", "no", "off"):
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    return fallback


def _coerce_groups(value):
    if isinstance(value, str):
        value = [x.strip() for x in value.replace("，", ",").split(",") if x.strip()]
    if not isinstance(value, list):
        value = ALLOWED_GROUPS
    clean = []
    for group in value:
        try:
            group_id = int(str(group).strip())
        except (ValueError, TypeError):
            continue
        if group_id > 0 and group_id not in clean:
            clean.append(group_id)
    return clean[:200]


def get_app_config():
    """Return normalised settings: persisted values merged over defaults."""
    raw = load_json(APP_CONFIG_FILE, {})
    if not isinstance(raw, dict):
        raw = {}

    result = dict(DEFAULT_APP_CONFIG)
    result.update(raw)

    # Never leak a placeholder in place of a real key.
    key = str(result.get("api_key") or "").strip()
    if key in {"已隐藏", "YOUR_API_KEY", "your-api-key", "sk-xxxx"}:
        key = ""
    result["api_key"] = key

    result["api_base"] = str(result.get("api_base") or AI_API_BASE).strip().rstrip("/")
    result["model"] = str(result.get("model") or AI_MODEL).strip()[:200]
    result["napcat_http_url"] = str(result.get("napcat_http_url") or NAPCAT_HTTP_URL).strip().rstrip("/")
    result["napcat_ws_url"] = str(result.get("napcat_ws_url") or NAPCAT_WS_URL).strip().rstrip("/")
    result["napcat_qr_path"] = str(result.get("napcat_qr_path") or "").strip()[:1024]
    result["bot_nick"] = str(result.get("bot_nick") or BOT_NICK).strip()[:40] or BOT_NICK

    for name, (low, high, fallback) in _INT_KEYS.items():
        result[name] = _coerce_int(result.get(name, fallback), fallback, low, high)

    for name, (low, high, fallback) in _FLOAT_KEYS.items():
        result[name] = _coerce_float(result.get(name, fallback), fallback, low, high)

    for name in _BOOL_KEYS:
        result[name] = _coerce_bool(result.get(name), DEFAULT_APP_CONFIG[name])

    result["bot_qq"] = _coerce_int(result.get("bot_qq", BOT_QQ), BOT_QQ, 0, 10**12)
    result["owner_qq"] = _coerce_int(result.get("owner_qq", 3523172449), 3523172449, 0, 10**12)
    result["allowed_groups"] = _coerce_groups(result.get("allowed_groups", ALLOWED_GROUPS))
    result["extra_persona"] = str(result.get("extra_persona") or "")[:4000]

    stickers = result.get("sticker_keywords")
    if not isinstance(stickers, dict):
        stickers = {}
    clean_stickers = {}
    for k, v in list(stickers.items())[:100]:
        name = str(k).strip()[:20]
        path = str(v or "").strip()[:1024]
        if name and path:
            clean_stickers[name] = path
    result["sticker_keywords"] = clean_stickers

    return result


def update_app_config(new_values):
    """Persist validated settings. An empty API key preserves the stored one."""
    if not isinstance(new_values, dict):
        raise ValueError("配置格式无效")

    current = get_app_config()

    def clean_url(value, fallback, allowed_prefixes):
        value = str(value if value is not None else fallback).strip().rstrip("/")
        if not value:
            value = fallback
        if not any(value.startswith(prefix) for prefix in allowed_prefixes):
            raise ValueError("地址必须使用 http://、https://、ws:// 或 wss://")
        if any(ch.isspace() for ch in value):
            raise ValueError("地址不能包含空格")
        return value

    if "api_base" in new_values:
        current["api_base"] = clean_url(new_values["api_base"], current["api_base"], ("https://", "http://"))
    if "napcat_http_url" in new_values:
        current["napcat_http_url"] = clean_url(new_values["napcat_http_url"], current["napcat_http_url"], ("http://", "https://"))
    if "napcat_ws_url" in new_values:
        current["napcat_ws_url"] = clean_url(new_values["napcat_ws_url"], current["napcat_ws_url"], ("ws://", "wss://"))

    if "napcat_qr_path" in new_values:
        qr_path = str(new_values.get("napcat_qr_path") or "").strip()
        if "\x00" in qr_path or len(qr_path) > 1024:
            raise ValueError("二维码路径格式无效")
        current["napcat_qr_path"] = qr_path

    if new_values.get("clear_api_key") is True:
        current["api_key"] = ""
    elif "api_key" in new_values:
        candidate = str(new_values.get("api_key") or "").strip()
        if candidate:
            if len(candidate) > 4096 or "\n" in candidate or "\r" in candidate:
                raise ValueError("API Key 格式不正确")
            current["api_key"] = candidate

    if "model" in new_values:
        current["model"] = str(new_values.get("model") or "").strip()[:200] or AI_MODEL

    for name in _INT_KEYS:
        if name in new_values:
            low, high, fallback = _INT_KEYS[name]
            current[name] = _coerce_int(new_values[name], current.get(name, fallback), low, high)

    for name in _FLOAT_KEYS:
        if name in new_values:
            low, high, fallback = _FLOAT_KEYS[name]
            current[name] = _coerce_float(new_values[name], current.get(name, fallback), low, high)

    for name in _BOOL_KEYS:
        if name in new_values:
            current[name] = _coerce_bool(new_values[name], current.get(name, DEFAULT_APP_CONFIG[name]))

    if "bot_qq" in new_values:
        current["bot_qq"] = _coerce_int(new_values["bot_qq"], current["bot_qq"], 0, 10**12)
    if "owner_qq" in new_values:
        current["owner_qq"] = _coerce_int(new_values["owner_qq"], current["owner_qq"], 0, 10**12)
    if "bot_nick" in new_values:
        current["bot_nick"] = str(new_values["bot_nick"]).strip()[:40] or BOT_NICK
    if "allowed_groups" in new_values:
        current["allowed_groups"] = _coerce_groups(new_values["allowed_groups"])
    if "extra_persona" in new_values:
        current["extra_persona"] = str(new_values.get("extra_persona") or "")[:4000]
    if "sticker_keywords" in new_values:
        raw_stickers = new_values["sticker_keywords"]
        if isinstance(raw_stickers, dict):
            current["sticker_keywords"] = {
                str(k).strip()[:20]: str(v or "").strip()[:1024]
                for k, v in list(raw_stickers.items())[:100]
                if str(k).strip() and str(v or "").strip()
            }

    save_json(APP_CONFIG_FILE, current)
    return current


def setting(name, default=None):
    """Convenience accessor used by hot paths."""
    return get_app_config().get(name, DEFAULT_APP_CONFIG.get(name, default))


def in_quiet_hours(now=None):
    """True when the bot should stay silent (unless directly addressed)."""
    cfg = get_app_config()
    if not cfg["feature_quiet_hours"]:
        return False
    import time as _time

    hour = _time.localtime(now or _time.time()).tm_hour
    start = cfg["quiet_hours_start"]
    end = cfg["quiet_hours_end"]
    if start == end:
        return False
    if start < end:
        return start <= hour < end
    # Window wraps past midnight, e.g. 23 -> 7.
    return hour >= start or hour < end
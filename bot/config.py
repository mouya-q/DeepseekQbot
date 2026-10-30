#!/usr/bin/env python3
"""Runtime configuration for DeepseekQbot; standard-library only."""
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

# Bot identity and defaults retained from the uploaded project.
BOT_QQ = 3086657739
BOT_NICK = "大肥鱼"
ALT_NICKS = ["本鲸", "肥鱼", "鲸鱼娘"]
ALLOWED_GROUPS = [960636357]
NAPCAT_HTTP_URL = "http://127.0.0.1:3000"
NAPCAT_WS_URL = "ws://127.0.0.1:3001"

# API key is intentionally blank; enter your own key in the app.
AI_API_BASE = "https://ly.77625.xyz/v1"
AI_API_KEY = ""
AI_MODEL = "glm-5.2"
AI_MAX_CONTEXT_TOKENS = 130000
AI_COMPRESS_TARGET = 90000
AI_TEMPERATURE = 0.85
AI_MAX_TOKENS = 2048

REPLY_PROBABILITY_NON_MENTION = 0.10
REPLY_DELAY_BASE_MS = 800
REPLY_DELAY_RANDOM_MS = 1500
MAX_REPLY_SPLIT = 300
REPLY_COOLDOWN_S = 3
ANALYZE_EVERY_N_MESSAGES = 50
ANALYSIS_MIN_MESSAGES = 10
LOG_FILE = os.path.join(LOG_DIR, "bot.log")
CHAT_LOG_DIR = os.path.join(DATA_DIR, "chat_logs")
PERSONALITY_DIR = os.path.join(DATA_DIR, "personalities")
CONTEXT_DIR = os.path.join(DATA_DIR, "contexts")
STATE_FILE = os.path.join(DATA_DIR, "state.json")
for d in (CHAT_LOG_DIR, PERSONALITY_DIR, CONTEXT_DIR):
    os.makedirs(d, exist_ok=True)

DEFAULT_APP_CONFIG = {
    "api_base": AI_API_BASE,
    "api_key": "",
    "model": AI_MODEL,
    "max_tokens": AI_MAX_TOKENS,
    "temperature": AI_TEMPERATURE,
    "napcat_http_url": NAPCAT_HTTP_URL,
    "napcat_ws_url": NAPCAT_WS_URL,
    "napcat_qr_path": "",
    "bot_qq": BOT_QQ,
    "owner_qq": 3523172449,
    "bot_nick": BOT_NICK,
    "allowed_groups": ALLOWED_GROUPS,
}


def load_persona_text():
    """Load the persona card.

    Order of preference:
    1. ``bot/data/persona_override.md`` — user-edited copy in writable storage.
    2. ``bot/persona/大肥鱼.md`` — checked-in card next to the sources.
    3. ``persona_builtin.PERSONA_TEXT`` — compiled into the APK so Android
       builds never lose the card when non-.py assets are not packaged.
    """
    override = os.path.join(DATA_DIR, "persona_override.md")
    for path in (override, PERSONA_FILE):
        try:
            if os.path.isfile(path):
                with open(path, "r", encoding="utf-8") as fh:
                    text = fh.read().strip()
                if text:
                    return text
        except OSError:
            continue
    try:
        from persona_builtin import PERSONA_TEXT

        return PERSONA_TEXT
    except Exception:
        return ""


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


def get_app_config():
    """Return normalized persisted settings over defaults."""
    raw = load_json(APP_CONFIG_FILE, {})
    if not isinstance(raw, dict):
        raw = {}
    result = dict(DEFAULT_APP_CONFIG)
    result.update(raw)
    # Old builds sometimes stored a placeholder rather than an actual API key.
    key = str(result.get("api_key") or "").strip()
    if key in {"已隐藏", "YOUR_API_KEY", "your-api-key", "sk-xxxx"}:
        key = ""
    result["api_key"] = key
    result["api_base"] = str(result.get("api_base") or AI_API_BASE).strip().rstrip("/")
    result["model"] = str(result.get("model") or AI_MODEL).strip()
    result["napcat_http_url"] = str(result.get("napcat_http_url") or NAPCAT_HTTP_URL).strip().rstrip("/")
    result["napcat_ws_url"] = str(result.get("napcat_ws_url") or NAPCAT_WS_URL).strip().rstrip("/")
    result["napcat_qr_path"] = str(result.get("napcat_qr_path") or "").strip()[:1024]
    try:
        result["max_tokens"] = min(32768, max(1, int(result.get("max_tokens", AI_MAX_TOKENS))))
    except (ValueError, TypeError):
        result["max_tokens"] = AI_MAX_TOKENS
    try:
        result["temperature"] = min(2.0, max(0.0, float(result.get("temperature", AI_TEMPERATURE))))
    except (ValueError, TypeError):
        result["temperature"] = AI_TEMPERATURE
    try:
        result["bot_qq"] = int(result.get("bot_qq", BOT_QQ))
    except (ValueError, TypeError):
        result["bot_qq"] = BOT_QQ
    try:
        result["owner_qq"] = max(0, int(result.get("owner_qq", 3523172449)))
    except (ValueError, TypeError):
        result["owner_qq"] = 3523172449
    result["bot_nick"] = str(result.get("bot_nick") or BOT_NICK).strip()[:40]
    groups = result.get("allowed_groups", ALLOWED_GROUPS)
    if not isinstance(groups, list):
        groups = ALLOWED_GROUPS
    clean_groups = []
    for group in groups:
        try:
            group_id = int(str(group).strip())
            if group_id > 0 and group_id not in clean_groups:
                clean_groups.append(group_id)
        except (ValueError, TypeError):
            continue
    result["allowed_groups"] = clean_groups[:200]
    return result


def update_app_config(new_values):
    """Persist only supported, validated settings. Empty API key preserves old key."""
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

    current["api_base"] = clean_url(new_values.get("api_base", current["api_base"]), current["api_base"], ("https://", "http://"))
    current["napcat_http_url"] = clean_url(new_values.get("napcat_http_url", current["napcat_http_url"]), current["napcat_http_url"], ("http://", "https://"))
    current["napcat_ws_url"] = clean_url(new_values.get("napcat_ws_url", current["napcat_ws_url"]), current["napcat_ws_url"], ("ws://", "wss://"))
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
    current["model"] = str(new_values.get("model", current["model"]) or "").strip()[:200]
    if "max_tokens" in new_values:
        current["max_tokens"] = min(32768, max(1, int(new_values["max_tokens"])))
    if "temperature" in new_values:
        current["temperature"] = min(2.0, max(0.0, float(new_values["temperature"])))
    if "bot_qq" in new_values:
        current["bot_qq"] = int(new_values["bot_qq"])
    if "owner_qq" in new_values:
        current["owner_qq"] = max(0, int(new_values["owner_qq"] or 0))
    if "bot_nick" in new_values:
        current["bot_nick"] = str(new_values["bot_nick"]).strip()[:40] or BOT_NICK
    if "allowed_groups" in new_values:
        groups = new_values["allowed_groups"]
        if isinstance(groups, str):
            groups = [x.strip() for x in groups.replace("，", ",").split(",") if x.strip()]
        if not isinstance(groups, list):
            raise ValueError("群号列表格式无效")
        parsed = []
        for item in groups:
            gid = int(str(item).strip())
            if gid <= 0:
                raise ValueError("群号必须为正整数")
            if gid not in parsed:
                parsed.append(gid)
        current["allowed_groups"] = parsed[:200]
    save_json(APP_CONFIG_FILE, current)
    return current
"""Android-side bootstrap for 大肥鱼 QQ bot.

Runs inside the app process via Chaquopy. Two responsibilities:

1. Expose a JSON-file configuration store in the app's private storage so
   the Kotlin UI can read/write the same settings the bot uses.
2. Provide a blocking ``run_bot()`` entry point that owns the asyncio loop,
   plus ``request_stop()`` so the Android Service can shut it down cleanly.

Nothing here touches QQ login. The bot only speaks OneBot v11 to whatever
endpoint ``napcat_ws_url`` points at.

Design notes
------------
* Standard library only (Chaquopy ships no third-party wheels here).
* ``config.py`` derives all of its paths from ``__file__``. Chaquopy keeps
  Python source in the APK, which is read-only, so we copy the bot package
  into the app's private ``files`` directory on first launch and import it
  from there. That keeps every module's path logic valid and writable.
* Thread creation is fine in-app (unlike the proot container), so the
  original threaded helpers keep working.
"""

import json
import os
import shutil
import sys
import threading
import traceback

# ── Paths ────────────────────────────────────────────────────────────────────

# Chaquopy sets this to the app's private files directory.
_APP_FILES = os.environ.get("ANDROID_APP_FILES") or ""
_PKG_DIR = os.path.dirname(os.path.abspath(__file__))

# Where the writable copy of the bot lives, e.g.
#   /data/data/com.mouya.qbotds/files/bot
_WORK_BOT_DIR = os.path.join(_APP_FILES, "bot") if _APP_FILES else _PKG_DIR

_state = {
    "thread": None,
    "stop_event": None,
    "running": False,
    "last_error": "",
}
_state_lock = threading.Lock()


def _log(msg):
    line = "[bootstrap] {}".format(msg)
    print(line, flush=True)
    if _APP_FILES:
        try:
            os.makedirs(os.path.join(_APP_FILES, "logs"), exist_ok=True)
            with open(os.path.join(_APP_FILES, "logs", "bootstrap.log"), "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except OSError:
            pass


# ── Source synchronisation ───────────────────────────────────────────────────

def _sync_bot_sources():
    """Copy packaged bot sources into private storage once, refreshing on change.

    Returns the directory that should go on ``sys.path``.
    """
    src = os.path.join(_PKG_DIR, "bot")
    if not os.path.isdir(src):
        # Already running from the writable copy, or layout differs.
        return _WORK_BOT_DIR if os.path.isdir(_WORK_BOT_DIR) else _PKG_DIR

    if not _APP_FILES:
        # No private dir available (e.g. unit test): use sources in place.
        return _PKG_DIR

    os.makedirs(_WORK_BOT_DIR, exist_ok=True)

    # Always refresh .py sources and the persona card; never touch data/.
    for name in os.listdir(src):
        src_path = os.path.join(src, name)
        dst_path = os.path.join(_WORK_BOT_DIR, name)
        if os.path.isdir(src_path):
            if name in ("data", "logs", "state", "__pycache__"):
                os.makedirs(dst_path, exist_ok=True)
                continue
            shutil.copytree(src_path, dst_path, dirs_exist_ok=True)
            continue
        try:
            shutil.copy2(src_path, dst_path)
        except OSError as exc:
            _log("copy failed for {}: {}".format(name, exc))

    for required in ("data", "logs", "state"):
        os.makedirs(os.path.join(_WORK_BOT_DIR, required), exist_ok=True)

    return _WORK_BOT_DIR


def _prepare_import_path():
    bot_dir = _sync_bot_sources()
    if bot_dir not in sys.path:
        sys.path.insert(0, bot_dir)
    return bot_dir


# ── Configuration bridge ─────────────────────────────────────────────────────

def _config_path():
    return os.path.join(_WORK_BOT_DIR, "data", "app_config.json")


def read_config_json():
    """Return the persisted app config as a JSON string (for Kotlin)."""
    try:
        path = _config_path()
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as fh:
                return fh.read()
    except OSError as exc:
        _log("read_config_json failed: {}".format(exc))
    return "{}"


def write_config_json(payload):
    """Persist config coming from Kotlin. Returns a JSON status string."""
    bot_dir = _prepare_import_path()
    try:
        from config import update_app_config  # noqa: E402

        data = json.loads(payload) if payload else {}
        update_app_config(data)
        return json.dumps({"ok": True}, ensure_ascii=False)
    except Exception as exc:  # noqa: BLE001 - report everything to the UI
        _log("write_config_json failed: {}".format(exc))
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)


def safe_config_json():
    """Config for display, with the API key masked."""
    _prepare_import_path()
    try:
        from config import get_app_config  # noqa: E402

        cfg = get_app_config()
        cfg = dict(cfg)
        cfg["api_key"] = "" if not cfg.get("api_key") else "已保存"
        return json.dumps(cfg, ensure_ascii=False)
    except Exception as exc:  # noqa: BLE001
        _log("safe_config_json failed: {}".format(exc))
        return json.dumps({"error": str(exc)}, ensure_ascii=False)


# ── Bot lifecycle ────────────────────────────────────────────────────────────

def is_running():
    with _state_lock:
        return bool(_state["running"])


def run_bot():
    """Start the bot on a background thread. Idempotent."""
    with _state_lock:
        if _state["running"]:
            return True
        stop_event = threading.Event()
        _state["stop_event"] = stop_event
        _state["running"] = True
        _state["last_error"] = ""

    def _worker():
        try:
            _run_bot_blocking(stop_event)
        except Exception as exc:  # noqa: BLE001
            tb = traceback.format_exc()
            with _state_lock:
                _state["last_error"] = "{}".format(exc)
            _log("bot crashed: {}\n{}".format(exc, tb))
        finally:
            with _state_lock:
                _state["running"] = False

    thread = threading.Thread(target=_worker, name="dafeiyu-bot", daemon=False)
    with _state_lock:
        _state["thread"] = thread
    thread.start()
    return True


def _run_bot_blocking(stop_event):
    bot_dir = _prepare_import_path()
    os.chdir(bot_dir)

    import asyncio

    # Import after the path is set up.
    from main import DayuBot  # noqa: E402

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    bot = DayuBot()

    async def _runner():
        # Watch for stop requests without relying on OS signals, which are not
        # delivered reliably inside an Android app process.
        async def _stop_watcher():
            while not stop_event.is_set():
                await asyncio.sleep(0.5)
            bot.stop()

        watcher = asyncio.ensure_future(_stop_watcher())
        try:
            await bot.run()
        finally:
            watcher.cancel()
            try:
                await watcher
            except asyncio.CancelledError:
                pass

    try:
        loop.run_until_complete(_runner())
    finally:
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception:  # noqa: BLE001
            pass
        loop.close()
        _log("bot loop finished")


def request_stop():
    """Ask the bot to stop. Returns True when a stop was signalled."""
    with _state_lock:
        stop_event = _state["stop_event"]
        if not stop_event:
            return False
        stop_event.set()
    return True


def last_error():
    with _state_lock:
        return _state["last_error"]


def bot_status_json():
    """Small status payload for the Kotlin UI."""
    with _state_lock:
        return json.dumps({
            "running": _state["running"],
            "last_error": _state["last_error"],
            "bot_dir": _WORK_BOT_DIR,
        }, ensure_ascii=False)


def tail_log(lines=120):
    """Return the tail of bot.log (or bootstrap.log as a fallback)."""
    for name in ("bot.log", "bootstrap.log"):
        path = os.path.join(_WORK_BOT_DIR, "logs", name)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as fh:
                    return "".join(fh.readlines()[-max(1, int(lines)):])
            except OSError as exc:
                return "读取日志失败：{}".format(exc)
    return "暂时没有日志。"
#!/usr/bin/env python3
"""Local-only DeepseekQbot control panel and OpenAI-compatible API setup.

Standard library only. By default binds to 127.0.0.1, never the public network.
Uses single-threaded HTTPServer to avoid proot thread creation issues.
"""
import base64
import json
import mimetypes
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
BOT_DIR = ROOT / "bot"
DATA_DIR = BOT_DIR / "data"
LOG_DIR = BOT_DIR / "logs"
WEB_DIR = ROOT / "web"
TOKEN_FILE = DATA_DIR / "panel-token"
PID_FILE = DATA_DIR / "bot.pid"
BOT_LOG = LOG_DIR / "bot.log"
PORT = int(os.environ.get("QBOT_PANEL_PORT", "3108"))
HOST = "127.0.0.1"  # Intentionally fixed: do not expose the control panel on LAN/public interfaces.

sys.path.insert(0, str(BOT_DIR))
from config import get_app_config, update_app_config, save_json  # noqa: E402

for folder in (DATA_DIR, LOG_DIR):
    folder.mkdir(parents=True, exist_ok=True)


def get_panel_token():
    if TOKEN_FILE.exists():
        token = TOKEN_FILE.read_text(encoding="utf-8").strip()
        if token:
            return token
    token = base64.urlsafe_b64encode(os.urandom(24)).decode("ascii").rstrip("=")
    TOKEN_FILE.write_text(token, encoding="utf-8")
    try:
        TOKEN_FILE.chmod(0o600)
    except OSError:
        pass
    return token


PANEL_TOKEN = get_panel_token()


def safe_config():
    cfg = get_app_config()
    return {
        "api_base": cfg["api_base"],
        "api_key_set": bool(cfg.get("api_key")),
        "model": cfg["model"],
        "max_tokens": cfg["max_tokens"],
        "temperature": cfg["temperature"],
        "napcat_http_url": cfg["napcat_http_url"],
        "napcat_ws_url": cfg["napcat_ws_url"],
        "napcat_qr_path": cfg.get("napcat_qr_path", ""),
        "bot_qq": cfg["bot_qq"],
        "owner_qq": cfg["owner_qq"],
        "bot_nick": cfg["bot_nick"],
        "allowed_groups": cfg["allowed_groups"],
    }


def api_endpoint(base, path):
    base = (base or "").strip().rstrip("/")
    for suffix in ("/chat/completions", "/models"):
        if base.endswith(suffix):
            base = base[:-len(suffix)]
    return base + "/" + path.lstrip("/")


def fetch_models():
    cfg = get_app_config()
    if not cfg.get("api_key"):
        raise ValueError("请先填写 API Key")
    url = api_endpoint(cfg["api_base"], "models")
    req = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + cfg["api_key"],
        "Accept": "application/json",
        "User-Agent": "DeepseekQbot/1.0",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:250]
        raise ValueError(f"模型列表请求失败（HTTP {exc.code}）：{detail}") from exc
    except Exception as exc:
        raise ValueError(f"无法获取模型列表：{exc}") from exc
    data = payload.get("data", []) if isinstance(payload, dict) else []
    models = []
    for item in data:
        if isinstance(item, dict) and item.get("id"):
            models.append({"id": str(item["id"]), "name": str(item.get("name") or item["id"])})
    # Some compatible APIs return a bare array.
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict) and item.get("id"):
                models.append({"id": str(item["id"]), "name": str(item.get("name") or item["id"])})
    unique = {}
    for model in models:
        unique[model["id"]] = model
    return sorted(unique.values(), key=lambda x: x["id"].lower())


def test_api():
    cfg = get_app_config()
    if not cfg.get("api_key"):
        raise ValueError("请先填写 API Key 并保存")
    payload = {
        "model": cfg["model"],
        "messages": [{"role": "user", "content": "请只回复：连接成功"}],
        "max_tokens": 32,
        "temperature": 0,
        "stream": False,
    }
    request = urllib.request.Request(
        api_endpoint(cfg["api_base"], "chat/completions"),
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + cfg["api_key"],
            "User-Agent": "DeepseekQbot/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:250]
        raise ValueError(f"接口测试失败（HTTP {exc.code}）：{detail}") from exc
    except Exception as exc:
        raise ValueError(f"接口连接失败：{exc}") from exc
    choices = result.get("choices", []) if isinstance(result, dict) else []
    if not choices:
        raise ValueError("接口已响应，但没有返回 choices 数据")
    msg = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
    return {"ok": True, "model": result.get("model", cfg["model"]), "reply": str(msg.get("content", "连接成功"))[:160]}


def get_http_json(url, timeout=2.5):
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "DeepseekQbot/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception:
        return None


def qq_status():
    cfg = get_app_config()
    info = get_http_json(cfg["napcat_http_url"] + "/get_login_info")
    if isinstance(info, dict) and info.get("status") == "ok":
        return {"online": True, "qq": (info.get("data") or {}).get("user_id"), "nickname": (info.get("data") or {}).get("nickname", "QQ 已登录"), "message": "NapCat 已连接"}
    # NapCat commonly accepts POST for OneBot API endpoints too.
    try:
        data = json.dumps({}).encode("utf-8")
        req = urllib.request.Request(cfg["napcat_http_url"] + "/get_login_info", data=data, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=2.5) as response:
            info = json.loads(response.read().decode("utf-8"))
        if isinstance(info, dict) and info.get("status") == "ok":
            data = info.get("data") or {}
            return {"online": True, "qq": data.get("user_id"), "nickname": data.get("nickname", "QQ 已登录"), "message": "NapCat 已连接"}
    except Exception:
        pass
    return {"online": False, "qq": None, "nickname": "未登录", "message": "无法连接 NapCat，请检查 QQ / NapCat 是否已启动"}


def find_bot_pids():
    found = []
    target = str((BOT_DIR / "main.py").resolve())
    proc = Path("/proc")
    try:
        for ent in proc.iterdir():
            if not ent.name.isdigit():
                continue
            try:
                raw_bytes = (ent / "cmdline").read_bytes()
                args = [part.decode("utf-8", errors="ignore") for part in raw_bytes.split(b"\0") if part]
                raw = " ".join(args)
                try:
                    cwd = os.path.realpath(os.readlink(ent / "cwd"))
                except OSError:
                    cwd = ""
                if "panel_server.py" not in raw and (target in args or (cwd == str(BOT_DIR.resolve()) and any(os.path.basename(arg) == "main.py" for arg in args))):
                    found.append(int(ent.name))
            except (OSError, PermissionError):
                continue
    except OSError:
        pass
    return sorted(set(found))


def bot_status():
    pids = find_bot_pids()
    latest = None
    state_file = DATA_DIR / "state.json"
    try:
        state = json.loads(state_file.read_text(encoding="utf-8"))
        ts = state.get("last_message_ts")
        if ts:
            latest = int(ts)
    except Exception:
        pass
    return {"running": bool(pids), "pids": pids, "last_message_ts": latest}


def start_bot():
    if find_bot_pids():
        return {"ok": True, "message": "机器人已经在运行"}
    log = open(BOT_LOG, "a", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, str(BOT_DIR / "main.py")],
        cwd=str(BOT_DIR), stdin=subprocess.DEVNULL, stdout=log,
        stderr=subprocess.STDOUT, start_new_session=True,
        close_fds=True,
    )
    log.close()
    PID_FILE.write_text(str(proc.pid), encoding="ascii")
    try:
        PID_FILE.chmod(0o600)
    except OSError:
        pass
    time.sleep(0.25)
    if proc.poll() is not None:
        return {"ok": False, "message": f"机器人启动失败，检查日志（退出码 {proc.returncode}）"}
    return {"ok": True, "message": "启动命令已发送", "pid": proc.pid}


def stop_bot():
    pids = find_bot_pids()
    if not pids:
        return {"ok": True, "message": "机器人当前未运行"}
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except PermissionError:
            return {"ok": False, "message": f"没有权限停止进程 {pid}"}
    deadline = time.time() + 3
    while time.time() < deadline and any(Path(f"/proc/{p}").exists() for p in pids):
        time.sleep(0.1)
    remaining = [p for p in pids if Path(f"/proc/{p}").exists()]
    for pid in remaining:
        try:
            os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    try:
        PID_FILE.unlink(missing_ok=True)
    except OSError:
        pass
    return {"ok": True, "message": "停止命令已发送"}


def tail_log(lines=80):
    if not BOT_LOG.exists():
        return "暂时没有日志。"
    try:
        with BOT_LOG.open("r", encoding="utf-8", errors="replace") as f:
            return "".join(f.readlines()[-max(1, min(200, lines)):])
    except OSError as exc:
        return f"读取日志失败：{exc}"


def find_qr_file():
    env = os.environ.get("NAPCAT_QR_PATH")
    configured = get_app_config().get("napcat_qr_path", "")
    candidates = []
    if configured:
        candidates.append(Path(configured).expanduser())
    if env:
        candidates.append(Path(env).expanduser())
    home = Path.home()
    candidates += [
        home / "Napcat/opt/QQ/resources/app/app_launcher/napcat/cache/qrcode.png",
        Path("/root/Napcat/opt/QQ/resources/app/app_launcher/napcat/cache/qrcode.png"),
        Path("/root/Napcat/opt/QQ/resources/app/app_launcher/napcat/cache/qrcode.jpg"),
        Path("/root/.config/QQ/NapCat/cache/qrcode.png"),
    ]
    for candidate in candidates:
        try:
            if candidate.is_file() and candidate.stat().st_size < 8 * 1024 * 1024:
                return candidate
        except OSError:
            continue
    return None


class Handler(BaseHTTPRequestHandler):
    server_version = "DeepseekQbotPanel/1.0"

    def log_message(self, fmt, *args):
        # Keep console noise low; do not log headers or submitted secrets.
        if os.environ.get("QBOT_PANEL_ACCESS_LOG") == "1":
            super().log_message(fmt, *args)

    def _send(self, status, body, content_type="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)

    def _json_body(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 0 or length > 65536:
                raise ValueError("请求数据过大")
            body = self.rfile.read(length) if length else b"{}"
            data = json.loads(body.decode("utf-8"))
            if not isinstance(data, dict):
                raise ValueError("请求内容必须是对象")
            return data
        except Exception as exc:
            raise ValueError(f"请求格式错误：{exc}") from exc

    def _authorized(self):
        if self.headers.get("X-Qbot-Panel", "") != PANEL_TOKEN:
            self._send(403, {"error": "面板校验失败，请刷新页面"})
            return False
        # Reject non-local callers even though binding is loopback by default.
        if self.client_address[0] not in {"127.0.0.1", "::1", "::ffff:127.0.0.1"}:
            self._send(403, {"error": "仅允许本机访问"})
            return False
        return True

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/" or path == "/index.html":
            try:
                html = (WEB_DIR / "index.html").read_text(encoding="utf-8").replace("__PANEL_TOKEN__", PANEL_TOKEN)
                self._send(200, html, "text/html; charset=utf-8")
            except Exception as exc:
                self._send(500, {"error": f"页面读取失败：{exc}"})
            return
        if path == "/favicon.ico":
            self._send(204, b"", "image/x-icon")
            return
        if not path.startswith("/api/"):
            self._send(404, {"error": "Not found"})
            return
        if not self._authorized():
            return
        try:
            if path == "/api/config":
                self._send(200, safe_config())
            elif path == "/api/status":
                self._send(200, {"bot": bot_status(), "qq": qq_status(), "config": safe_config()})
            elif path == "/api/models":
                models = fetch_models()
                self._send(200, {"models": models, "count": len(models)})
            elif path == "/api/logs":
                self._send(200, {"text": tail_log()})
            elif path == "/api/qq/qrcode":
                qr = find_qr_file()
                if not qr:
                    self._send(404, {"error": "未找到 NapCat 登录二维码。请先启动 QQ/NapCat，并设置 NAPCAT_QR_PATH（如有需要）。"})
                else:
                    content_type = mimetypes.guess_type(str(qr))[0] or "image/png"
                    self._send(200, qr.read_bytes(), content_type)
            else:
                self._send(404, {"error": "未知接口"})
        except ValueError as exc:
            self._send(400, {"error": str(exc)})
        except Exception as exc:
            self._send(500, {"error": str(exc)[:300]})

    def do_POST(self):
        path = urlparse(self.path).path
        if not path.startswith("/api/") or not self._authorized():
            if path.startswith("/api/"):
                return
            self._send(404, {"error": "Not found"})
            return
        try:
            if path == "/api/config":
                data = self._json_body()
                cfg = update_app_config(data)
                self._send(200, {"ok": True, "config": safe_config(), "message": "设置已保存；群权限立即生效，QQ 地址变更后请重启机器人"})
            elif path == "/api/api-test":
                self._send(200, test_api())
            elif path == "/api/bot/start":
                self._send(200, start_bot())
            elif path == "/api/bot/stop":
                self._send(200, stop_bot())
            elif path == "/api/bot/restart":
                stop_bot()
                time.sleep(0.3)
                self._send(200, start_bot())
            elif path == "/api/qq/refresh":
                self._send(200, qq_status())
            else:
                self._send(404, {"error": "未知接口"})
        except ValueError as exc:
            self._send(400, {"error": str(exc)})
        except Exception as exc:
            self._send(500, {"error": str(exc)[:300]})


def main():
    server = HTTPServer((HOST, PORT), Handler)
    server.timeout = 0.5
    print(f"DeepseekQbot 面板已启动：http://{HOST}:{PORT}")
    print("仅监听本机；请在同一手机的浏览器或 DeepseekQbot App 中打开。")
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
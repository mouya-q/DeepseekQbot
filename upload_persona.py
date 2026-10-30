#!/usr/bin/env python3
"""One-shot: upload bot/persona/大肥鱼.md to GitHub."""
import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request

TOKEN = os.environ.get("GH_TOKEN", "")
if not TOKEN:
    print("ERROR: GH_TOKEN not set")
    import sys
    sys.exit(1)

OWNER = "mouya-q"
REPO = "DeepseekQbot"
BRANCH = "main"
rel_path = "bot/persona/大肥鱼.md"
full_path = "/storage/emulated/0/大肥鱼/DeepseekQbot/bot/persona/大肥鱼.md"

with open(full_path, "rb") as f:
    content = f.read()

content_b64 = base64.b64encode(content).decode("ascii")
segments = rel_path.split("/")
path_encoded = "/".join(urllib.parse.quote(seg, safe="") for seg in segments)

body = json.dumps({
    "message": "Add persona file (URL-encoded Chinese filename)",
    "content": content_b64,
    "branch": BRANCH,
}).encode("utf-8")

req = urllib.request.Request(
    f"https://api.github.com/repos/{OWNER}/{REPO}/contents/{path_encoded}",
    data=body,
    headers={
        "Authorization": f"Bearer {TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
        "User-Agent": "DeepseekQbot-uploader/1.0",
    },
    method="PUT",
)

try:
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
        print(f"Status: {resp.status}")
        print(raw.decode("utf-8")[:500])
except urllib.error.HTTPError as e:
    raw = e.read()
    print(f"HTTP Error {e.code}")
    print(raw.decode("utf-8", errors="replace")[:500])
except Exception as e:
    print(f"Error: {e}")
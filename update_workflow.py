#!/usr/bin/env python3
"""One-shot: update .github/workflows/build-apk.yml on GitHub."""
import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

TOKEN = os.environ.get("GH_TOKEN", "")
if not TOKEN:
    print("ERROR: GH_TOKEN not set")
    sys.exit(1)

OWNER = "mouya-q"
REPO = "DeepseekQbot"
BRANCH = "main"
rel_path = ".github/workflows/build-apk.yml"
full_path = "/storage/emulated/0/大肥鱼/DeepseekQbot/.github/workflows/build-apk.yml"

# First, get the current file's SHA (required for update)
api_base = "https://api.github.com"
segments = rel_path.split("/")
path_encoded = "/".join(urllib.parse.quote(seg, safe="") for seg in segments)

# GET current file to get SHA
get_req = urllib.request.Request(
    f"{api_base}/repos/{OWNER}/{REPO}/contents/{path_encoded}?ref={BRANCH}",
    headers={
        "Authorization": f"Bearer {TOKEN}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "DeepseekQbot-updater/1.0",
    },
    method="GET",
)
try:
    with urllib.request.urlopen(get_req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        old_sha = data.get("sha", "")
        print(f"Current SHA: {old_sha}")
except urllib.error.HTTPError as e:
    print(f"GET failed: {e.code} {e.read().decode('utf-8', errors='replace')[:200]}")
    old_sha = ""

# Read new content
with open(full_path, "rb") as f:
    content = f.read()
content_b64 = base64.b64encode(content).decode("ascii")

body = json.dumps({
    "message": "fix: use manual Gradle install instead of setup-gradle action",
    "content": content_b64,
    "branch": BRANCH,
    "sha": old_sha,
}).encode("utf-8")

put_req = urllib.request.Request(
    f"{api_base}/repos/{OWNER}/{REPO}/contents/{path_encoded}",
    data=body,
    headers={
        "Authorization": f"Bearer {TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
        "User-Agent": "DeepseekQbot-updater/1.0",
    },
    method="PUT",
)
try:
    with urllib.request.urlopen(put_req, timeout=30) as resp:
        raw = resp.read()
        print(f"Update Status: {resp.status}")
        print(raw.decode("utf-8")[:300])
except urllib.error.HTTPError as e:
    raw = e.read()
    print(f"HTTP Error {e.code}")
    print(raw.decode("utf-8", errors="replace")[:500])
except Exception as e:
    print(f"Error: {e}")
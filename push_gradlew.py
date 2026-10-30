#!/usr/bin/env python3
"""Push gradlew and updated workflow to GitHub."""
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
API_BASE = "https://api.github.com"

files = [
    {
        "rel_path": "android/gradlew",
        "full_path": "/storage/emulated/0/大肥鱼/DeepseekQbot/android/gradlew",
        "message": "Add bootstrap gradlew script (Gradle 8.14)",
    },
    {
        "rel_path": ".github/workflows/build-apk.yml",
        "full_path": "/storage/emulated/0/大肥鱼/DeepseekQbot/.github/workflows/build-apk.yml",
        "message": "fix: use bootstrap gradlew instead of manual Gradle install",
    },
]

def encode_path(rel_path):
    segments = rel_path.split("/")
    return "/".join(urllib.parse.quote(seg, safe="") for seg in segments)

def get_sha(rel_path):
    """Get SHA of existing file for update."""
    path_enc = encode_path(rel_path)
    url = f"{API_BASE}/repos/{OWNER}/{REPO}/contents/{path_enc}?ref={BRANCH}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {TOKEN}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "DeepseekQbot-pusher/1.0",
    }, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("sha", "")
    except urllib.error.HTTPError as e:
        print(f"  GET {rel_path}: {e.code} (new file)")
        return ""
    except Exception as e:
        print(f"  GET {rel_path}: {e}")
        return ""

for f in files:
    print(f"\nProcessing {f['rel_path']}...")
    sha = get_sha(f["rel_path"])
    if sha:
        print(f"  Existing SHA: {sha}")
    
    with open(f["full_path"], "rb") as fh:
        content = fh.read()
    content_b64 = base64.b64encode(content).decode("ascii")
    
    body_dict = {
        "message": f["message"],
        "content": content_b64,
        "branch": BRANCH,
    }
    if sha:
        body_dict["sha"] = sha
    
    body = json.dumps(body_dict).encode("utf-8")
    path_enc = encode_path(f["rel_path"])
    url = f"{API_BASE}/repos/{OWNER}/{REPO}/contents/{path_enc}"
    
    req = urllib.request.Request(url, data=body, headers={
        "Authorization": f"Bearer {TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
        "User-Agent": "DeepseekQbot-pusher/1.0",
    }, method="PUT")
    
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            print(f"  Status: {resp.status}")
            result = json.loads(raw.decode("utf-8"))
            print(f"  SHA: {result.get('content', {}).get('sha', '?')}")
    except urllib.error.HTTPError as e:
        raw = e.read()
        print(f"  HTTP Error {e.code}")
        print(f"  {raw.decode('utf-8', errors='replace')[:500]}")
    except Exception as e:
        print(f"  Error: {e}")

print("\nDone.")
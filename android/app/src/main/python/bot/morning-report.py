#!/usr/bin/env python3
"""Morning report — fetches weather and reminds 大肥鱼 to say good morning.

Every day at 08:00 (Beijing time, UTC+8):
  1. Fetch weather from wttr.in (using lat,lon for accuracy)
  2. Write into her memory (state/morning-report.json)
  3. Wake her up → she sends good morning to the owner

Pure stdlib.
"""

import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import STATE_FILE, load_json, save_json

REPORT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state", "morning-report.json")
# Default location — update with actual phone coordinates
WEATHER_LAT = "39.9042"
WEATHER_LON = "116.4074"


def log(msg):
    print(f"[morning-report] {time.strftime('%H:%M:%S')} {msg}", flush=True)


def fetch_weather(lat: str, lon: str) -> str:
    """Fetch weather from wttr.in in plain text format."""
    url = f"https://wttr.in/{lat},{lon}?0&lang=zh-cn&format=%c+%t+%w+%h+%p"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "curl/7.68"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            text = resp.read().decode("utf-8", errors="replace").strip()
            return text
    except Exception as e:
        log(f"天气查询失败: {e}")
        return "今天天气数据暂时查不到，可能网络不太行。"


def build_report() -> str:
    """Build the morning report text."""
    weather = fetch_weather(WEATHER_LAT, WEATHER_LON)
    today = time.strftime("%Y年%m月%d日 %A")

    report = f"""【早安 · {today}】

天气: {weather}

记得提醒老大今天该干嘛。别发太长，大肥鱼喜欢短句。
"""
    return report


def main():
    log("早报服务启动")

    # Check if we should run immediately (for testing)
    if "--once" in sys.argv:
        report = build_report()
        log(report)
        save_json(REPORT_FILE, {"report": report, "ts": time.time(), "date": time.strftime("%Y-%m-%d")})
        log("早报已写入")
        return

    last_date = None

    while True:
        try:
            now = time.localtime()
            today_str = time.strftime("%Y-%m-%d", now)
            hour = now.tm_hour

            # Run at 08:00 Beijing time, once per day
            if hour == 8 and today_str != last_date:
                log("⏰ 8点了，生成早报…")
                report = build_report()
                save_json(
                    REPORT_FILE,
                    {"report": report, "ts": time.time(), "date": today_str},
                )
                log("早报已生成，等待 bot 读取并唤醒大肥鱼…")
                last_date = today_str
        except Exception as e:
            log(f"出错: {e}")

        time.sleep(60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("退出")
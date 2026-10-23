#!/usr/bin/env python3
# 网易云音乐 每日签到
import os, json, sys
from datetime import datetime, timezone, timedelta
import requests

COOKIE = os.environ.get("NETEASE_COOKIE", "").strip()
if not COOKIE:
    print("错误：缺少 NETEASE_COOKIE"); sys.exit(1)

URL = "https://music.163.com/api/point/dailyTask?type=1"
HEAD = {
    "Cookie": COOKIE,
    "Referer": "https://music.163.com/",
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
}
DATA = "data/netease.json"

r = requests.post(URL, headers=HEAD, timeout=30)
try:
    d = r.json()
except Exception:
    d = {"code": -1, "msg": r.text[:100]}

code = d.get("code")
msg = d.get("msg") or ""
point = d.get("point") or 0
already = (code == -2) and ("重复" in msg)
ok = (code == 200) or already

today = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
print(f"接口返回: {json.dumps(d, ensure_ascii=False)}")

doc = {"updated": "", "history": []}
if os.path.exists(DATA):
    try:
        doc = json.load(open(DATA, encoding="utf-8"))
    except Exception:
        pass
doc.setdefault("history", [])

row = {"date": today, "ok": ok,
       "point": point if code == 200 else 0,
       "msg": "签到成功" if code == 200 else (msg or "失败")}
h = doc["history"]
for i, x in enumerate(h):
    if x.get("date") == today:
        h[i] = row; break
else:
    h.append(row)

doc["history"] = sorted(h, key=lambda x: x.get("date", ""))[-180:]
doc["updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

os.makedirs("data", exist_ok=True)
json.dump(doc, open(DATA, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"{today}: ok={ok} {row['msg']}")

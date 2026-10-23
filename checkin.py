#!/usr/bin/env python3
# GLaDOS 每日签到 + 记录数据（供网页统计）
import os, json, sys
from datetime import datetime, timezone, timedelta
import requests

COOKIE = os.environ.get("GLADOS_COOKIE", "").strip()
if not COOKIE:
    print("错误：缺少 GLADOS_COOKIE"); sys.exit(1)

BASE = "https://glados.network"
HEAD = {
    "Cookie": COOKIE,
    "User-Agent": "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/126.0.0.0 Mobile Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": BASE + "/console",
}
DATA = "data/history.json"

def call(path, method="GET"):
    r = requests.request(method, BASE + path, headers=HEAD, timeout=30)
    try:
        return r.json()
    except Exception:
        return {"code": -1, "raw": r.text[:200]}

res  = call("/api/user/checkin", "POST")
st   = call("/api/user/status").get("data") or {}
pt   = call("/api/user/points")
print("签到返回:", json.dumps(res, ensure_ascii=False)[:200])

points    = float(pt.get("points") or 0)
streak    = int(pt.get("streak") or 0)
plans_raw = pt.get("plans") or {}
left_days = float(st.get("leftDays") or 0)
traffic   = int(st.get("traffic") or 0)
email     = st.get("email") or ""
today     = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")

doc = {"updated": "", "account": {}, "current": {}, "plans": [], "history": []}
if os.path.exists(DATA):
    try:
        doc = json.load(open(DATA, encoding="utf-8"))
    except Exception:
        pass
doc.setdefault("history", [])

ok = res.get("code") == 0
change = 0.0
if ok:
    try:
        change = float(res.get("points") or 0)
    except Exception:
        change = 0.0
    if change == 0:
        for h in pt.get("history", []):
            if h.get("detail") == today and h.get("business") == "system:checkin":
                try: change = float(h.get("change") or 0)
                except Exception: pass

doc["account"] = {"email": email}
doc["current"] = {"points": points, "streak": streak,
                  "leftDays": left_days, "traffic": traffic}
doc["plans"] = ([{"points": v.get("points"), "days": v.get("days")}
                 for v in plans_raw.values()] if isinstance(plans_raw, dict) else [])
doc["updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

row = {"date": today, "ok": ok, "change": change,
       "balance": points, "streak": streak, "leftDays": left_days}
hist = doc["history"]
for i, h in enumerate(hist):
    if h.get("date") == today:
        hist[i] = row; break
else:
    hist.append(row)
doc["history"] = sorted(hist, key=lambda x: x.get("date", ""))[-180:]

os.makedirs("data", exist_ok=True)
json.dump(doc, open(DATA, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"{today}: 签到={ok} +{change} 积分 | 余额={points} 连续={streak}天 剩余={left_days}天")

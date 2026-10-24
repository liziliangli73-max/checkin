#!/usr/bin/env python3
# GLaDOS 每日签到 + 记录数据（供网页统计）
# 退出码：0 = 签到成功或当天已签（无需再跑）；2 = 签到失败（需要人工看一眼）
import os, json, sys, time
from datetime import datetime, timezone, timedelta
import requests

DATA = "data/history.json"
FORCE = os.environ.get("FORCE_CHECKIN", "").strip().lower() in ("1", "true", "yes")


def bj_today():
    return datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")


def load_doc():
    doc = None
    if os.path.exists(DATA):
        try:
            with open(DATA, encoding="utf-8") as f:
                doc = json.load(f)
        except Exception:
            doc = None
    if not isinstance(doc, dict):
        doc = {"updated": "", "account": {}, "current": {}, "plans": [], "history": []}
    doc.setdefault("history", [])
    return doc


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


CHECKED_GAP_H = 4      # 「最近检查」最多 4 小时刷新一次，避免一天几十条提交


def checked_stale(doc):
    old = doc.get("checked")
    if not old:
        return True
    try:
        t = datetime.strptime(old, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except Exception:
        return True
    return (datetime.now(timezone.utc) - t).total_seconds() > CHECKED_GAP_H * 3600


def save_doc(doc):
    """写盘：updated 只在真正签到写入时变，checked 按 4 小时间隔刷新"""
    doc["checked"] = now_iso()
    os.makedirs("data", exist_ok=True)
    with open(DATA, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)


today = bj_today()

# 一天只需要签一次：当天已成功就跳过，省掉重复请求
if not FORCE:
    doc = load_doc()
    for h in doc["history"]:
        if h.get("date") == today and h.get("ok"):
            print(f"{today} 已有成功记录（+{h.get('change')} 积分），本次跳过")
            if checked_stale(doc):
                save_doc(doc)      # 只刷新「最近检查」，页面据此知道任务还活着
            else:
                print("「最近检查」4 小时内已刷新过，本次不写文件")
            sys.exit(0)

COOKIE = os.environ.get("GLADOS_COOKIE", "").strip()
if not COOKIE:
    print("错误：缺少 GLADOS_COOKIE（仓库 secret 没配或已失效）")
    sys.exit(2)

BASE = "https://glados.network"
HEAD = {
    "Cookie": COOKIE,
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": BASE + "/console",
}

def call(path, method="GET", tries=3):
    """网络抖动或 5xx 时自动重试，最多 3 次"""
    err = ""
    for i in range(tries):
        try:
            r = requests.request(method, BASE + path, headers=HEAD, timeout=25)
            if r.status_code >= 500:
                raise requests.RequestException(f"HTTP {r.status_code}")
            try:
                return r.json()
            except Exception:
                return {"code": -1, "raw": r.text[:200]}
        except requests.RequestException as e:
            err = str(e)
            print(f"  请求失败（第 {i+1}/{tries} 次）：{e}")
            if i + 1 < tries:
                time.sleep(8)
    return {"code": -1, "error": err}

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

doc = load_doc()

code = res.get("code")
msg = ((res.get("message") or "") + " " + (res.get("reason") or "")).lower()
already = ("return tomorrow" in msg) or ("already" in msg) or (code == 1)
ok = (code == 0) or already
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

hist = doc["history"]
prev_row = next((h for h in hist if h.get("date") == today), None)
got_profile = bool(email or points or streak or left_days)

# 接口没给出账号信息（cookie 失效/失败）时，别用 0 覆盖上一次的好数据
if got_profile or not doc.get("current"):
    doc["account"] = {"email": email or (doc.get("account") or {}).get("email") or ""}
    doc["current"] = {"points": points, "streak": streak,
                      "leftDays": left_days, "traffic": traffic}
    doc["plans"] = ([{"points": v.get("points"), "days": v.get("days")}
                     for v in plans_raw.values()] if isinstance(plans_raw, dict) else [])
else:
    print("接口没返回账号信息，保留上一次的积分/天数")

# 已经成功的当天记录不会被后来的失败覆盖（避免重试把「已签」改回「失败」）
if ok or not (prev_row and prev_row.get("ok")):
    row = {"date": today, "ok": ok, "change": change,
           "balance": points, "streak": streak, "leftDays": left_days}
    for i, h in enumerate(hist):
        if h.get("date") == today:
            hist[i] = row; break
    else:
        hist.append(row)
    doc["history"] = sorted(hist, key=lambda x: x.get("date", ""))[-180:]
    doc["updated"] = now_iso()
else:
    print("今天已有成功记录，本次失败不覆盖，页面数据保持不变")

save_doc(doc)

if os.environ.get("GITHUB_OUTPUT"):
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
        f.write(f"ok={'true' if ok else 'false'}\n")

print(f"{today}: 签到={ok} +{change} 积分 | 余额={points} 连续={streak}天 剩余={left_days}天")
sys.exit(0 if ok else 2)

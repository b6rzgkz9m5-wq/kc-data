#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# GitHub Actions: 抓取 szggzy 勘察招标+土拍, 生成 data.js 推送到本仓库
# 电脑关机也能跑(由 GitHub 服务器定时执行)
import urllib.request, json, ssl, os, base64, sys
from datetime import datetime, timedelta

CTX = ssl.create_default_context(); CTX.check_hostname=False; CTX.verify_mode=ssl.CERT_NONE

REPO = os.environ.get("GITHUB_REPOSITORY", "b6rzgkz9m5-wq/kc-data")
TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("MY_TOKEN")
if not TOKEN:
    print("ERROR: no GITHUB_TOKEN"); sys.exit(1)
GH_API = "https://api.github.com/repos/%s" % REPO
SZ_LIST = "https://szggzy.com/cms/api/v1/trade/content/page"
SZ_HEADERS = {"Content-Type":"application/json","Referer":"https://szggzy.com/jygg/list.html","Origin":"https://szggzy.com","User-Agent":"Mozilla/5.0"}

CORE = ['勘察','岩土','桩基','超前钻','勘测','地灾','边坡','挡墙','基坑']
STREET = ['街道','社区','旧改','城中村','股份合作']
STREET_GEO = CORE + ['监测','检测']

def geo_hit(title):
    t = title or ''
    if any(k in t for k in CORE): return True
    if any(k in t for k in STREET) and any(k in t for k in STREET_GEO): return True
    return False

def sz_post(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode('utf-8'), headers=SZ_HEADERS, method='POST')
    with urllib.request.urlopen(req, timeout=40, context=CTX) as r:
        return json.loads(r.read().decode('utf-8'))

def fetch_channel(channelId, days):
    items = []
    page = 0
    cutoff = datetime.now() - timedelta(days=days)
    while page < 20:
        body = {"channelId":channelId,"fields":[],"title":None,"releaseTimeBegin":None,"releaseTimeEnd":None,"page":page,"size":50,"modelId":1378}
        try:
            d = sz_post(SZ_LIST, body)
        except Exception as e:
            print("list err ch=%s page=%s : %s" % (channelId, page, e)); break
        rows = (d.get("data") or {}).get("content") or d.get("data") or []
        if not rows: break
        stop = False
        for row in rows:
            pt = (row.get("publishTime") or "")[:10]
            try: pdt = datetime.strptime(pt, "%Y-%m-%d")
            except: pdt = datetime.now()
            if pdt < cutoff: stop = True; break
            items.append(row)
        if stop: break
        if len(rows) < 50: break
        page += 1
    print("ch=%s fetched=%d" % (channelId, len(items)))
    return items

def org_of(row):
    for k in ["tenderer","tenderer2","purchaseCom","purchaseMan","constructCompany"]:
        v = row.get(k)
        if v: return v
    return ""

def build_projects():
    out = []
    seen = set()
    for ch, cat in [(2851,"勘察公告"),(2850,"勘察采购")]:
        for row in fetch_channel(ch, 35):
            title = row.get("noticeTitle","")
            if not geo_hit(title): continue
            cid = str(row.get("contentId",""))
            key = str(ch)+"-"+cid
            if key in seen: continue
            seen.add(key)
            org = org_of(row)
            out.append({
                "id":key, "name":title, "category":cat, "org":org,
                "date":(row.get("publishTime") or "")[:10], "budget":"待定","budgetNum":0,
                "status":"active","deadline":"待定","deadlineDate":"","isOfficial":True,"isPlan":False,
                "link":"https://szggzy.com/jygg/details.html?contentId="+cid,
                "attention":"【"+cat+"】建设单位："+org,
                "detail":{"建设单位":org,"栏目":cat,"发布时间":row.get("publishTime","")}
            })
    for row in fetch_channel(3196, 35):
        pt = row.get("projectType","")
        if pt not in ["其他","勘察","咨询"]: continue
        cid = str(row.get("contentId",""))
        key = "plan"+cid
        if key in seen: continue
        seen.add(key)
        org = org_of(row)
        out.append({
            "id":key, "name":row.get("noticeTitle",""), "category":pt, "org":org,
            "date":(row.get("publishTime") or "")[:10], "budget":"待定","budgetNum":0,
            "status":"plan","deadline":"待定","deadlineDate":"","isOfficial":True,"isPlan":True,
            "link":"https://szggzy.com/jygg/details.html?contentId="+cid,
            "attention":"【"+pt+"】工程类别："+pt+"；建设单位："+org,
            "detail":{"建设单位":org,"栏目":pt,"发布时间":row.get("publishTime","")}
        })
    return out

def build_land():
    out = []
    seen = set()
    for row in fetch_channel(2852, 45):
        cid = str(row.get("contentId",""))
        if cid in seen: continue
        seen.add(cid)
        nt = row.get("noticeType","")
        out.append({
            "id":cid, "code":row.get("projectName","") or "", "name":row.get("noticeTitle",""),
            "district":row.get("areaName") or row.get("projectRegion","") or "",
            "use":"—","area":0,"dealPrice":0,
            "winner":row.get("winnerName") or "—",
            "dealDate":(row.get("publishTime") or "")[:10],
            "status":"done" if nt=="2" else "listing",
            "link":"https://szggzy.com/jygg/details.html?contentId="+cid
        })
    return out

def gh_get(path):
    req = urllib.request.Request(GH_API+"/contents/"+path, headers={"Authorization":"token "+TOKEN,"Accept":"application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=30, context=CTX) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        print("gh_get %s err: %s" % (path, e)); return None

def gh_put(path, content_bytes, message):
    obj = gh_get(path)
    sha = obj.get("sha") if obj else None
    body = {"message":message, "content":base64.b64encode(content_bytes).decode("ascii")}
    if sha: body["sha"] = sha
    req = urllib.request.Request(GH_API+"/contents/"+path, data=json.dumps(body).encode("utf-8"), method="PUT",
        headers={"Authorization":"token "+TOKEN,"Content-Type":"application/json","Accept":"application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=60, context=CTX) as r:
        return json.loads(r.read().decode())

def main():
    print("=== 抓取开始 (GitHub Actions) ===")
    auto_projects = build_projects()
    auto_land = build_land()
    print("auto_projects=%d auto_land=%d" % (len(auto_projects), len(auto_land)))

    # 从现有 data.js 提取手工项目(id 不以 plan/2851-/2850-/3196- 开头)
    obj = gh_get("data.js")
    manual = []
    old_count = 0
    if obj:
        try:
            raw = base64.b64decode(obj["content"]).decode("utf-8")
            i = raw.find("{"); j = raw.rfind("}")
            old = json.loads(raw[i:j+1]) if i>=0 and j>=0 else {}
            old_projects = old.get("projects", [])
            old_count = len(old_projects)
            autoPrefix = ["plan","2851-","2850-","3196-"]
            manual = [p for p in old_projects if not any(str(p.get("id","")).startswith(pre) for pre in autoPrefix)]
            print("old_projects=%d manual=%d" % (old_count, len(manual)))
        except Exception as e:
            print("parse old data.js err: %s" % e)

    # 防清空守卫
    if len(auto_projects) == 0:
        print("GUARD: 抓取为0, 不覆盖 data.js, 保留上次数据"); return
    if old_count > 0 and len(auto_projects) < old_count * 0.3:
        print("GUARD: 抓取量(%d) < 现有30%%(%d), 可能异常, 不覆盖" % (len(auto_projects), int(old_count*0.3))); return

    new_projects = auto_projects + manual
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    data = {"update":now, "projects":new_projects, "land":auto_land}
    text = "window.__DATA__=" + json.dumps(data, ensure_ascii=False) + ";"

    c = gh_put("data.js", text.encode("utf-8"), "update data.js (Actions) "+now)
    print("pushed commit: %s" % c.get("commit",{}).get("sha","?")[:10])
    print("total projects=%d land=%d update=%s" % (len(new_projects), len(auto_land), now))
    print("=== 完成 ===")

if __name__ == "__main__":
    main()

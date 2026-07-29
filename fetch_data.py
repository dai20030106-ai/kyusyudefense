# -*- coding: utf-8 -*-
"""九州災害情報ダッシュボード データ取得
防衛省会見(給水・支援) / JR九州(鉄道・事実の要約のみ) を取得し data.json を出力。
停電・道路は方針により link_only。失敗時は unavailable を出力し、決して落ちない。
出典: 防衛省ウェブサイト(公共データ利用規約PDL1.0), JR九州(事実の記述+リンク)
"""
import json, re, sys, urllib.request
from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))
NOW = datetime.now(JST)
PREFS = {"40":"福岡県","41":"佐賀県","42":"長崎県","43":"熊本県","44":"大分県","45":"宮崎県","46":"鹿児島県"}
JRAREA = {"40":"fukhok","41":"sagnag","42":"sagnag","43":"kuma","44":"oita","45":"miya","46":"kago"}
UA = {"User-Agent":"kyusyu-dashboard/0.1 (personal non-commercial; github.com/dai20030106-ai/kyusyudefense)"}

def get(url, timeout=25):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")

items = []
def add(**kw):
    d = {"id":None,"category":None,"pref":None,"level":"unknown","headline":"",
         "detail":None,"note":None,"source_name":None,"source_url":None,
         "source_updated_at":None,"status":"ok"}
    d.update(kw); items.append(d)

def wareki_to_iso(s):
    m = re.search(r"令和(\d+)年(\d+)月(\d+)日", s)
    if not m: return None
    y = 2018 + int(m.group(1))
    t = re.search(r"(\d{1,2}):(\d{2})", s)
    return datetime(y,int(m.group(2)),int(m.group(3)),
                    int(t.group(1)) if t else 0, int(t.group(2)) if t else 0,
                    tzinfo=JST).isoformat(timespec="seconds")

# ---------- 防衛省（給水・支援） ----------
try:
    js = get("https://www.mod.go.jp/j/press/kisha/kisha_ja.js")
    ent = re.findall(r'date:"([^"]+)"[^}]*?title:"([^"]+)"[^}]*?url:"([^"]+)"', js)
    dis = [(d,t,u) for d,t,u in ent if ("地震" in t or "災害" in t)]
    if dis:
        d,t,u = dis[0]
        full = "https://www.mod.go.jp/j/press/kisha/" + u
        body = re.sub(r"<[^>]+>"," ",get(full))
        body = re.sub(r"\s+"," ",body)
        sents = [s.strip() for s in body.split("。") if s.strip()]
        water = [s for s in sents if "給水" in s]
        jsdf  = [s for s in sents if ("態勢" in s or "人命救助" in s or "救助活動" in s)]
        iso = wareki_to_iso(d)
        add(id="gov.mod",category="gov",pref="43",level="alert",headline=t,detail=d,
            note=("。".join(jsdf[:2])+"。")[:300] if jsdf else None,
            source_name="防衛省（大臣会見）",source_url=full,source_updated_at=iso)
        if water:
            add(id="water.mod",category="water",pref="43",level="good",
                headline="自衛隊が給水支援を実施・準備中",
                note=("。".join(water[:2])+"。")[:300],
                source_name="防衛省（大臣会見）",source_url=full,source_updated_at=iso)
    else:
        add(id="gov.mod",category="gov",pref=None,level="normal",
            headline="現在、災害に関する防衛省の発表はありません",
            source_name="防衛省",source_url="https://www.mod.go.jp/j/press/kisha/index.html")
except Exception as e:
    print("MOD error:", e, file=sys.stderr)
    add(id="gov.mod",category="gov",pref=None,level="unknown",
        headline="現在、防衛省の情報を取得できていません",
        source_name="防衛省",source_url="https://www.mod.go.jp/j/press/kisha/index.html",
        status="unavailable")

# ---------- JR九州（事実の要約のみ・本文転載しない） ----------
try:
    t = re.sub(r"<[^>]+>"," ",get("https://www.jrkyushu.co.jp/trains/info/inc/info_top.html"))
    t = re.sub(r"\s+"," ",t)
    md = re.search(r"(\d{1,2})月(\d{1,2})日",t)
    tm = re.search(r"(\d{1,2}):(\d{2})現在",t)
    iso = None
    if md:
        iso = datetime(NOW.year,int(md.group(1)),int(md.group(2)),
                       int(tm.group(1)) if tm else 0,int(tm.group(2)) if tm else 0,
                       tzinfo=JST).isoformat(timespec="seconds")
    if "運行取り止め" in t or "運休" in t:
        head, lvl = "一部線区で運休が発生しています（JR九州発表）","alert"
    elif "遅れ" in t:
        head, lvl = "遅れ等が発生しています（JR九州発表）","watch"
    else:
        head, lvl = "大きな運行支障の発表はありません","normal"
    # 鮮度検証: 本文日付が3日以上前なら stale
    stale = False
    if iso and (NOW - datetime.fromisoformat(iso)).days >= 3:
        stale = True
    for c in PREFS:
        if stale:
            add(id=f"rail.{c}",category="rail",pref=c,level="unknown",
                headline="最新の運行情報を取得できていません",
                source_name="JR九州",source_url=f"https://www.jrkyushu.co.jp/trains/info/{JRAREA[c]}.html",
                source_updated_at=iso,status="stale")
        else:
            add(id=f"rail.{c}",category="rail",pref=c,level=lvl,headline=head,
                detail="線区ごとの詳細は公式ページ・PDFで公開されています",
                source_name="JR九州",source_url=f"https://www.jrkyushu.co.jp/trains/info/{JRAREA[c]}.html",
                source_updated_at=iso)
except Exception as e:
    print("JR error:", e, file=sys.stderr)
    for c in PREFS:
        add(id=f"rail.{c}",category="rail",pref=c,level="unknown",
            headline="現在、運行情報を取得できていません",
            source_name="JR九州",source_url=f"https://www.jrkyushu.co.jp/trains/info/{JRAREA[c]}.html",
            status="unavailable")

# ---------- 停電・道路（方針により link_only） ----------
for c in PREFS:
    add(id=f"power.{c}",category="power",pref=c,
        headline="停電の状況については、九州電力送配電のページをご参照ください",
        source_name="九州電力送配電",
        source_url=f"https://www.kyuden.co.jp/td_teiden/syousai.html?pref={c}",
        status="link_only")
    add(id=f"road.{c}",category="road",pref=c,
        headline="高速道路の通行止め状況は、NEXCO西日本のページをご参照ください",
        source_name="NEXCO西日本",
        source_url="https://ihighway.jp/pcsite/",
        status="link_only")

json.dump({"generated_at":NOW.isoformat(timespec="seconds"),"items":items},
          open("data.json","w",encoding="utf-8"),ensure_ascii=False,indent=1)
print("wrote data.json:",len(items),"items")

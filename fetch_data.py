# -*- coding: utf-8 -*-
"""九州災害情報ダッシュボード データ取得 v2
具体的な事実（給水の場所・か所数 / 高速道路の通行止め区間 / 鉄道の不通線区）を
構造化して data.json に出力する。本文の転載はせず、事実のみを要約する。
失敗時は unavailable を出力し、決して落ちない。
"""
import json, re, sys, urllib.request
from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))
NOW = datetime.now(JST)
PREFS = {"40":"福岡県","41":"佐賀県","42":"長崎県","43":"熊本県","44":"大分県","45":"宮崎県","46":"鹿児島県"}
JRAREA = {"40":"fukhok","41":"sagnag","42":"sagnag","43":"kuma","44":"oita","45":"miya","46":"kago"}
UA = {"User-Agent":"kyusyu-dashboard/0.2 (personal non-commercial; github.com/dai20030106-ai/kyusyudefense)"}

def get(url, timeout=25):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")

def strip_tags(h):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h))

Z2H = str.maketrans("０１２３４５６７８９ＩＣＪＴＢＥ～", "0123456789ICJTBE〜")
def norm(s): return s.translate(Z2H).replace("～","〜")

items = []
def add(**kw):
    d = {"id":None,"category":None,"pref":None,"level":"unknown","headline":"",
         "detail":None,"note":None,"source_name":None,"source_url":None,
         "source_updated_at":None,"status":"ok"}
    d.update(kw); items.append(d)

def wareki_to_iso(s):
    m = re.search(r"令和(\d+)年(\d+)月(\d+)日", s)
    if not m: return None
    t = re.search(r"(\d{1,2}):(\d{2})", s)
    return datetime(2018+int(m.group(1)),int(m.group(2)),int(m.group(3)),
                    int(t.group(1)) if t else 0,int(t.group(2)) if t else 0,
                    tzinfo=JST).isoformat(timespec="seconds")

# ---------- 防衛省（給水の場所を構造化） ----------
try:
    js = get("https://www.mod.go.jp/j/press/kisha/kisha_ja.js")
    ent = re.findall(r'date:"([^"]+)"[^}]*?title:"([^"]+)"[^}]*?url:"([^"]+)"', js)
    dis = [(d,t,u) for d,t,u in ent if ("地震" in t or "災害" in t)]
    if dis:
        d,t,u = dis[0]
        full = "https://www.mod.go.jp/j/press/kisha/" + u
        body = strip_tags(get(full))
        sents = [s.strip() for s in body.split("。") if s.strip()]
        water = [s for s in sents if "給水" in s]
        jsdf  = [s for s in sents if ("態勢" in s or "人命救助" in s or "救助活動" in s)]
        iso = wareki_to_iso(d)
        add(id="gov.mod",category="gov",pref=None,level="alert",headline=t,detail=d,
            note=("。".join(jsdf[:2])+"。")[:300] if jsdf else None,
            source_name="防衛省（大臣会見）",source_url=full,source_updated_at=iso)
        if water:
            wtxt = norm("。".join(water))
            spots = re.findall(r"([一-龥]{1,6}(?:市|町|村))(?:[^。0-9]{0,4})([0-9]+)\s*か所", wtxt)
            tm = re.search(r"(午前|午後)?\s*([0-9]+)\s*時\s*([0-9]+)?\s*分?\s*以降", wtxt)
            plan = []
            for s in water:
                if "予定" in s:
                    plan += re.findall(r"([一-龥]{1,6}(?:市|町|村))", norm(s))
            plan = [p for p in dict.fromkeys(plan) if p not in [a for a,_ in spots]]
            det = []
            if spots:
                det.append("実施中: " + " ／ ".join(f"{a} {n}か所" for a,n in spots)
                           + (f"（{tm.group(0)}）" if tm else ""))
            if plan:
                det.append("開始予定: " + "・".join(plan))
            add(id="water.mod",category="water",pref="43",level="good",
                headline="自衛隊の給水支援",
                detail=" ／ ".join(det) if det else None,
                note=None if det else ("。".join(water[:2])+"。")[:300],
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

# ---------- NEXCO西日本（通行止め区間を構造化） ----------
try:
    top = get("https://www.w-nexco.co.jp/")
    ems = re.findall(r'href="[^"]*?(/emc/\d+\.html)"', top)
    if ems:
        eurl = "https://www.w-nexco.co.jp" + sorted(set(ems))[-1]
        et = norm(strip_tags(get(eurl)))
        ts = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日(\d{1,2})時(\d{1,2})分\s*現在", et)
        iso = None
        if ts:
            iso = datetime(int(ts.group(1)),int(ts.group(2)),int(ts.group(3)),
                           int(ts.group(4)),int(ts.group(5)),tzinfo=JST).isoformat(timespec="seconds")
        parts = re.split(r"解除", et, maxsplit=1)
        SEC = r"([一-龥A-Z0-9]{2,14}(?:自動車道|道路|道))\s*(?:上下線|上り線|下り線)?\s*([一-龥ぁ-んA-Za-z0-9]{1,12}(?:IC|JCT|TB))\s*〜\s*([一-龥ぁ-んA-Za-z0-9]{1,12}(?:IC|JCT|TB))"
        closed = [f"{a} {b}〜{c}" for a,b,c in re.findall(SEC, parts[0])]
        opened = [f"{a} {b}〜{c}" for a,b,c in re.findall(SEC, parts[1])] if len(parts)>1 else []
        closed = list(dict.fromkeys(closed)); opened = [o for o in dict.fromkeys(opened) if o not in closed]
        if closed or opened:
            add(id="road.emc",category="road",pref=None,
                level="alert" if closed else "good",
                headline=(f"高速道路 通行止め {len(closed)}区間" if closed else "通行止めは解除されました"),
                detail=" ／ ".join(closed) if closed else None,
                note=("解除済み: " + " ／ ".join(opened)) if opened else None,
                source_name="NEXCO西日本",source_url=eurl,source_updated_at=iso)
except Exception as e:
    print("NEXCO error:", e, file=sys.stderr)

# ---------- JR九州（不通・運休の線区を構造化） ----------
try:
    t = strip_tags(get("https://www.jrkyushu.co.jp/trains/info/inc/info_top.html"))
    md = re.search(r"(\d{1,2})月(\d{1,2})日", t)
    tm = re.search(r"(\d{1,2}):(\d{2})現在", t)
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
    lines = []
    try:
        mid = norm(strip_tags(get("https://www.jrkyushu.co.jp/trains/info/inc/info_mid.html")))
        for m in re.finditer(r"([一-龥ぁ-んA-Z0-9]{2,10}線)\s*[（(]?\s*([一-龥ぁ-ん0-9]{1,8}\s*[〜.・～]\s*[一-龥ぁ-ん0-9]{1,8})\s*(?:間)?[)）]?\s*[^。|]{0,25}?(不通|運転を取りやめ)", mid):
            lines.append(f"{m.group(1)} {m.group(2).replace(' ','')}")
        lines = list(dict.fromkeys(lines))[:8]
    except Exception:
        pass
    stale = bool(iso and (NOW - datetime.fromisoformat(iso)).days >= 3)
    for c in PREFS:
        if stale:
            add(id=f"rail.{c}",category="rail",pref=c,level="unknown",
                headline="最新の運行情報を取得できていません",
                source_name="JR九州",source_url=f"https://www.jrkyushu.co.jp/trains/info/{JRAREA[c]}.html",
                source_updated_at=iso,status="stale")
        else:
            add(id=f"rail.{c}",category="rail",pref=c,level=lvl,headline=head,
                detail=("運転見合わせ中の線区（九州全体）: " + " ／ ".join(lines)) if lines else "線区ごとの詳細は公式ページ・PDFで公開されています",
                source_name="JR九州",source_url=f"https://www.jrkyushu.co.jp/trains/info/{JRAREA[c]}.html",
                source_updated_at=iso)
except Exception as e:
    print("JR error:", e, file=sys.stderr)
    for c in PREFS:
        add(id=f"rail.{c}",category="rail",pref=c,level="unknown",
            headline="現在、運行情報を取得できていません",
            source_name="JR九州",source_url=f"https://www.jrkyushu.co.jp/trains/info/{JRAREA[c]}.html",
            status="unavailable")

# ---------- 通行実績マップ（トヨタ・ホンダ）----------
# トヨタの「優先表示」に載っている災害エリアから対象県を判定し、該当県にだけ表示する。
# （全国共通ページのため、判定せずに出すと無関係な地域の情報を見せてしまう）
try:
    ty = strip_tags(get("https://www.toyota.co.jp/jpn/auto/passable_route/map/", timeout=20))
    seg = ty.split("優先表示")[1].split("北海道")[0] if "優先表示" in ty else ""
    targets = {}
    for ent in re.findall(r"([^\[\]\s]+?_\d{8,12})", seg):
        for code, pname in PREFS.items():
            if pname in ent or pname.replace("県","") in ent:
                label = ent.split("_")[0]
                dt = re.search(r"_(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})", ent)
                if dt:
                    label += f"（{int(dt.group(2))}/{int(dt.group(3))} {dt.group(4)}:{dt.group(5)}〜）"
                targets.setdefault(code, label)
    for c in PREFS:
        if c in targets:
            add(id=f"passable.{c}", category="passable", pref=c, level="good",
                headline="実際に通れた道の地図が公開されています",
                detail=f"対象エリア: {targets[c]} ／ 自動車メーカーが走行データをもとに直近24時間に通行実績のあった道を地図で公開しています",
                note="通行実績があっても現在通行できるとは限りません。緊急交通路など規制されている場合があるため、現地の規制・誘導に従ってください。",
                source_name="トヨタ 通れた道マップ",
                source_url="https://www.toyota.co.jp/jpn/auto/passable_route/map/")
            add(id=f"passable2.{c}", category="passable", pref=c, level="good",
                headline="通行実績情報マップ（ホンダ）",
                detail="インターナビ装着車の走行軌跡から作成された通行実績です",
                source_name="ホンダ／ゼンリンデータコム",
                source_url="https://disaster-map.its-mo.com/")
        else:
            add(id=f"passable.{c}", category="passable", pref=c, level="normal",
                headline="この県を対象とした通行実績マップは公開されていません",
                detail="大きな災害の際に、自動車メーカーが「実際に通れた道」の地図を対象地域向けに公開することがあります。")
except Exception as e:
    print("passable error:", e, file=sys.stderr)
    for c in PREFS:
        add(id=f"passable.{c}", category="passable", pref=c, level="unknown",
            headline="通行実績マップの公開状況を取得できていません",
            source_name="トヨタ 通れた道マップ",
            source_url="https://www.toyota.co.jp/jpn/auto/passable_route/map/",
            status="unavailable")

# ---------- 停電（link_only）・道路の県別リンク ----------
for c in PREFS:
    add(id=f"power.{c}",category="power",pref=c,
        headline="停電の状況については、九州電力送配電のページをご参照ください",
        source_name="九州電力送配電",
        source_url=f"https://www.kyuden.co.jp/td_teiden/syousai.html?pref={c}",
        status="link_only")
    add(id=f"road.{c}",category="road",pref=c,
        headline="渋滞・工事などリアルタイムの道路状況はこちら",
        source_name="NEXCO西日本 iHighway",
        source_url="https://ihighway.jp/pcsite/",
        status="link_only")

json.dump({"generated_at":NOW.isoformat(timespec="seconds"),"items":items},
          open("data.json","w",encoding="utf-8"),ensure_ascii=False,indent=1)
print("wrote data.json:",len(items),"items")

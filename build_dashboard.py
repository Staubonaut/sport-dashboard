#!/usr/bin/env python3
"""
build_dashboard.py — Generiert das Sport Dashboard (index.html)
Liest Strava CSV, Gym-Logfiles & Gewichtsdaten und erstellt eine
professionelle, interaktive Single-Page App als einzelne HTML-Datei.

Usage:
    python3 build_dashboard.py
"""

import os, re, csv, json
from datetime import datetime, date, timedelta
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).parent

# ─────────────────────────────────────────────────────────────────────
# DATA LOADING
# ─────────────────────────────────────────────────────────────────────

PUSH_KEYS = ["bankdrücken","brustpresse","butterfly","dip","schulterpresse",
             "seitenheben","trizeps","triceps","french press","incline","decline","chest","cable cross"]
PULL_KEYS = ["latzug","latpull","rudern","klimmzug","curls","bizeps","hammer curl",
             "rückenzug","t bar","t-bar","preacher","facepull","face pull"]
LEG_KEYS  = ["hackenschmidt","hacksquat","beinstrecker","beinbeuger","kniebeuge",
             "wadenpresse","wadenheben","beinpresse","leg press","squat"]


def classify_session(lines):
    text = " ".join(lines).lower()
    p  = sum(1 for k in PUSH_KEYS if k in text)
    pu = sum(1 for k in PULL_KEYS if k in text)
    l  = sum(1 for k in LEG_KEYS  if k in text)
    total = p + pu + l
    if total == 0: return "Sonstiges"
    if l > 0 and p == 0 and pu == 0: return "Beine"
    if p > 0 and pu > 0: return "Push+Pull"
    if l > 0 and p > 0: return "Push+Beine"
    if l > 0 and pu > 0: return "Pull+Beine"
    if p >= pu: return "Push"
    return "Pull"


def parse_gym_date(fname):
    m = re.match(r"(\d{2})(\d{2})(\d{4})", fname)
    if m:
        try: return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except: pass
    return None


def parse_exercises(lines):
    exercises = []
    current_ex = None
    current_weight = None
    for line in lines:
        l = line.strip()
        if not l: continue
        low = l.lower()
        is_name = (l and not l[0].isdigit() and "kg" not in low
                   and "x" not in low.replace("extra","").replace("max","")
                   and l not in ["↑","→","—","-"] and len(l) > 2
                   and not low.startswith("aufwärm"))
        if is_name:
            current_ex = l
            current_weight = None
            continue
        if current_ex:
            wm = re.match(r"(\d+(?:[.,]\d+)?)\s*kg", low.replace(" ",""))
            if wm:
                current_weight = float(wm.group(1).replace(",","."))
                continue
            rm = re.match(r"(\d+)\s*x\s*(\d+)", low.replace(" ",""))
            if rm and current_weight:
                sets = int(rm.group(1))
                reps = int(rm.group(2))
                exercises.append({
                    "name": current_ex,
                    "weight": current_weight,
                    "sets": sets,
                    "reps": reps,
                    "volume": current_weight * sets * reps
                })
    return exercises


def extract_bench(lines):
    in_bench = False
    current_weight = None
    best = None
    for line in lines:
        l = line.strip().lower()
        if "bankdrücken" in l or "bank drücken" in l:
            in_bench = True; continue
        if in_bench and l and not l[0].isdigit() and "kg" not in l and "x" not in l and l not in ["","↑","→"]:
            if any(k in l for k in PUSH_KEYS + PULL_KEYS + LEG_KEYS):
                if "bankdrücken" not in l: in_bench = False
        if in_bench:
            m = re.match(r"(\d+(?:[.,]\d+)?)kg", l.replace(" ",""))
            if m: current_weight = float(m.group(1).replace(",","."))
        if in_bench and current_weight:
            m = re.match(r"(\d+)x(\d+)", l.replace(" ",""))
            if m:
                reps = int(m.group(2))
                if reps >= 4:
                    if best is None or current_weight > best[0]:
                        best = (current_weight, reps)
    return best


def load_gym():
    gymdir = BASE / "imports" / "gym"
    sessions = []
    for fname in sorted(os.listdir(gymdir)):
        if not fname.endswith(".txt"): continue
        d = parse_gym_date(fname)
        if not d: continue
        with open(gymdir / fname, encoding="utf-8", errors="ignore") as f:
            lines = [l.rstrip() for l in f.readlines()]
        stype = classify_session(lines)
        exercises = parse_exercises(lines)
        bench = extract_bench(lines)
        total_vol = sum(e["volume"] for e in exercises)
        # Simplify exercises for JSON
        ex_summary = {}
        for e in exercises:
            name = e["name"]
            if name not in ex_summary:
                ex_summary[name] = {"w": e["weight"], "sets": 0, "reps": 0, "vol": 0}
            ex_summary[name]["sets"] += e["sets"]
            ex_summary[name]["reps"] += e["sets"] * e["reps"]
            ex_summary[name]["vol"] += e["volume"]
            if e["weight"] > ex_summary[name]["w"]:
                ex_summary[name]["w"] = e["weight"]
        sessions.append({
            "d": d.isoformat(),
            "t": stype,
            "vol": round(total_vol),
            "n": len(ex_summary),
            "bench": [bench[0], bench[1]] if bench else None,
            "ex": [{"name": k, "w": v["w"], "s": v["sets"], "r": v["reps"], "v": round(v["vol"])}
                   for k, v in ex_summary.items()]
        })
    sessions.sort(key=lambda x: x["d"])

    # Add Notion-sourced sessions not yet in txt files
    notion_extras = [
        {
            "d": "2026-04-13",
            "t": "Push",
            "vol": round(30*1*8 + 35*1*8 + 40*1*8 + 60*1*8 + 85*1*7 + 85*1*5 + 80*1*7 + 20*1*8 + 20*1*7 + 20*1*8 + 20*1*5),
            "n": 3,
            "bench": [85, 7],
            "ex": [
                {"name": "Butterfly Kabelturm", "w": 40, "s": 3, "r": 24, "v": round(30*8+35*8+40*8)},
                {"name": "Bankdrücken", "w": 85, "s": 4, "r": 27, "v": round(60*8+85*7+85*5+80*7)},
                {"name": "Dips (Support)", "w": 20, "s": 4, "r": 28, "v": round(20*8+20*7+20*8+20*5)},
            ]
        },
        {
            "d": "2026-04-14",
            "t": "Pull+Beine",
            "vol": round(
                20*1*8 + 15*2*6 +           # Klimmzug Support
                70*2*8 +                     # Latzug eng
                70*1*7 + 70*1*6 +            # Latzug breit
                60*1*8 + 60*2*10 +           # Rudern Maschine
                60*1*8 + 60*1*10 +           # Rudern Kabelzug
                80*2*8 +                     # Latzug Maschine
                20*1*5 + 18*1*6 + 16*2*8 +  # Hammer Curls
                40*2*8 +                     # Preacher Curls
                55*1*10 + 70*1*10 + 80*2*10 + 80*1*8 +  # Beinbeuger
                60*1*15 + 80*1*13 + 80*2*12             # Wadenpresse
            ),
            "n": 10,
            "bench": None,
            "ex": [
                {"name": "Klimmzug (Support)", "w": 20, "s": 3, "r": 20, "v": round(20*8+15*12)},
                {"name": "Latzug eng", "w": 70, "s": 2, "r": 16, "v": round(70*2*8)},
                {"name": "Latzug breit", "w": 70, "s": 2, "r": 13, "v": round(70*13)},
                {"name": "Rudern Maschine", "w": 60, "s": 3, "r": 28, "v": round(60*1*8+60*2*10)},
                {"name": "Rudern Kabelzug", "w": 60, "s": 2, "r": 18, "v": round(60*18)},
                {"name": "Latzug Maschine", "w": 80, "s": 2, "r": 16, "v": round(80*2*8)},
                {"name": "Hammer Curls", "w": 20, "s": 4, "r": 27, "v": round(20*5+18*6+16*2*8)},
                {"name": "Preacher Curls Maschine", "w": 40, "s": 2, "r": 16, "v": round(40*2*8)},
                {"name": "Beinbeuger", "w": 80, "s": 5, "r": 48, "v": round(55*10+70*10+80*2*10+80*8)},
                {"name": "Wadenpresse sitzend", "w": 80, "s": 4, "r": 52, "v": round(60*15+80*13+80*2*12)},
            ]
        },
    ]
    existing_dates = {s["d"] for s in sessions}
    for extra in notion_extras:
        if extra["d"] not in existing_dates:
            sessions.append(extra)
    sessions.sort(key=lambda x: x["d"])

    return sessions


def load_runs():
    csv_path = BASE / "imports" / "strava" / "activities.csv"
    if not csv_path.exists():
        return []
    runs = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        headers = next(reader)
        for row in reader:
            if row[3] != "Run": continue
            try:
                dt = datetime.strptime(row[1].strip(), "%b %d, %Y, %I:%M:%S %p")
            except: continue
            dist_m = float(row[17] or 0)
            dist_km = dist_m / 1000
            if dist_km < 0.5: continue  # Skip very short entries
            moving_s = float(row[16] or 0)
            avg_speed = float(row[19] or 0)
            if avg_speed > 0:
                pace = (1000 / avg_speed) / 60
            elif dist_km > 0 and moving_s > 0:
                pace = (moving_s / 60) / dist_km
            else:
                pace = 0
            hr_avg = round(float(row[31])) if row[31] else None
            hr_max = round(float(row[30])) if row[30] else None
            cal = round(float(row[34])) if row[34] else None
            elev = round(float(row[20]), 1) if row[20] else 0
            cadence = round(float(row[29])) if row[29] else None
            runs.append({
                "d": dt.strftime("%Y-%m-%d"),
                "km": round(dist_km, 2),
                "sec": int(moving_s),
                "pace": round(pace, 2),
                "hr": hr_avg,
                "hrMax": hr_max,
                "cal": cal,
                "elev": round(elev),
                "cad": cadence,
                "name": row[2],
            })
    runs.sort(key=lambda x: x["d"])
    return runs


def load_weight():
    wp = BASE / "fortschritt" / "gewicht.md"
    if not wp.exists(): return []
    entries = []
    with open(wp, encoding="utf-8") as f:
        for line in f:
            m = re.match(r"\|\s*(\d{2}\.\d{2}\.\d{4})\s*\|\s*~?(\d+(?:[.,]\d+)?)\s*", line)
            if m:
                d = datetime.strptime(m.group(1), "%d.%m.%Y").strftime("%Y-%m-%d")
                w = float(m.group(2).replace(",", "."))
                entries.append({"d": d, "kg": w})
    return entries


# ─────────────────────────────────────────────────────────────────────
# HTML TEMPLATE
# ─────────────────────────────────────────────────────────────────────

def generate_html(runs, gym, weight):
    runs_json = json.dumps(runs, ensure_ascii=False)
    gym_json = json.dumps(gym, ensure_ascii=False)
    weight_json = json.dumps(weight, ensure_ascii=False)

    return f'''<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>Sport Dashboard</title>
<style>
:root {{
  --bg: #090a0f;
  --s0: #0e1018;
  --s1: #141722;
  --s2: #1c2030;
  --s3: #252a3a;
  --border: #252a3a;
  --blue: #4f8ef7;
  --blue2: #3a6fd8;
  --green: #34c77b;
  --green2: #28a966;
  --yellow: #f7c948;
  --red: #e05c6e;
  --purple: #a78bfa;
  --cyan: #22d3ee;
  --text: #e8eaf0;
  --text2: #c0c4d4;
  --muted: #6b7194;
  --radius: 10px;
  --radius-sm: 6px;
}}
*{{box-sizing:border-box;margin:0;padding:0;}}
html{{scroll-behavior:smooth;}}
body{{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI","Inter",sans-serif;font-size:14px;line-height:1.5;overflow-x:hidden;}}
::selection{{background:var(--blue);color:#fff;}}
::-webkit-scrollbar{{width:6px;}}
::-webkit-scrollbar-track{{background:var(--s0);}}
::-webkit-scrollbar-thumb{{background:var(--s3);border-radius:3px;}}

/* ── NAV ── */
.nav{{position:sticky;top:0;z-index:100;background:rgba(14,16,24,.85);backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);border-bottom:1px solid var(--border);}}
.nav-inner{{max-width:1200px;margin:0 auto;display:flex;align-items:center;padding:0 24px;height:52px;gap:8px;}}
.nav-brand{{font-weight:700;font-size:15px;margin-right:24px;color:var(--text);letter-spacing:-.01em;}}
.nav-brand span{{color:var(--blue);}}
.nav-tabs{{display:flex;gap:2px;}}
.nav-tab{{padding:6px 16px;border-radius:var(--radius-sm);font-size:13px;font-weight:500;color:var(--muted);cursor:pointer;transition:.15s;border:none;background:none;}}
.nav-tab:hover{{color:var(--text2);background:var(--s2);}}
.nav-tab.active{{color:var(--text);background:var(--s2);}}
.nav-indicator{{display:none;}}

/* ── LAYOUT ── */
.page{{display:none;max-width:1200px;margin:0 auto;padding:24px 24px 80px;}}
.page.active{{display:block;animation:fadeIn .25s ease;}}
@keyframes fadeIn{{from{{opacity:0;transform:translateY(6px)}}to{{opacity:1;transform:translateY(0)}}}}

/* ── GRID ── */
.grid{{display:grid;gap:16px;}}
.grid-4{{grid-template-columns:repeat(4,1fr);}}
.grid-3{{grid-template-columns:repeat(3,1fr);}}
.grid-2{{grid-template-columns:repeat(2,1fr);}}
@media(max-width:900px){{.grid-4,.grid-3{{grid-template-columns:repeat(2,1fr);}}}}
@media(max-width:600px){{.grid-4,.grid-3,.grid-2{{grid-template-columns:1fr;}}}}

/* ── CARDS ── */
.card{{background:var(--s1);border:1px solid var(--border);border-radius:var(--radius);padding:20px;transition:border-color .2s;}}
.card:hover{{border-color:var(--s3);}}
.card-lg{{padding:24px;}}

/* ── KPI ── */
.kpi{{text-align:center;padding:20px 12px;}}
.kpi .value{{font-size:28px;font-weight:700;letter-spacing:-.02em;line-height:1.2;}}
.kpi .label{{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.08em;margin-top:4px;}}
.kpi .sub{{font-size:12px;color:var(--muted);margin-top:2px;}}
.kpi .trend{{font-size:11px;margin-top:3px;font-weight:600;}}
.kpi .trend.up{{color:var(--green);}}
.kpi .trend.down{{color:var(--red);}}
.kpi .mini-bar{{height:4px;background:var(--s3);border-radius:99px;margin:8px auto 0;width:80%;overflow:hidden;}}
.kpi .mini-bar-fill{{height:100%;border-radius:99px;transition:width .6s ease;}}

/* ── DASH WEEKLY ── */
.week-row{{display:flex;gap:6px;align-items:flex-end;height:100%;}}
.week-col{{flex:1;display:flex;flex-direction:column;align-items:center;gap:4px;min-width:0;}}
.week-col.current{{background:rgba(79,142,247,.06);border-radius:var(--radius-sm);margin:-4px -2px;padding:4px 2px;}}
.week-bars{{display:flex;flex-direction:column;gap:1px;width:100%;height:100%;justify-content:flex-end;}}
.week-bar{{width:100%;border-radius:2px;min-height:0;transition:height .4s ease;}}
.week-label{{font-size:9px;color:var(--muted);white-space:nowrap;}}
.week-count{{font-size:11px;font-weight:600;}}

/* ── FEED ── */
.feed-item{{display:flex;align-items:center;gap:12px;padding:12px 0;border-bottom:1px solid var(--border);cursor:pointer;transition:background .15s;}}
.feed-item:last-child{{border-bottom:none;}}
.feed-item:hover{{background:var(--s2);margin:0 -12px;padding:12px;border-radius:var(--radius-sm);}}
.feed-dot{{width:36px;height:36px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:14px;flex-shrink:0;}}
.feed-body{{flex:1;min-width:0;}}
.feed-title{{font-size:13px;font-weight:600;}}
.feed-meta{{font-size:11px;color:var(--muted);}}
.feed-value{{font-size:15px;font-weight:700;text-align:right;white-space:nowrap;}}

/* ── MONTH SUMMARY ── */
.month-stat{{display:flex;justify-content:space-between;align-items:center;padding:10px 0;border-bottom:1px solid var(--border);}}
.month-stat:last-child{{border-bottom:none;}}
.month-stat .ms-label{{font-size:13px;color:var(--text2);display:flex;align-items:center;gap:8px;}}
.month-stat .ms-val{{font-size:14px;font-weight:600;}}

/* ── SECTION HEADER ── */
.section-head{{display:flex;align-items:center;justify-content:space-between;margin:32px 0 16px;flex-wrap:wrap;gap:8px;}}
.section-head:first-child{{margin-top:0;}}
.section-title{{font-size:13px;font-weight:600;text-transform:uppercase;letter-spacing:.1em;color:var(--muted);}}
.section-title .accent{{color:var(--blue);}}

/* ── FILTER BAR ── */
.filter-bar{{display:flex;gap:4px;flex-wrap:wrap;}}
.filter-btn{{padding:5px 14px;border-radius:var(--radius-sm);font-size:12px;font-weight:500;color:var(--muted);cursor:pointer;border:1px solid var(--border);background:var(--s1);transition:.15s;}}
.filter-btn:hover{{color:var(--text2);border-color:var(--s3);}}
.filter-btn.active{{color:#fff;background:var(--blue);border-color:var(--blue);}}

/* ── CHART BOX ── */
.chart-box{{background:var(--s1);border:1px solid var(--border);border-radius:var(--radius);padding:20px;}}
.chart-header{{display:flex;align-items:center;justify-content:space-between;margin-bottom:14px;flex-wrap:wrap;gap:8px;}}
.chart-title{{font-size:15px;font-weight:600;}}
.chart-legend{{display:flex;gap:14px;font-size:11px;color:var(--muted);align-items:center;}}
.leg-dot{{width:8px;height:8px;border-radius:50%;display:inline-block;margin-right:4px;vertical-align:middle;}}
canvas{{display:block;width:100%;}}

/* ── TOGGLE ── */
.toggle-wrap{{display:flex;gap:2px;background:var(--s0);border-radius:var(--radius-sm);padding:2px;}}
.toggle-btn{{padding:4px 12px;border-radius:4px;font-size:11px;font-weight:500;color:var(--muted);cursor:pointer;border:none;background:none;transition:.15s;}}
.toggle-btn.on{{color:#fff;background:var(--blue);}}

/* ── TABLE ── */
.table-wrap{{overflow-x:auto;border-radius:var(--radius);border:1px solid var(--border);}}
table{{width:100%;border-collapse:collapse;font-size:13px;}}
thead{{background:var(--s2);}}
th{{padding:10px 14px;text-align:left;font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);cursor:pointer;white-space:nowrap;user-select:none;}}
th:hover{{color:var(--text2);}}
td{{padding:10px 14px;border-top:1px solid var(--border);white-space:nowrap;}}
tr:hover td{{background:var(--s2);}}
.sort-arrow{{margin-left:4px;opacity:.4;}}
th.sorted .sort-arrow{{opacity:1;color:var(--blue);}}

/* ── BADGE ── */
.badge{{display:inline-block;padding:2px 8px;border-radius:99px;font-size:10px;font-weight:600;letter-spacing:.03em;}}
.badge-push{{background:rgba(79,142,247,.15);color:var(--blue);}}
.badge-pull{{background:rgba(52,199,123,.15);color:var(--green);}}
.badge-legs{{background:rgba(167,139,250,.15);color:var(--purple);}}
.badge-mixed{{background:rgba(247,201,72,.15);color:var(--yellow);}}
.badge-other{{background:rgba(107,113,148,.15);color:var(--muted);}}

/* ── PR TAG ── */
.pr-tag{{display:inline-block;background:rgba(247,201,72,.15);color:var(--yellow);font-size:10px;font-weight:700;padding:1px 6px;border-radius:3px;margin-left:6px;}}

/* ── TOOLTIP ── */
#tooltip{{position:fixed;background:var(--s2);border:1px solid var(--s3);border-radius:8px;padding:10px 14px;font-size:13px;pointer-events:none;display:none;z-index:200;max-width:260px;box-shadow:0 8px 32px rgba(0,0,0,.5);}}
#tooltip .tt-val{{font-size:18px;font-weight:700;margin-bottom:2px;}}
#tooltip .tt-lbl{{color:var(--muted);font-size:11px;line-height:1.4;}}

/* ── PROGRESS BAR ── */
.progress{{height:6px;background:var(--s3);border-radius:99px;overflow:hidden;}}
.progress-fill{{height:100%;border-radius:99px;transition:width .6s ease;}}

/* ── STAT ROW ── */
.stat-row{{display:flex;justify-content:space-between;align-items:center;padding:10px 0;border-bottom:1px solid var(--border);}}
.stat-row:last-child{{border-bottom:none;}}
.stat-label{{font-size:13px;color:var(--muted);}}
.stat-value{{font-size:14px;font-weight:600;}}

/* ── EMPTY STATE ── */
.empty{{text-align:center;padding:48px 24px;color:var(--muted);}}

/* ── SPARKLINE ── */
.spark-wrap{{display:inline-block;vertical-align:middle;}}

/* ── RUN CARD ── */
.run-card{{display:grid;grid-template-columns:1fr auto;gap:8px;align-items:center;padding:14px 16px;background:var(--s1);border:1px solid var(--border);border-radius:var(--radius-sm);transition:.15s;cursor:pointer;}}
.run-card:hover{{border-color:var(--green);background:var(--s2);}}
.run-card .top{{display:flex;align-items:center;gap:10px;}}
.run-card .dist{{font-size:18px;font-weight:700;color:var(--green);}}
.run-card .meta{{font-size:12px;color:var(--muted);}}
.run-card .pace-badge{{font-size:13px;font-weight:600;padding:4px 10px;border-radius:var(--radius-sm);background:var(--s2);}}

/* ── PAGE HEADER ── */
.page-header{{margin-bottom:24px;}}
.page-header h1{{font-size:22px;font-weight:700;letter-spacing:-.02em;}}
.page-header p{{color:var(--muted);font-size:13px;margin-top:4px;}}

/* ── DONUT ── */
.donut-wrap{{position:relative;width:160px;height:160px;margin:0 auto;}}
.donut-center{{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);text-align:center;}}
.donut-center .val{{font-size:24px;font-weight:700;}}
.donut-center .lbl{{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.1em;}}

/* ── HEATMAP ── */
.heatmap{{display:grid;grid-template-columns:repeat(7,1fr);gap:3px;}}
.hm-cell{{aspect-ratio:1;border-radius:3px;position:relative;}}
.hm-cell.empty{{background:var(--s2);opacity:.3;}}
.hm-label{{font-size:9px;color:var(--muted);text-align:center;}}

/* ── RESPONSIVE ── */
@media(max-width:640px){{
  .nav-inner{{padding:0 12px;}}
  .page{{padding:16px 12px 60px;}}
  .kpi .value{{font-size:22px;}}
  .chart-header{{flex-direction:column;align-items:flex-start;}}
}}
</style>
</head>
<body>

<div id="tooltip"><div class="tt-val" id="tt-val"></div><div class="tt-lbl" id="tt-lbl"></div></div>

<nav class="nav">
  <div class="nav-inner">
    <div class="nav-brand">Sport<span>Hub</span></div>
    <div class="nav-tabs">
      <button class="nav-tab active" onclick="showPage('dashboard')">Dashboard</button>
      <button class="nav-tab" onclick="showPage('gym')">Gym</button>
      <button class="nav-tab" onclick="showPage('laufen')">Laufen</button>
      <button class="nav-tab" onclick="showPage('koerper')">Körper</button>
    </div>
  </div>
</nav>

<!-- ═══════════════ DASHBOARD ═══════════════ -->
<div class="page active" id="page-dashboard">
  <div class="page-header">
    <h1>Dashboard</h1>
    <p id="dash-subtitle">Gesamtübersicht</p>
  </div>
  <div class="grid grid-4" id="dash-kpis"></div>

  <div class="section-head">
    <span class="section-title">Wochenübersicht — Letzte 12 Wochen</span>
    <div class="chart-legend">
      <span><span class="leg-dot" style="background:var(--blue)"></span>Gym</span>
      <span><span class="leg-dot" style="background:var(--green)"></span>Laufen</span>
      <span style="color:var(--muted);font-size:11px">Ziel: 4/Woche</span>
    </div>
  </div>
  <div class="card card-lg">
    <canvas id="dash-weekly" height="180"></canvas>
  </div>

  <div class="grid grid-2" style="margin-top:16px">
    <div class="card card-lg">
      <div class="chart-header">
        <span class="chart-title">Letzte Einheiten</span>
        <span style="font-size:11px;color:var(--muted)" id="feed-range"></span>
      </div>
      <div id="dash-feed"></div>
    </div>
    <div class="card card-lg">
      <div class="chart-header">
        <span class="chart-title" id="month-title">Diesen Monat</span>
      </div>
      <div id="dash-month-stats"></div>
    </div>
  </div>

  <div class="grid grid-2" style="margin-top:16px">
    <div class="card card-lg">
      <div class="chart-header">
        <span class="chart-title">Bankdrücken — Est. 1RM Trend</span>
      </div>
      <canvas id="dash-bench-trend" height="150"></canvas>
    </div>
    <div class="card card-lg">
      <div class="chart-header">
        <span class="chart-title">Laufen — Pace-Trend</span>
      </div>
      <canvas id="dash-pace-trend" height="150"></canvas>
    </div>
  </div>
</div>

<!-- ═══════════════ GYM ═══════════════ -->
<div class="page" id="page-gym">
  <div class="page-header">
    <h1>Gym</h1>
    <p id="gym-subtitle"></p>
  </div>
  <div class="grid grid-4" id="gym-kpis"></div>

  <div class="section-head">
    <span class="section-title">Bankdrücken — Progression</span>
    <div class="toggle-wrap">
      <button class="toggle-btn on" onclick="setGymMode('kg')">Gewicht</button>
      <button class="toggle-btn" onclick="setGymMode('vol')">Volumen</button>
      <button class="toggle-btn" onclick="setGymMode('e1rm')">Est. 1RM</button>
    </div>
  </div>
  <div class="chart-box"><canvas id="bench-chart" height="280"></canvas></div>

  <div class="section-head">
    <span class="section-title">Session-Volumen</span>
    <div class="filter-bar" id="gym-filter"></div>
  </div>
  <div class="chart-box"><canvas id="volume-chart" height="220"></canvas></div>

  <div class="grid grid-2" style="margin-top:16px">
    <div class="card card-lg">
      <div class="chart-header"><span class="chart-title">Split-Verteilung</span></div>
      <div style="display:flex;align-items:center;gap:24px;">
        <div class="donut-wrap"><canvas id="split-donut" width="160" height="160"></canvas>
          <div class="donut-center"><div class="val" id="split-total"></div><div class="lbl">Sessions</div></div>
        </div>
        <div id="split-legend" style="font-size:13px;"></div>
      </div>
    </div>
    <div class="card card-lg">
      <div class="chart-header"><span class="chart-title">Monatliche Frequenz</span></div>
      <canvas id="gym-freq" height="180"></canvas>
    </div>
  </div>

  <div class="section-head"><span class="section-title">Session-Verlauf</span></div>
  <div class="table-wrap">
    <table id="gym-table">
      <thead>
        <tr>
          <th onclick="sortGymTable('d')">Datum <span class="sort-arrow">▼</span></th>
          <th onclick="sortGymTable('t')">Typ <span class="sort-arrow">▼</span></th>
          <th onclick="sortGymTable('vol')">Volumen <span class="sort-arrow">▼</span></th>
          <th onclick="sortGymTable('n')">Übungen <span class="sort-arrow">▼</span></th>
          <th onclick="sortGymTable('bench')">Bench <span class="sort-arrow">▼</span></th>
          <th>Details</th>
        </tr>
      </thead>
      <tbody id="gym-tbody"></tbody>
    </table>
  </div>
</div>

<!-- ═══════════════ LAUFEN ═══════════════ -->
<div class="page" id="page-laufen">
  <div class="page-header">
    <h1>Laufen</h1>
    <p id="run-subtitle"></p>
  </div>
  <div class="grid grid-4" id="run-kpis"></div>

  <div class="section-head">
    <span class="section-title">Pace-Trend</span>
    <div class="toggle-wrap">
      <button class="toggle-btn on" onclick="setRunMode('pace')">Pace</button>
      <button class="toggle-btn" onclick="setRunMode('dist')">Distanz</button>
      <button class="toggle-btn" onclick="setRunMode('time')">Zeit</button>
    </div>
  </div>
  <div class="chart-box"><canvas id="pace-chart" height="300"></canvas></div>

  <div class="grid grid-2" style="margin-top:16px">
    <div class="card card-lg">
      <div class="chart-header"><span class="chart-title">Pace vs. Distanz</span></div>
      <canvas id="pace-dist-scatter" height="220"></canvas>
    </div>
    <div class="card card-lg">
      <div class="chart-header"><span class="chart-title">Monatliches Volumen</span></div>
      <canvas id="run-monthly" height="220"></canvas>
    </div>
  </div>

  <div class="grid grid-2" style="margin-top:16px">
    <div class="card card-lg">
      <div class="chart-header"><span class="chart-title">Pace-Verteilung</span></div>
      <canvas id="pace-histogram" height="180"></canvas>
    </div>
    <div class="card card-lg">
      <div class="chart-header"><span class="chart-title">Personal Records</span></div>
      <div id="run-prs"></div>
    </div>
  </div>

  <div class="section-head"><span class="section-title">Alle Läufe</span></div>
  <div class="table-wrap">
    <table id="run-table">
      <thead>
        <tr>
          <th onclick="sortRunTable('d')">Datum <span class="sort-arrow">▼</span></th>
          <th onclick="sortRunTable('km')">Distanz <span class="sort-arrow">▼</span></th>
          <th onclick="sortRunTable('pace')">Pace <span class="sort-arrow">▼</span></th>
          <th onclick="sortRunTable('sec')">Zeit <span class="sort-arrow">▼</span></th>
          <th onclick="sortRunTable('hr')">HR <span class="sort-arrow">▼</span></th>
          <th onclick="sortRunTable('cal')">kcal <span class="sort-arrow">▼</span></th>
          <th onclick="sortRunTable('elev')">Höhe <span class="sort-arrow">▼</span></th>
        </tr>
      </thead>
      <tbody id="run-tbody"></tbody>
    </table>
  </div>
</div>

<!-- ═══════════════ KÖRPER ═══════════════ -->
<div class="page" id="page-koerper">
  <div class="page-header">
    <h1>Körper</h1>
    <p>Gewicht & Ziele</p>
  </div>
  <div class="grid grid-4" id="body-kpis"></div>
  <div class="section-head"><span class="section-title">Gewichtsverlauf</span></div>
  <div class="chart-box"><canvas id="weight-chart" height="280"></canvas></div>
  <div class="section-head"><span class="section-title">Ziele</span></div>
  <div class="grid grid-3" id="goals-grid"></div>
</div>

<script>
// ═══════════════════════════════════════════════════════════════
// DATA
// ═══════════════════════════════════════════════════════════════
const RUNS = {runs_json};
const GYM = {gym_json};
const WEIGHT = {weight_json};

// ═══════════════════════════════════════════════════════════════
// UTILS
// ═══════════════════════════════════════════════════════════════
const $ = id => document.getElementById(id);
const dpr = window.devicePixelRatio || 1;
const today = new Date();

// roundRect polyfill
if(!CanvasRenderingContext2D.prototype.roundRect) {{
  CanvasRenderingContext2D.prototype.roundRect = function(x,y,w,h,r) {{
    if(!Array.isArray(r)) r=[r||0];
    const tl=r[0]||0,tr=r[1]||tl,br=r[2]||tl,bl=r[3]||tr;
    this.moveTo(x+tl,y);
    this.lineTo(x+w-tr,y); this.quadraticCurveTo(x+w,y,x+w,y+tr);
    this.lineTo(x+w,y+h-br); this.quadraticCurveTo(x+w,y+h,x+w-br,y+h);
    this.lineTo(x+bl,y+h); this.quadraticCurveTo(x,y+h,x,y+h-bl);
    this.lineTo(x,y+tl); this.quadraticCurveTo(x,y,x+tl,y);
    this.closePath();
  }};
}}

function fmtDate(iso) {{
  const [y,m,d] = iso.split('-');
  return d+'.'+m+'.'+y;
}}
function fmtPace(p) {{
  if(!p||p<=0) return '-';
  const m=Math.floor(p);
  const s=Math.round((p-m)*60);
  return m+':'+(s<10?'0':'')+s;
}}
function fmtTime(sec) {{
  if(!sec) return '-';
  const h=Math.floor(sec/3600);
  const m=Math.floor((sec%3600)/60);
  const s=sec%60;
  if(h>0) return h+'h '+m+'m';
  return m+':'+((s<10)?'0':'')+s;
}}
function fmtNum(n) {{
  return n.toLocaleString('de-DE');
}}
function lerp(a,b,t){{ return a+(b-a)*t; }}

// E1RM using Epley formula
function e1rm(w,r) {{
  if(r<=0||w<=0) return 0;
  if(r===1) return w;
  return Math.round(w*(1+r/30));
}}

// Linear regression
function linReg(pts) {{
  const n=pts.length;
  if(n<2) return {{slope:0,intercept:pts[0]?.y||0}};
  let sx=0,sy=0,sxx=0,sxy=0;
  pts.forEach((p,i)=>{{sx+=i;sy+=p.y;sxx+=i*i;sxy+=i*p.y}});
  const slope=(n*sxy-sx*sy)/(n*sxx-sx*sx);
  const intercept=(sy-slope*sx)/n;
  return {{slope,intercept}};
}}

// ═══════════════════════════════════════════════════════════════
// NAVIGATION
// ═══════════════════════════════════════════════════════════════
let currentPage = 'dashboard';

function showPage(id) {{
  currentPage = id;
  document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));
  document.querySelectorAll('.nav-tab').forEach(t=>t.classList.remove('active'));
  $('page-'+id).classList.add('active');
  document.querySelectorAll('.nav-tab').forEach(t=>{{
    if(t.textContent.toLowerCase().replace('ö','oe').includes(id.replace('koerper','koerper').replace('oe','')))
      t.classList.add('active');
  }});
  // Simpler: find by index
  const tabs = document.querySelectorAll('.nav-tab');
  tabs.forEach(t=>t.classList.remove('active'));
  const map = {{'dashboard':0,'gym':1,'laufen':2,'koerper':3}};
  if(tabs[map[id]]) tabs[map[id]].classList.add('active');

  // Trigger chart draws
  requestAnimationFrame(()=>{{
    if(id==='dashboard') drawDashboard();
    if(id==='gym') drawGym();
    if(id==='laufen') drawLaufen();
    if(id==='koerper') drawKoerper();
  }});
}}

// ═══════════════════════════════════════════════════════════════
// CANVAS UTILS
// ═══════════════════════════════════════════════════════════════
function initCanvas(canvas, h) {{
  const w = canvas.offsetWidth || canvas.parentElement.offsetWidth || 600;
  canvas.width = w * dpr;
  canvas.height = (h||280) * dpr;
  canvas.style.width = w + 'px';
  canvas.style.height = (h||280) + 'px';
  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);
  return {{ctx, W:w, H:h||280}};
}}

function drawGrid(ctx, W, H, pad, yMin, yMax, steps, fmt) {{
  ctx.strokeStyle = '#1c2030';
  ctx.lineWidth = 1;
  ctx.fillStyle = '#6b7194';
  ctx.font = '10px -apple-system,sans-serif';
  ctx.textAlign = 'right';
  for(let i=0;i<=steps;i++) {{
    const y = pad.t + (i/steps)*(H-pad.t-pad.b);
    ctx.beginPath(); ctx.moveTo(pad.l,y); ctx.lineTo(W-pad.r,y); ctx.stroke();
    const val = yMax - (i/steps)*(yMax-yMin);
    ctx.fillText(fmt ? fmt(val) : Math.round(val).toString(), pad.l-6, y+4);
  }}
}}

function showTooltip(e, val, lbl) {{
  const tt = $('tooltip');
  $('tt-val').innerHTML = val;
  $('tt-lbl').innerHTML = lbl;
  tt.style.display = 'block';
  tt.style.left = Math.min(e.clientX+14, window.innerWidth-270) + 'px';
  tt.style.top = (e.clientY-40) + 'px';
}}
function hideTooltip() {{ $('tooltip').style.display='none'; }}

function setupHover(canvas, points, valueFn, labelFn) {{
  canvas._hoverPts = points;
  canvas.onmousemove = (e) => {{
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    let closest = null, minDist = 25;
    (canvas._hoverPts||[]).forEach(p => {{
      const d = Math.sqrt((p.x-mx)**2+(p.y-my)**2);
      if(d<minDist) {{ minDist=d; closest=p; }}
    }});
    if(closest) showTooltip(e, valueFn(closest), labelFn(closest));
    else hideTooltip();
  }};
  canvas.onmouseleave = hideTooltip;
}}

// Badge for session type
function typeBadge(t) {{
  const cls = t.includes('Push')&&t.includes('Pull')?'mixed':
    t.includes('Push')?'push':t.includes('Pull')?'pull':
    t.includes('Bein')?'legs':'other';
  return '<span class="badge badge-'+cls+'">'+t+'</span>';
}}

// ═══════════════════════════════════════════════════════════════
// DASHBOARD
// ═══════════════════════════════════════════════════════════════
function drawDashboard() {{
  // ── Compute key metrics ──
  const currentWeight = WEIGHT.length ? WEIGHT[WEIGHT.length-1].kg : 99;
  const lastBench = [...GYM].reverse().find(s=>s.bench);
  const benchKg = lastBench ? lastBench.bench[0] : 0;
  const benchReps = lastBench ? lastBench.bench[1] : 0;
  const benchE1rm = e1rm(benchKg, benchReps);
  const prevBench = [...GYM].reverse().filter(s=>s.bench);
  const benchTrend = prevBench.length>=2 ? prevBench[0].bench[0]-prevBench[1].bench[0] : 0;

  // Streak: consecutive weeks with >=1 session
  const streak = calcStreak();
  const thisWeek = getThisWeekSessions();
  const weekTarget = 4;

  // ── KPIs ──
  $('dash-kpis').innerHTML = [
    `<div class="card kpi">
      <div class="value" style="color:var(--green)">${{thisWeek}}/${{weekTarget}}</div>
      <div class="label">Diese Woche</div>
      <div class="mini-bar"><div class="mini-bar-fill" style="width:${{Math.min(100,thisWeek/weekTarget*100)}}%;background:${{thisWeek>=weekTarget?'var(--green)':'var(--yellow)'}}"></div></div>
    </div>`,
    `<div class="card kpi">
      <div class="value" style="color:var(--yellow)">${{streak}}</div>
      <div class="label">Wochen-Streak</div>
      <div class="sub">am Stück aktiv</div>
    </div>`,
    `<div class="card kpi">
      <div class="value" style="color:var(--blue)">${{benchKg}}kg</div>
      <div class="label">Bankdrücken</div>
      <div class="trend ${{benchTrend>=0?'up':'down'}}">${{benchTrend>0?'+':''}}${{benchTrend}}kg · 1RM ~${{benchE1rm}}kg</div>
    </div>`,
    `<div class="card kpi">
      <div class="value" style="color:var(--purple)">${{currentWeight}}kg</div>
      <div class="label">Gewicht</div>
      <div class="mini-bar"><div class="mini-bar-fill" style="width:${{Math.max(0,Math.min(100,(1-(currentWeight-90)/(99-90))*100))}}%;background:var(--purple)"></div></div>
      <div class="sub">Ziel: &lt;90kg</div>
    </div>`,
  ].join('');

  $('dash-subtitle').textContent = GYM.length+' Gym · '+RUNS.length+' Läufe · '+Math.round(RUNS.reduce((a,r)=>a+r.km,0))+' km gesamt';

  drawWeeklyChart();
  drawDashFeed();
  drawMonthStats();
  drawDashBenchTrend();
  drawDashPaceTrend();
}}

function calcStreak() {{
  // Weeks in a row with >=1 session, counting back from current week
  const allDates = [...GYM.map(s=>s.d), ...RUNS.map(r=>r.d)].sort().reverse();
  if(!allDates.length) return 0;
  const getWeekKey = (iso) => {{
    const d = new Date(iso);
    const mon = new Date(d); mon.setDate(d.getDate()-((d.getDay()+6)%7));
    return mon.toISOString().slice(0,10);
  }};
  const weeks = new Set(allDates.map(getWeekKey));
  let streak = 0;
  let check = new Date();
  check.setDate(check.getDate()-((check.getDay()+6)%7)); // this monday
  check.setHours(0,0,0,0);
  for(let i=0; i<52; i++) {{
    const key = check.toISOString().slice(0,10);
    if(weeks.has(key)) streak++;
    else break;
    check.setDate(check.getDate()-7);
  }}
  return streak;
}}

function getThisWeekSessions() {{
  const now = new Date();
  const monday = new Date(now);
  monday.setDate(now.getDate() - ((now.getDay()+6)%7));
  monday.setHours(0,0,0,0);
  const mStr = monday.toISOString().slice(0,10);
  return GYM.filter(s=>s.d>=mStr).length + RUNS.filter(r=>r.d>=mStr).length;
}}

function kpiCard(value, label, sub, colorVar) {{
  return `<div class="card kpi"><div class="value" style="color:var(${{colorVar}})">${{value}}</div><div class="label">${{label}}</div><div class="sub">${{sub}}</div></div>`;
}}

// ── WEEKLY BAR CHART ──
function drawWeeklyChart() {{
  const canvas = $('dash-weekly');
  const {{ctx,W,H}} = initCanvas(canvas, 180);
  const pad = {{l:36, r:12, t:24, b:36}};
  const cW = W-pad.l-pad.r;
  const cH = H-pad.t-pad.b;
  const nWeeks = 12;
  const target = 4;

  // Build weekly data
  const weeks = [];
  const now = new Date();
  const curMon = new Date(now);
  curMon.setDate(now.getDate()-((now.getDay()+6)%7));
  curMon.setHours(0,0,0,0);

  for(let i=nWeeks-1; i>=0; i--) {{
    const mon = new Date(curMon);
    mon.setDate(curMon.getDate()-i*7);
    const sun = new Date(mon); sun.setDate(mon.getDate()+6);
    const mStr = mon.toISOString().slice(0,10);
    const sStr = sun.toISOString().slice(0,10);
    const gym = GYM.filter(s=>s.d>=mStr && s.d<=sStr).length;
    const run = RUNS.filter(r=>r.d>=mStr && r.d<=sStr).length;
    // KW number
    const jan1 = new Date(mon.getFullYear(),0,1);
    const kw = Math.ceil(((mon-jan1)/86400000+jan1.getDay()+1)/7);
    weeks.push({{kw, gym, run, total:gym+run, isCurrent:i===0, mStr, sStr}});
  }}

  const maxTotal = Math.max(target+1, ...weeks.map(w=>w.total));
  const barW = Math.max(16, Math.min(48, cW/nWeeks-8));

  // Target line
  const targetY = pad.t + cH - (target/maxTotal)*cH;
  ctx.strokeStyle = 'rgba(247,201,72,.35)';
  ctx.lineWidth = 1;
  ctx.setLineDash([4,3]);
  ctx.beginPath(); ctx.moveTo(pad.l, targetY); ctx.lineTo(W-pad.r, targetY); ctx.stroke();
  ctx.setLineDash([]);
  ctx.fillStyle = 'rgba(247,201,72,.6)';
  ctx.font = '10px -apple-system,sans-serif';
  ctx.textAlign = 'right';
  ctx.fillText('Ziel '+target+'x', pad.l-4, targetY+4);

  const pts = [];
  weeks.forEach((w,i) => {{
    const x = pad.l + (i+0.5)/nWeeks * cW;
    const gymH = (w.gym/maxTotal)*cH;
    const runH = (w.run/maxTotal)*cH;
    const totalH = gymH+runH;
    const baseY = pad.t + cH;

    // Highlight current week bg
    if(w.isCurrent) {{
      ctx.fillStyle = 'rgba(79,142,247,.06)';
      ctx.beginPath();
      ctx.roundRect(x-barW/2-4, pad.t-4, barW+8, cH+12, 6);
      ctx.fill();
    }}

    // Gym bar (bottom)
    if(w.gym>0) {{
      ctx.fillStyle = w.isCurrent ? '#4f8ef7' : 'rgba(79,142,247,.7)';
      ctx.beginPath();
      ctx.roundRect(x-barW/2, baseY-gymH, barW, gymH, w.run>0?[0,0,3,3]:[3,3,3,3]);
      ctx.fill();
    }}
    // Run bar (stacked on top)
    if(w.run>0) {{
      ctx.fillStyle = w.isCurrent ? '#34c77b' : 'rgba(52,199,123,.7)';
      ctx.beginPath();
      ctx.roundRect(x-barW/2, baseY-totalH, barW, runH, w.gym>0?[3,3,0,0]:[3,3,3,3]);
      ctx.fill();
    }}
    // Zero state
    if(w.total===0) {{
      ctx.fillStyle = 'rgba(224,92,110,.25)';
      ctx.beginPath();
      ctx.roundRect(x-barW/2, baseY-3, barW, 3, 2);
      ctx.fill();
    }}

    // Count on top
    if(w.total>0) {{
      ctx.fillStyle = w.total>=target ? '#34c77b' : w.total>=2 ? '#c0c4d4' : '#e05c6e';
      ctx.font = '11px -apple-system,sans-serif';
      ctx.fontWeight = '600';
      ctx.textAlign = 'center';
      ctx.fillText(w.total, x, baseY-totalH-6);
    }}

    // KW label
    ctx.fillStyle = w.isCurrent ? '#e8eaf0' : '#6b7194';
    ctx.font = (w.isCurrent?'bold ':'')+' 10px -apple-system,sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('KW'+w.kw, x, H-pad.b+14);
    // Month tick on first week of month
    if(i===0 || weeks[i-1]?.mStr?.slice(5,7)!==w.mStr.slice(5,7)) {{
      const mNames = ['','Jan','Feb','Mär','Apr','Mai','Jun','Jul','Aug','Sep','Okt','Nov','Dez'];
      ctx.fillStyle = '#6b7194';
      ctx.font = '9px -apple-system,sans-serif';
      ctx.fillText(mNames[parseInt(w.mStr.slice(5,7))], x, H-pad.b+26);
    }}

    pts.push({{x, y:baseY-totalH, data:w}});
  }});

  setupHover(canvas, pts,
    p => p.data.total + ' Einheiten',
    p => 'KW'+p.data.kw + (p.data.isCurrent?' (aktuell)':'') + ' · '+p.data.gym+' Gym + '+p.data.run+' Lauf'
  );
}}

// ── RECENT SESSIONS FEED ──
function drawDashFeed() {{
  const all = [
    ...GYM.map(s=>({{d:s.d, type:'gym', label:s.t, val:s.bench?s.bench[0]+'kg ×'+s.bench[1]:fmtNum(s.vol)+'kg vol', color:'var(--blue)', icon:'G', details:s.ex.map(e=>e.name).join(', ')}})),
    ...RUNS.map(r=>({{d:r.d, type:'run', label:'Lauf', val:r.km+'km', color:'var(--green)', icon:'L', details:fmtPace(r.pace)+'/km · '+fmtTime(r.sec)}}))
  ].sort((a,b)=>b.d.localeCompare(a.d)).slice(0,6);

  if(all.length) {{
    $('feed-range').textContent = fmtDate(all[all.length-1].d)+' – '+fmtDate(all[0].d);
  }}

  $('dash-feed').innerHTML = all.map(s => `
    <div class="feed-item" onclick="showPage('${{s.type==='gym'?'gym':'laufen'}}')">
      <div class="feed-dot" style="background:${{s.type==='gym'?'rgba(79,142,247,.15)':'rgba(52,199,123,.15)'}};color:${{s.color}};font-weight:700;font-size:12px;">${{s.icon}}</div>
      <div class="feed-body">
        <div class="feed-title">${{s.label}} <span style="font-weight:400;color:var(--muted);font-size:12px">${{fmtDate(s.d)}}</span></div>
        <div class="feed-meta">${{s.details.substring(0,50)}}</div>
      </div>
      <div class="feed-value" style="color:${{s.color}}">${{s.val}}</div>
    </div>
  `).join('');
}}

// ── MONTH SUMMARY ──
function drawMonthStats() {{
  const mNames = ['Januar','Februar','März','April','Mai','Juni','Juli','August','September','Oktober','November','Dezember'];
  const now = new Date();
  const mStr = now.toISOString().slice(0,7); // YYYY-MM
  $('month-title').textContent = mNames[now.getMonth()] + ' ' + now.getFullYear();

  const gymThisMonth = GYM.filter(s=>s.d.startsWith(mStr));
  const runsThisMonth = RUNS.filter(r=>r.d.startsWith(mStr));
  const kmThisMonth = runsThisMonth.reduce((a,r)=>a+r.km,0);
  const volThisMonth = gymThisMonth.reduce((a,s)=>a+s.vol,0);
  const benchSessions = gymThisMonth.filter(s=>s.bench);
  const bestBenchMonth = benchSessions.length ? Math.max(...benchSessions.map(s=>s.bench[0])) : null;
  const bestPaceMonth = runsThisMonth.filter(r=>r.pace>0).length
    ? Math.min(...runsThisMonth.filter(r=>r.pace>0).map(r=>r.pace)) : null;

  const stats = [
    {{icon:'rgba(79,142,247,.15)', ic:'var(--blue)', label:'Gym-Sessions', val:gymThisMonth.length}},
    {{icon:'rgba(52,199,123,.15)', ic:'var(--green)', label:'Läufe', val:runsThisMonth.length}},
    {{icon:'rgba(52,199,123,.15)', ic:'var(--green)', label:'Kilometer', val:kmThisMonth.toFixed(1)+' km'}},
    {{icon:'rgba(79,142,247,.15)', ic:'var(--blue)', label:'Gym-Volumen', val:fmtNum(volThisMonth)+' kg'}},
  ];
  if(bestBenchMonth) stats.push({{icon:'rgba(247,201,72,.15)',ic:'var(--yellow)',label:'Bestes Bench',val:bestBenchMonth+'kg'}});
  if(bestPaceMonth) stats.push({{icon:'rgba(167,139,250,.15)',ic:'var(--purple)',label:'Beste Pace',val:fmtPace(bestPaceMonth)+'/km'}});

  $('dash-month-stats').innerHTML = stats.map(s=>`
    <div class="month-stat">
      <div class="ms-label"><span style="width:8px;height:8px;border-radius:50%;background:${{s.ic}};display:inline-block;"></span>${{s.label}}</div>
      <div class="ms-val">${{s.val}}</div>
    </div>
  `).join('');
}}

// ── BENCH EST. 1RM TREND (Dashboard) ──
function drawDashBenchTrend() {{
  const canvas = $('dash-bench-trend');
  const {{ctx,W,H}} = initCanvas(canvas, 150);
  const pad = {{l:44,r:12,t:12,b:24}};
  const cW=W-pad.l-pad.r, cH=H-pad.t-pad.b;

  const benchData = GYM.filter(s=>s.bench).map(s=>({{d:s.d, e:e1rm(s.bench[0],s.bench[1])}}));
  const recent = benchData.slice(-15); // last 15
  if(recent.length<2) return;

  const vals = recent.map(d=>d.e);
  const yMin = Math.min(...vals)*0.92;
  const yMax = Math.max(...vals)*1.06;
  const sy = v => pad.t+cH-((v-yMin)/(yMax-yMin))*cH;
  const sx = i => pad.l+(i/(recent.length-1))*cW;

  // Grid
  drawGrid(ctx,W,H,pad,yMin,yMax,3,v=>Math.round(v)+'kg');

  // Area fill
  ctx.fillStyle = 'rgba(79,142,247,.08)';
  ctx.beginPath();
  ctx.moveTo(sx(0), sy(vals[0]));
  recent.forEach((_,i)=>ctx.lineTo(sx(i), sy(vals[i])));
  ctx.lineTo(sx(recent.length-1), pad.t+cH);
  ctx.lineTo(sx(0), pad.t+cH);
  ctx.closePath(); ctx.fill();

  // Line
  ctx.strokeStyle = '#4f8ef7'; ctx.lineWidth=2; ctx.lineJoin='round';
  ctx.beginPath();
  recent.forEach((d,i)=>i===0?ctx.moveTo(sx(i),sy(d.e)):ctx.lineTo(sx(i),sy(d.e)));
  ctx.stroke();

  // Dots
  const pts = [];
  recent.forEach((d,i) => {{
    ctx.fillStyle='#4f8ef7'; ctx.beginPath(); ctx.arc(sx(i),sy(d.e),3,0,Math.PI*2); ctx.fill();
    pts.push({{x:sx(i),y:sy(d.e),data:d}});
  }});

  // X labels
  ctx.fillStyle='#6b7194'; ctx.font='9px -apple-system,sans-serif'; ctx.textAlign='center';
  [0, recent.length-1].forEach(i=>ctx.fillText(fmtDate(recent[i].d).slice(0,5), sx(i), H-4));

  // Current value label
  const last = recent[recent.length-1];
  ctx.fillStyle='#4f8ef7'; ctx.font='bold 12px -apple-system,sans-serif'; ctx.textAlign='right';
  ctx.fillText(last.e+'kg', W-pad.r, pad.t+10);

  setupHover(canvas, pts,
    p=>'Est. 1RM: '+p.data.e+'kg',
    p=>fmtDate(p.data.d)
  );
}}

// ── PACE TREND (Dashboard) ──
function drawDashPaceTrend() {{
  const canvas = $('dash-pace-trend');
  const {{ctx,W,H}} = initCanvas(canvas, 150);
  const pad = {{l:44,r:12,t:12,b:24}};
  const cW=W-pad.l-pad.r, cH=H-pad.t-pad.b;

  const recent = RUNS.filter(r=>r.pace>0&&r.pace<15).slice(-20);
  if(recent.length<2) return;

  const vals = recent.map(r=>r.pace);
  const yMin = Math.min(...vals)*0.95;
  const yMax = Math.max(...vals)*1.03;
  // Inverted: lower pace (faster) = higher on chart
  const sy = v => pad.t + ((v-yMin)/(yMax-yMin))*cH;
  const sx = i => pad.l+(i/(recent.length-1))*cW;

  // Grid (inverted labels)
  ctx.strokeStyle='#1c2030'; ctx.lineWidth=1;
  ctx.fillStyle='#6b7194'; ctx.font='10px -apple-system,sans-serif'; ctx.textAlign='right';
  for(let i=0;i<=3;i++) {{
    const y=pad.t+(i/3)*cH;
    ctx.beginPath(); ctx.moveTo(pad.l,y); ctx.lineTo(W-pad.r,y); ctx.stroke();
    const v=yMin+(i/3)*(yMax-yMin);
    ctx.fillText(fmtPace(v), pad.l-6, y+4);
  }}

  // Area fill
  ctx.fillStyle='rgba(52,199,123,.08)';
  ctx.beginPath();
  ctx.moveTo(sx(0), sy(vals[0]));
  recent.forEach((_,i)=>ctx.lineTo(sx(i), sy(vals[i])));
  ctx.lineTo(sx(recent.length-1), pad.t);
  ctx.lineTo(sx(0), pad.t);
  ctx.closePath(); ctx.fill();

  // Trend line
  const regPts = vals.map((v,i)=>({{x:i,y:v}}));
  const reg = linReg(regPts);
  ctx.strokeStyle='rgba(167,139,250,.5)'; ctx.lineWidth=1.5; ctx.setLineDash([4,3]);
  ctx.beginPath(); ctx.moveTo(sx(0),sy(reg.intercept)); ctx.lineTo(sx(recent.length-1),sy(reg.intercept+reg.slope*(recent.length-1))); ctx.stroke();
  ctx.setLineDash([]);

  // Line
  ctx.strokeStyle='#34c77b'; ctx.lineWidth=2; ctx.lineJoin='round';
  ctx.beginPath();
  recent.forEach((r,i)=>i===0?ctx.moveTo(sx(i),sy(r.pace)):ctx.lineTo(sx(i),sy(r.pace)));
  ctx.stroke();

  // Dots
  const pts = [];
  recent.forEach((r,i) => {{
    const c = r.km<5?'#4f8ef7':r.km<10?'#34c77b':'#f7c948';
    ctx.fillStyle=c; ctx.beginPath(); ctx.arc(sx(i),sy(r.pace),3,0,Math.PI*2); ctx.fill();
    pts.push({{x:sx(i),y:sy(r.pace),data:r}});
  }});

  // X labels
  ctx.fillStyle='#6b7194'; ctx.font='9px -apple-system,sans-serif'; ctx.textAlign='center';
  [0, recent.length-1].forEach(i=>ctx.fillText(fmtDate(recent[i].d).slice(0,5), sx(i), H-4));

  // Current avg pace
  const avgP = vals.reduce((a,b)=>a+b,0)/vals.length;
  ctx.fillStyle='#34c77b'; ctx.font='bold 12px -apple-system,sans-serif'; ctx.textAlign='right';
  ctx.fillText('Ø '+fmtPace(avgP)+'/km', W-pad.r, pad.t+10);

  setupHover(canvas, pts,
    p=>fmtPace(p.data.pace)+'/km',
    p=>fmtDate(p.data.d)+' · '+p.data.km+'km · '+fmtTime(p.data.sec)
  );
}}

// ═══════════════════════════════════════════════════════════════
// GYM
// ═══════════════════════════════════════════════════════════════
let gymMode = 'kg';
let gymFilter = 'all';
let gymSortCol = 'd';
let gymSortAsc = false;

function setGymMode(m) {{
  gymMode = m;
  document.querySelectorAll('#page-gym .toggle-btn').forEach(b=>b.classList.remove('on'));
  document.querySelector(`#page-gym .toggle-btn[onclick="setGymMode('${{m}}')"]`).classList.add('on');
  drawBenchChart();
}}

function setGymFilter(f) {{
  gymFilter = f;
  document.querySelectorAll('#gym-filter .filter-btn').forEach(b=>b.classList.toggle('active', b.dataset.f===f));
  drawVolumeChart();
}}

function drawGym() {{
  const totalVol = GYM.reduce((a,s)=>a+s.vol, 0);
  const avgVol = GYM.length ? Math.round(totalVol/GYM.length) : 0;
  const lastBench = [...GYM].reverse().find(s=>s.bench);
  const peakBench = GYM.reduce((mx,s)=>s.bench&&s.bench[0]>mx?s.bench[0]:mx, 0);

  $('gym-subtitle').textContent = GYM.length+' Sessions · '+fmtNum(totalVol)+' kg Gesamtvolumen';
  $('gym-kpis').innerHTML = [
    kpiCard(GYM.length, 'Sessions', GYM[0]?'seit '+fmtDate(GYM[0].d):'', '--blue'),
    kpiCard(fmtNum(avgVol)+'kg', 'Ø Volumen', 'pro Session', '--green'),
    kpiCard(lastBench?lastBench.bench[0]+'kg':'-', 'Bench aktuell', lastBench?'×'+lastBench.bench[1]+' Wdh':'', '--yellow'),
    kpiCard(peakBench+'kg', 'Bench Peak', 'All-time', '--red'),
  ].join('');

  // Build filter bar
  const types = [...new Set(GYM.map(s=>s.t))].sort();
  $('gym-filter').innerHTML = '<button class="filter-btn active" data-f="all" onclick="setGymFilter(\\x27all\\x27)">Alle</button>' +
    types.map(t=>'<button class="filter-btn" data-f="'+t+'" onclick="setGymFilter(\\x27'+t+'\\x27)">'+t+'</button>').join('');

  drawBenchChart();
  drawVolumeChart();
  drawSplitDonut();
  drawGymFreq();
  buildGymTable();
}}

function drawBenchChart() {{
  const canvas = $('bench-chart');
  const {{ctx,W,H}} = initCanvas(canvas, 280);
  const pad = {{l:54, r:20, t:20, b:36}};
  const cW = W-pad.l-pad.r;
  const cH = H-pad.t-pad.b;

  const benchData = GYM.filter(s=>s.bench).map(s=>({{
    d: s.d,
    kg: s.bench[0],
    reps: s.bench[1],
    vol: s.bench[0] * s.bench[1],
    est: e1rm(s.bench[0], s.bench[1])
  }}));

  if(!benchData.length) {{ ctx.fillStyle='#6b7194'; ctx.font='14px sans-serif'; ctx.fillText('Keine Bankdrücken-Daten', W/2-60, H/2); return; }}

  const vals = benchData.map(d => gymMode==='kg'?d.kg : gymMode==='vol'?d.vol : d.est);
  const preInjury = gymMode==='kg'?85 : gymMode==='vol'?85*8 : e1rm(85,8);
  const peak = gymMode==='kg'?90 : gymMode==='vol'?90*5 : e1rm(90,5);
  const allVals = [...vals, preInjury, peak];
  const yMin = Math.min(...allVals)*0.88;
  const yMax = Math.max(...allVals)*1.08;
  const unit = gymMode==='kg'?'kg' : gymMode==='vol'?'vol' : '1RM';

  drawGrid(ctx,W,H,pad,yMin,yMax,5, v => Math.round(v)+unit);

  // Reference lines
  const sy = v => pad.t + cH - ((v-yMin)/(yMax-yMin))*cH;
  const sx = i => pad.l + (i/(benchData.length-1||1))*cW;

  const drawRef = (val, color, label) => {{
    if(val<yMin||val>yMax) return;
    const y=sy(val);
    ctx.save(); ctx.strokeStyle=color; ctx.lineWidth=1; ctx.setLineDash([4,4]); ctx.globalAlpha=.5;
    ctx.beginPath(); ctx.moveTo(pad.l,y); ctx.lineTo(W-pad.r,y); ctx.stroke(); ctx.restore();
    ctx.fillStyle=color; ctx.font='10px -apple-system,sans-serif'; ctx.textAlign='left'; ctx.globalAlpha=.7;
    ctx.fillText(label+' '+Math.round(val)+unit, pad.l+4, y-5); ctx.globalAlpha=1;
  }};
  drawRef(peak, '#e05c6e', 'Peak');
  drawRef(preInjury, '#f7c948', 'Pre-Injury');

  // Line
  ctx.strokeStyle = '#4f8ef7';
  ctx.lineWidth = 2.5;
  ctx.lineJoin = 'round';
  ctx.beginPath();
  benchData.forEach((d,i) => {{
    const x=sx(i), y=sy(vals[i]);
    i===0 ? ctx.moveTo(x,y) : ctx.lineTo(x,y);
  }});
  ctx.stroke();

  // Area fill
  ctx.fillStyle = 'rgba(79,142,247,.08)';
  ctx.beginPath();
  ctx.moveTo(sx(0), sy(vals[0]));
  benchData.forEach((_,i) => ctx.lineTo(sx(i), sy(vals[i])));
  ctx.lineTo(sx(benchData.length-1), pad.t+cH);
  ctx.lineTo(sx(0), pad.t+cH);
  ctx.closePath();
  ctx.fill();

  // Dots
  const pts = [];
  benchData.forEach((d,i) => {{
    const x=sx(i), y=sy(vals[i]);
    ctx.fillStyle = '#4f8ef7';
    ctx.beginPath(); ctx.arc(x,y,4,0,Math.PI*2); ctx.fill();
    ctx.fillStyle = '#0e1018';
    ctx.beginPath(); ctx.arc(x,y,2,0,Math.PI*2); ctx.fill();
    pts.push({{x,y,data:d}});
  }});

  // X labels
  ctx.fillStyle = '#6b7194'; ctx.font='10px -apple-system,sans-serif'; ctx.textAlign='center';
  const step = Math.max(1, Math.floor(benchData.length/8));
  benchData.forEach((d,i) => {{
    if(i%step===0||i===benchData.length-1) ctx.fillText(fmtDate(d.d).slice(0,5), sx(i), H-pad.b+16);
  }});

  setupHover(canvas, pts,
    p => {{
      if(gymMode==='kg') return p.data.kg+'kg × '+p.data.reps+' Wdh';
      if(gymMode==='vol') return fmtNum(p.data.vol)+' vol';
      return p.data.est+' kg (est.)';
    }},
    p => fmtDate(p.data.d)+' · E1RM: '+p.data.est+'kg'
  );
}}

function drawVolumeChart() {{
  const canvas = $('volume-chart');
  const {{ctx,W,H}} = initCanvas(canvas, 220);
  const pad = {{l:54, r:16, t:16, b:28}};
  const filtered = gymFilter==='all' ? GYM : GYM.filter(s=>s.t===gymFilter);
  if(!filtered.length) return;

  const cW = W-pad.l-pad.r;
  const cH = H-pad.t-pad.b;
  const maxV = Math.max(...filtered.map(s=>s.vol))*1.1 || 1;

  drawGrid(ctx,W,H,pad,0,maxV,4,v=>Math.round(v/1000)+'k');

  const barW = Math.max(3, Math.min(14, cW/filtered.length-2));
  const pts = [];
  filtered.forEach((s,i) => {{
    const x = pad.l + (i/(filtered.length-1||1))*cW;
    const h = (s.vol/maxV)*cH;
    const y = pad.t+cH-h;
    const c = s.t.includes('Push')&&!s.t.includes('Pull')?'#4f8ef7':
      s.t.includes('Pull')&&!s.t.includes('Push')?'#34c77b':
      s.t.includes('Bein')?'#a78bfa':'#f7c948';
    ctx.fillStyle = c;
    ctx.globalAlpha = .8;
    ctx.beginPath(); ctx.roundRect(x-barW/2,y,barW,h,[3,3,0,0]); ctx.fill();
    ctx.globalAlpha = 1;
    pts.push({{x,y,data:s}});
  }});

  // Avg line
  const avg = filtered.reduce((a,s)=>a+s.vol,0)/filtered.length;
  const avgY = pad.t+cH-(avg/maxV)*cH;
  ctx.strokeStyle = '#f7c948'; ctx.lineWidth=1; ctx.setLineDash([4,3]); ctx.globalAlpha=.5;
  ctx.beginPath(); ctx.moveTo(pad.l,avgY); ctx.lineTo(W-pad.r,avgY); ctx.stroke();
  ctx.setLineDash([]); ctx.globalAlpha=1;
  ctx.fillStyle='#f7c948'; ctx.font='10px -apple-system,sans-serif'; ctx.textAlign='left';
  ctx.fillText('Ø '+fmtNum(Math.round(avg))+'kg', pad.l+4, avgY-5);

  // X labels
  ctx.fillStyle='#6b7194'; ctx.font='10px -apple-system,sans-serif'; ctx.textAlign='center';
  const step = Math.max(1,Math.floor(filtered.length/8));
  filtered.forEach((s,i) => {{
    if(i%step===0||i===filtered.length-1) ctx.fillText(fmtDate(s.d).slice(0,5), pad.l+(i/(filtered.length-1||1))*cW, H-6);
  }});

  setupHover(canvas, pts,
    p=>fmtNum(p.data.vol)+' kg',
    p=>fmtDate(p.data.d)+' · '+p.data.t+' · '+p.data.n+' Übungen'
  );
}}

function drawSplitDonut() {{
  const canvas = $('split-donut');
  const ctx = canvas.getContext('2d');
  canvas.width = 160*dpr; canvas.height=160*dpr;
  canvas.style.width='160px'; canvas.style.height='160px';
  ctx.scale(dpr,dpr);

  const typeCount = {{}};
  GYM.forEach(s=>{{ typeCount[s.t]=(typeCount[s.t]||0)+1; }});
  const total = GYM.length;
  $('split-total').textContent = total;

  const colors = {{'Push':'#4f8ef7','Pull':'#34c77b','Push+Pull':'#f7c948','Beine':'#a78bfa',
    'Push+Beine':'#22d3ee','Pull+Beine':'#e05c6e','Sonstiges':'#6b7194'}};
  const sorted = Object.entries(typeCount).sort((a,b)=>b[1]-a[1]);

  let angle = -Math.PI/2;
  sorted.forEach(([t,n])=>{{
    const sweep = (n/total)*Math.PI*2;
    ctx.fillStyle = colors[t]||'#6b7194';
    ctx.beginPath();
    ctx.moveTo(80,80);
    ctx.arc(80,80,72,angle,angle+sweep);
    ctx.closePath();
    ctx.fill();
    angle+=sweep;
  }});
  // Inner circle
  ctx.fillStyle = '#141722';
  ctx.beginPath(); ctx.arc(80,80,48,0,Math.PI*2); ctx.fill();

  // Legend
  $('split-legend').innerHTML = sorted.map(([t,n])=>
    `<div style="margin-bottom:6px;"><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${{colors[t]||'#6b7194'}};margin-right:8px;vertical-align:middle;"></span>${{t}} <span style="color:var(--muted)">${{n}} (${{Math.round(n/total*100)}}%)</span></div>`
  ).join('');
}}

function drawGymFreq() {{
  const canvas = $('gym-freq');
  const {{ctx,W,H}} = initCanvas(canvas, 180);
  const pad = {{l:40,r:16,t:16,b:32}};
  const byMonth = {{}};
  GYM.forEach(s=>{{ const m=s.d.slice(0,7); byMonth[m]=(byMonth[m]||0)+1; }});
  const months = Object.keys(byMonth).sort();
  if(!months.length) return;
  const cW=W-pad.l-pad.r, cH=H-pad.t-pad.b;
  const maxN = Math.max(...Object.values(byMonth));
  const barW = Math.max(8, Math.min(28, cW/months.length-4));

  drawGrid(ctx,W,H,pad,0,maxN,4,v=>Math.round(v).toString());

  months.forEach((m,i)=>{{
    const n=byMonth[m];
    const x=pad.l+(i/(months.length-1||1))*cW;
    const h=(n/maxN)*cH;
    const y=pad.t+cH-h;
    ctx.fillStyle = n>=4?'#34c77b':n>=2?'#4f8ef7':'#e05c6e';
    ctx.globalAlpha=.8;
    ctx.beginPath(); ctx.roundRect(x-barW/2,y,barW,h,[3,3,0,0]); ctx.fill();
    ctx.globalAlpha=1;
    // Label
    const [yr,mo]=m.split('-');
    const names=['','Jan','Feb','Mär','Apr','Mai','Jun','Jul','Aug','Sep','Okt','Nov','Dez'];
    ctx.fillStyle='#6b7194'; ctx.font='9px -apple-system,sans-serif'; ctx.textAlign='center';
    if(i%Math.max(1,Math.floor(months.length/10))===0)
      ctx.fillText(names[parseInt(mo)]+" '"+yr.slice(2), x, H-8);
  }});
}}

function buildGymTable() {{
  const sorted = [...GYM].sort((a,b)=> gymSortAsc? (a[gymSortCol]>b[gymSortCol]?1:-1) : (a[gymSortCol]<b[gymSortCol]?1:-1));
  $('gym-tbody').innerHTML = sorted.map(s=>{{
    const exStr = s.ex.map(e=>`${{e.name}} ${{e.w}}kg ${{e.s}}×${{e.r}}`).join(', ');
    return `<tr>
      <td>${{fmtDate(s.d)}}</td>
      <td>${{typeBadge(s.t)}}</td>
      <td>${{fmtNum(s.vol)}} kg</td>
      <td>${{s.n}}</td>
      <td>${{s.bench ? s.bench[0]+'kg ×'+s.bench[1] : '-'}}</td>
      <td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;font-size:11px;color:var(--muted)">${{exStr||'-'}}</td>
    </tr>`;
  }}).join('');
}}

function sortGymTable(col) {{
  if(gymSortCol===col) gymSortAsc=!gymSortAsc;
  else {{ gymSortCol=col; gymSortAsc=col==='d'?false:true; }}
  buildGymTable();
}}

// ═══════════════════════════════════════════════════════════════
// LAUFEN
// ═══════════════════════════════════════════════════════════════
let runMode = 'pace';
let runSortCol = 'd';
let runSortAsc = false;

function setRunMode(m) {{
  runMode = m;
  document.querySelectorAll('#page-laufen .toggle-btn').forEach(b=>b.classList.remove('on'));
  document.querySelector(`#page-laufen .toggle-btn[onclick="setRunMode('${{m}}')"]`).classList.add('on');
  drawPaceChart();
}}

function drawLaufen() {{
  const totalKm = RUNS.reduce((a,r)=>a+r.km, 0);
  const totalTime = RUNS.reduce((a,r)=>a+r.sec, 0);
  const validPaces = RUNS.filter(r=>r.pace>0&&r.pace<15);
  const avgPace = validPaces.length ? validPaces.reduce((a,r)=>a+r.pace,0)/validPaces.length : 0;
  const bestPace = validPaces.length ? Math.min(...validPaces.map(r=>r.pace)) : 0;
  const longestRun = Math.max(...RUNS.map(r=>r.km));

  $('run-subtitle').textContent = RUNS.length+' Läufe · '+Math.round(totalKm)+' km · '+Math.round(totalTime/3600)+'h '+Math.round((totalTime%3600)/60)+'m';
  $('run-kpis').innerHTML = [
    kpiCard(Math.round(totalKm)+'km', 'Gesamtdistanz', RUNS.length+' Läufe', '--green'),
    kpiCard(fmtPace(avgPace), 'Ø Pace', 'min/km', '--blue'),
    kpiCard(fmtPace(bestPace), 'Beste Pace', 'min/km', '--yellow'),
    kpiCard(longestRun.toFixed(1)+'km', 'Längster Lauf', '', '--purple'),
  ].join('');

  drawPaceChart();
  drawPaceDistScatter();
  drawRunMonthly();
  drawPaceHistogram();
  buildRunPRs();
  buildRunTable();
}}

function drawPaceChart() {{
  const canvas = $('pace-chart');
  const {{ctx,W,H}} = initCanvas(canvas, 300);
  const pad = {{l:54,r:20,t:20,b:36}};
  const cW=W-pad.l-pad.r, cH=H-pad.t-pad.b;

  const valid = RUNS.filter(r=>r.pace>0&&r.pace<15);
  if(!valid.length) return;

  let vals, yMin, yMax, unit, fmt;
  if(runMode==='pace') {{
    vals = valid.map(r=>r.pace);
    // Invert Y: lower pace = higher position
    yMin = Math.min(...vals)*0.9; yMax = Math.max(...vals)*1.05;
    unit = '/km'; fmt = v=>fmtPace(v);
    // For pace, we want high values at bottom (slow) and low at top (fast)
  }} else if(runMode==='dist') {{
    vals = valid.map(r=>r.km);
    yMin = 0; yMax = Math.max(...vals)*1.1;
    unit = 'km'; fmt = v=>v.toFixed(1)+'km';
  }} else {{
    vals = valid.map(r=>r.sec/60);
    yMin = 0; yMax = Math.max(...vals)*1.1;
    unit = 'min'; fmt = v=>Math.round(v)+'m';
  }}

  const invertY = runMode==='pace';
  const sy = v => {{
    if(invertY) return pad.t + ((v-yMin)/(yMax-yMin))*cH; // Higher pace = lower position
    return pad.t + cH - ((v-yMin)/(yMax-yMin))*cH;
  }};
  const sx = i => pad.l + (i/(valid.length-1||1))*cW;

  // Grid
  const steps = 5;
  ctx.strokeStyle='#1c2030'; ctx.lineWidth=1;
  ctx.fillStyle='#6b7194'; ctx.font='10px -apple-system,sans-serif'; ctx.textAlign='right';
  for(let i=0;i<=steps;i++) {{
    const y = pad.t + (i/steps)*cH;
    ctx.beginPath(); ctx.moveTo(pad.l,y); ctx.lineTo(W-pad.r,y); ctx.stroke();
    const val = invertY ? yMin+(i/steps)*(yMax-yMin) : yMax-(i/steps)*(yMax-yMin);
    ctx.fillText(fmt(val), pad.l-6, y+4);
  }}

  // Color dots by distance
  const distColor = km => {{
    if(km<5) return '#4f8ef7';
    if(km<10) return '#34c77b';
    if(km<15) return '#f7c948';
    return '#a78bfa';
  }};

  // Trend line
  const regPts = vals.map((v,i)=>({{x:i,y:v}}));
  const reg = linReg(regPts);
  ctx.strokeStyle = 'rgba(167,139,250,.5)';
  ctx.lineWidth = 1.5;
  ctx.setLineDash([5,4]);
  ctx.beginPath();
  ctx.moveTo(sx(0), sy(reg.intercept));
  ctx.lineTo(sx(valid.length-1), sy(reg.intercept+reg.slope*(valid.length-1)));
  ctx.stroke();
  ctx.setLineDash([]);

  // Trend label
  const trendPerMonth = reg.slope * 4; // ~4 runs per month
  ctx.fillStyle = '#a78bfa'; ctx.font='10px -apple-system,sans-serif'; ctx.textAlign='right';
  const trendText = runMode==='pace' ?
    (trendPerMonth<0 ? 'Verbesserung' : 'Verschlechterung') + ' '+Math.abs(trendPerMonth*60).toFixed(0)+'s/Monat' :
    (trendPerMonth>0 ? '+' : '')+trendPerMonth.toFixed(1)+unit+'/Monat';
  ctx.fillText('Trend: '+trendText, W-pad.r, pad.t-4);

  // Data points
  const pts = [];
  valid.forEach((r,i) => {{
    const x=sx(i), y=sy(vals[i]);
    ctx.fillStyle = distColor(r.km);
    ctx.globalAlpha = .9;
    ctx.beginPath(); ctx.arc(x,y,4,0,Math.PI*2); ctx.fill();
    ctx.globalAlpha = 1;
    pts.push({{x,y,data:r,val:vals[i]}});
  }});

  // X labels
  ctx.fillStyle='#6b7194'; ctx.font='10px -apple-system,sans-serif'; ctx.textAlign='center';
  const step = Math.max(1,Math.floor(valid.length/10));
  valid.forEach((r,i) => {{
    if(i%step===0||i===valid.length-1) ctx.fillText(fmtDate(r.d).slice(3,10), sx(i), H-pad.b+16);
  }});

  // Legend for distance colors
  ctx.textAlign='left';
  const legend = [['<5km','#4f8ef7'],['5-10km','#34c77b'],['10-15km','#f7c948'],['>15km','#a78bfa']];
  legend.forEach(([label,color],i) => {{
    const lx = pad.l + i*80;
    ctx.fillStyle=color; ctx.beginPath(); ctx.arc(lx,H-6,4,0,Math.PI*2); ctx.fill();
    ctx.fillStyle='#6b7194'; ctx.font='10px -apple-system,sans-serif';
    ctx.fillText(label, lx+8, H-2);
  }});

  setupHover(canvas, pts,
    p => {{
      if(runMode==='pace') return fmtPace(p.data.pace)+'/km';
      if(runMode==='dist') return p.data.km+'km';
      return fmtTime(p.data.sec);
    }},
    p => fmtDate(p.data.d)+' · '+p.data.km+'km · '+fmtPace(p.data.pace)+'/km'+(p.data.hr?' · HR '+p.data.hr:'')
  );
}}

function drawPaceDistScatter() {{
  const canvas = $('pace-dist-scatter');
  const {{ctx,W,H}} = initCanvas(canvas, 220);
  const pad = {{l:50,r:16,t:16,b:32}};
  const cW=W-pad.l-pad.r, cH=H-pad.t-pad.b;

  const valid = RUNS.filter(r=>r.pace>0&&r.pace<15);
  if(!valid.length) return;

  const xMin=0, xMax=Math.max(...valid.map(r=>r.km))*1.1;
  const yMin=Math.min(...valid.map(r=>r.pace))*0.92, yMax=Math.max(...valid.map(r=>r.pace))*1.05;

  // Grid
  ctx.strokeStyle='#1c2030'; ctx.lineWidth=1;
  for(let i=0;i<=4;i++) {{
    const y=pad.t+(i/4)*cH;
    ctx.beginPath(); ctx.moveTo(pad.l,y); ctx.lineTo(W-pad.r,y); ctx.stroke();
    const v=yMin+(i/4)*(yMax-yMin);
    ctx.fillStyle='#6b7194'; ctx.font='10px -apple-system,sans-serif'; ctx.textAlign='right';
    ctx.fillText(fmtPace(v), pad.l-6, y+4);
  }}
  // X axis
  for(let i=0;i<=4;i++) {{
    const x=pad.l+(i/4)*cW;
    ctx.fillStyle='#6b7194'; ctx.textAlign='center';
    ctx.fillText(Math.round(xMin+(i/4)*(xMax-xMin))+'km', x, H-8);
  }}

  // Y inverted for pace: high value = bottom
  const sy = v => pad.t+((v-yMin)/(yMax-yMin))*cH;
  const sx = v => pad.l+((v-xMin)/(xMax-xMin))*cW;

  // Trend line (pace vs dist)
  const regPts = valid.map(r=>({{x:r.km,y:r.pace}}));
  // Simple correlation
  const n=regPts.length;
  let sX=0,sY=0,sXX=0,sXY=0;
  regPts.forEach(p=>{{sX+=p.x;sY+=p.y;sXX+=p.x*p.x;sXY+=p.x*p.y;}});
  const slope=(n*sXY-sX*sY)/(n*sXX-sX*sX);
  const intercept=(sY-slope*sX)/n;

  ctx.strokeStyle='rgba(247,201,72,.4)'; ctx.lineWidth=1.5; ctx.setLineDash([4,3]);
  ctx.beginPath(); ctx.moveTo(sx(xMin),sy(intercept)); ctx.lineTo(sx(xMax),sy(intercept+slope*xMax)); ctx.stroke();
  ctx.setLineDash([]);

  const pts = [];
  valid.forEach(r => {{
    const x=sx(r.km), y=sy(r.pace);
    const recent = r.d >= '2025-01-01';
    ctx.fillStyle = recent ? '#34c77b' : '#4f8ef7';
    ctx.globalAlpha = recent ? .9 : .4;
    ctx.beginPath(); ctx.arc(x,y,4,0,Math.PI*2); ctx.fill();
    ctx.globalAlpha=1;
    pts.push({{x,y,data:r}});
  }});

  // Legend
  ctx.font='10px -apple-system,sans-serif';
  ctx.fillStyle='#34c77b'; ctx.beginPath(); ctx.arc(pad.l+10, pad.t+10, 4, 0, Math.PI*2); ctx.fill();
  ctx.fillStyle='#6b7194'; ctx.textAlign='left'; ctx.fillText('2025+', pad.l+18, pad.t+14);
  ctx.fillStyle='#4f8ef7'; ctx.globalAlpha=.5; ctx.beginPath(); ctx.arc(pad.l+60,pad.t+10,4,0,Math.PI*2); ctx.fill();
  ctx.globalAlpha=1; ctx.fillStyle='#6b7194'; ctx.fillText('Älter', pad.l+68, pad.t+14);

  setupHover(canvas, pts,
    p=>p.data.km+'km @ '+fmtPace(p.data.pace)+'/km',
    p=>fmtDate(p.data.d)+(p.data.hr?' · HR '+p.data.hr:'')
  );
}}

function drawRunMonthly() {{
  const canvas = $('run-monthly');
  const {{ctx,W,H}} = initCanvas(canvas, 220);
  const pad = {{l:50,r:16,t:16,b:32}};
  const cW=W-pad.l-pad.r, cH=H-pad.t-pad.b;

  const byMonth = {{}};
  RUNS.forEach(r=>{{
    const m=r.d.slice(0,7);
    if(!byMonth[m]) byMonth[m]={{km:0,runs:0,sec:0}};
    byMonth[m].km+=r.km;
    byMonth[m].runs++;
    byMonth[m].sec+=r.sec;
  }});
  const months = Object.keys(byMonth).sort();
  if(!months.length) return;

  const maxKm = Math.max(...months.map(m=>byMonth[m].km));
  const barW = Math.max(6, Math.min(24, cW/months.length-3));

  drawGrid(ctx,W,H,pad,0,maxKm*1.1,4,v=>Math.round(v)+'km');

  months.forEach((m,i) => {{
    const d=byMonth[m];
    const x=pad.l+(i/(months.length-1||1))*cW;
    const h=(d.km/(maxKm*1.1))*cH;
    const y=pad.t+cH-h;
    ctx.fillStyle='rgba(52,199,123,.7)';
    ctx.beginPath(); ctx.roundRect(x-barW/2,y,barW,h,[3,3,0,0]); ctx.fill();

    // Run count on top
    ctx.fillStyle='#6b7194'; ctx.font='9px -apple-system,sans-serif'; ctx.textAlign='center';
    ctx.fillText(d.runs+'×', x, y-4);

    // Month label
    const [yr,mo]=m.split('-');
    const names=['','J','F','M','A','M','J','J','A','S','O','N','D'];
    if(i%Math.max(1,Math.floor(months.length/12))===0)
      ctx.fillText(names[parseInt(mo)]+"'"+yr.slice(2), x, H-8);
  }});
}}

function drawPaceHistogram() {{
  const canvas = $('pace-histogram');
  const {{ctx,W,H}} = initCanvas(canvas, 180);
  const pad = {{l:44,r:16,t:16,b:28}};
  const cW=W-pad.l-pad.r, cH=H-pad.t-pad.b;

  const valid = RUNS.filter(r=>r.pace>0&&r.pace<15);
  // Bins: 4:00-8:00 in 0.5 increments
  const binSize = 0.5;
  const minPace = 4, maxPace = 9;
  const bins = [];
  for(let p=minPace; p<maxPace; p+=binSize) {{
    const count = valid.filter(r=>r.pace>=p&&r.pace<p+binSize).length;
    bins.push({{from:p, to:p+binSize, n:count}});
  }}
  const maxN = Math.max(...bins.map(b=>b.n));
  if(!maxN) return;

  const barW = cW/bins.length - 2;
  bins.forEach((b,i) => {{
    const x = pad.l + i*(barW+2);
    const h = (b.n/maxN)*cH;
    const y = pad.t+cH-h;
    ctx.fillStyle = b.from<5.5?'#34c77b':b.from<6.5?'#4f8ef7':'#f7c948';
    ctx.globalAlpha = .8;
    ctx.beginPath(); ctx.roundRect(x,y,barW,h,[3,3,0,0]); ctx.fill();
    ctx.globalAlpha=1;
    // Count label
    if(b.n>0) {{
      ctx.fillStyle='#e8eaf0'; ctx.font='10px -apple-system,sans-serif'; ctx.textAlign='center';
      ctx.fillText(b.n, x+barW/2, y-4);
    }}
    // X label
    ctx.fillStyle='#6b7194'; ctx.font='9px -apple-system,sans-serif'; ctx.textAlign='center';
    ctx.fillText(fmtPace(b.from), x+barW/2, H-8);
  }});
}}

function buildRunPRs() {{
  const valid = RUNS.filter(r=>r.pace>0&&r.pace<15);
  const categories = [
    {{label:'5K', filter: r=>r.km>=4.8&&r.km<=5.5}},
    {{label:'10K', filter: r=>r.km>=9.5&&r.km<=10.5}},
    {{label:'15K', filter: r=>r.km>=14.5&&r.km<=16}},
    {{label:'Halbmarathon', filter: r=>r.km>=20&&r.km<=22}},
    {{label:'Längster Lauf', filter: ()=>true, metric:'dist'}},
  ];

  let html = '';
  categories.forEach(cat => {{
    const candidates = valid.filter(cat.filter);
    if(!candidates.length) return;
    let best;
    if(cat.metric==='dist') {{
      best = candidates.reduce((a,b)=>a.km>b.km?a:b);
      html += `<div class="stat-row"><span class="stat-label">${{cat.label}}</span><span class="stat-value" style="color:var(--green)">${{best.km}} km</span></div>`;
    }} else {{
      best = candidates.reduce((a,b)=>a.pace<b.pace?a:b);
      html += `<div class="stat-row"><span class="stat-label">${{cat.label}}</span><span class="stat-value" style="color:var(--green)">${{fmtPace(best.pace)}}/km · ${{fmtTime(best.sec)}}</span></div>`;
    }}
    html += `<div style="font-size:11px;color:var(--muted);padding:0 0 8px;">${{fmtDate(best.d)}} · ${{best.km}}km</div>`;
  }});

  $('run-prs').innerHTML = html || '<div class="empty">Keine PRs</div>';
}}

function buildRunTable() {{
  const sorted = [...RUNS].sort((a,b) => runSortAsc ? (a[runSortCol]>b[runSortCol]?1:-1) : (a[runSortCol]<b[runSortCol]?1:-1));
  $('run-tbody').innerHTML = sorted.map(r => {{
    const paceColor = r.pace<5.5?'var(--green)':r.pace<6.5?'var(--blue)':'var(--yellow)';
    return `<tr>
      <td>${{fmtDate(r.d)}}</td>
      <td style="font-weight:600;color:var(--green)">${{r.km}} km</td>
      <td style="color:${{paceColor}};font-weight:600">${{fmtPace(r.pace)}}</td>
      <td>${{fmtTime(r.sec)}}</td>
      <td>${{r.hr||'-'}}</td>
      <td>${{r.cal||'-'}}</td>
      <td>${{r.elev?r.elev+'m':'-'}}</td>
    </tr>`;
  }}).join('');
}}

function sortRunTable(col) {{
  if(runSortCol===col) runSortAsc=!runSortAsc;
  else {{ runSortCol=col; runSortAsc=col==='d'?false:true; }}
  buildRunTable();
}}

// ═══════════════════════════════════════════════════════════════
// KÖRPER
// ═══════════════════════════════════════════════════════════════
function drawKoerper() {{
  const currentW = WEIGHT.length ? WEIGHT[WEIGHT.length-1].kg : 99;
  const goal = 90;
  const pct = Math.max(0, Math.round((1 - (currentW-goal)/(99-goal)) * 100));

  $('body-kpis').innerHTML = [
    kpiCard(currentW+'kg', 'Aktuell', '', '--text'),
    kpiCard(goal+'kg', 'Zielgewicht', '<90 kg', '--green'),
    kpiCard(Math.round((currentW-goal)*10)/10+'kg', 'Noch abzunehmen', '', '--yellow'),
    kpiCard(pct+'%', 'Fortschritt', 'zum Ziel', '--purple'),
  ].join('');

  // Weight chart
  const canvas = $('weight-chart');
  const {{ctx,W,H}} = initCanvas(canvas, 280);
  const pad = {{l:54,r:20,t:20,b:36}};

  if(WEIGHT.length < 2) {{
    ctx.fillStyle='#6b7194'; ctx.font='14px -apple-system,sans-serif'; ctx.textAlign='center';
    ctx.fillText('Noch nicht genug Daten — wiege dich jeden Montag morgens!', W/2, H/2-10);
    ctx.fillText('Aktuell: '+currentW+' kg → Ziel: '+goal+' kg', W/2, H/2+16);
    return;
  }}

  const cW=W-pad.l-pad.r, cH=H-pad.t-pad.b;
  const vals = WEIGHT.map(w=>w.kg);
  const yMin = Math.min(goal-2, ...vals)*0.98;
  const yMax = Math.max(...vals)*1.02;

  drawGrid(ctx,W,H,pad,yMin,yMax,5,v=>v.toFixed(1)+'kg');

  const sy=v=>pad.t+cH-((v-yMin)/(yMax-yMin))*cH;
  const sx=i=>pad.l+(i/(WEIGHT.length-1||1))*cW;

  // Goal line
  const goalY=sy(goal);
  ctx.strokeStyle='#34c77b'; ctx.lineWidth=1; ctx.setLineDash([4,4]); ctx.globalAlpha=.6;
  ctx.beginPath(); ctx.moveTo(pad.l,goalY); ctx.lineTo(W-pad.r,goalY); ctx.stroke();
  ctx.setLineDash([]); ctx.globalAlpha=1;
  ctx.fillStyle='#34c77b'; ctx.font='10px -apple-system,sans-serif'; ctx.textAlign='left';
  ctx.fillText('Ziel '+goal+'kg', pad.l+4, goalY-5);

  // Line
  ctx.strokeStyle='#f7c948'; ctx.lineWidth=2.5; ctx.lineJoin='round';
  ctx.beginPath();
  WEIGHT.forEach((w,i) => i===0 ? ctx.moveTo(sx(i),sy(w.kg)) : ctx.lineTo(sx(i),sy(w.kg)));
  ctx.stroke();

  // Dots
  WEIGHT.forEach((w,i) => {{
    ctx.fillStyle='#f7c948'; ctx.beginPath(); ctx.arc(sx(i),sy(w.kg),5,0,Math.PI*2); ctx.fill();
    ctx.fillStyle='#0e1018'; ctx.beginPath(); ctx.arc(sx(i),sy(w.kg),2.5,0,Math.PI*2); ctx.fill();
  }});
}}

// Goals
function drawGoals() {{
  const goals = [
    {{title:'Unter 90kg', current:WEIGHT.length?WEIGHT[WEIGHT.length-1].kg:99, target:90, start:99, unit:'kg', color:'var(--green)', invert:true}},
    {{title:'Bankdrücken 90kg', current: (() => {{ const b=[...GYM].reverse().find(s=>s.bench); return b?b.bench[0]:0; }})(), target:90, start:60, unit:'kg', color:'var(--blue)'}},
    {{title:'10km Lauf', current: Math.max(...RUNS.filter(r=>r.d>='2026-01-01').map(r=>r.km),0), target:10, start:0, unit:'km', color:'var(--purple)'}},
  ];

  $('goals-grid').innerHTML = goals.map(g => {{
    const pct = g.invert
      ? Math.max(0, Math.min(100, Math.round((1-(g.current-g.target)/(g.start-g.target))*100)))
      : Math.max(0, Math.min(100, Math.round(((g.current-g.start)/(g.target-g.start))*100)));
    return `<div class="card" style="padding:20px">
      <div style="font-size:13px;font-weight:600;margin-bottom:8px">${{g.title}}</div>
      <div style="font-size:24px;font-weight:700;color:${{g.color}}">${{g.current}}${{g.unit}}</div>
      <div style="font-size:12px;color:var(--muted);margin:4px 0 10px">Ziel: ${{g.target}}${{g.unit}}</div>
      <div class="progress"><div class="progress-fill" style="width:${{pct}}%;background:${{g.color}}"></div></div>
      <div style="font-size:11px;color:var(--muted);margin-top:4px">${{pct}}% erreicht</div>
    </div>`;
  }}).join('');
}}

// ═══════════════════════════════════════════════════════════════
// INIT
// ═══════════════════════════════════════════════════════════════
window.addEventListener('load', () => {{
  drawDashboard();
  drawGoals();
}});
window.addEventListener('resize', () => {{
  if(currentPage==='dashboard') drawDashboard();
  if(currentPage==='gym') drawGym();
  if(currentPage==='laufen') drawLaufen();
  if(currentPage==='koerper') drawKoerper();
}});
</script>
</body>
</html>'''


# ─────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Lade Daten...")
    runs = load_runs()
    gym = load_gym()
    weight = load_weight()

    print(f"  Läufe: {len(runs)}")
    print(f"  Gym-Sessions: {len(gym)}")
    print(f"  Gewichtseinträge: {len(weight)}")

    print("Generiere HTML...")
    html = generate_html(runs, gym, weight)

    output = BASE / "index.html"
    output.write_text(html, encoding="utf-8")
    size_kb = len(html.encode("utf-8")) / 1024
    print(f"✓ Dashboard generiert: {output}")
    print(f"  Dateigröße: {size_kb:.0f} KB")

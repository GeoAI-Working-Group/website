#!/usr/bin/env python3
"""Pull the lecture-tracking Google Sheet (all year tabs) -> data/lectures/history.json  (PUBLIC-SAFE: no emails/admin cols).

Sheet must be 'Anyone with the link can view'. Runs in CI (deploy.yml). Keeps the existing file on any failure.
usage: python scripts/sync_sheet.py [--sheet-id ID]
"""
import argparse, io, json, re, sys, urllib.request
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/lectures/history.json"
SHEET = "1Ank_MXj6GxYWZILDXpxIzktKDz7LYmdN24V0wh7S9u4"
COLS = {  # normalized header -> field (anything not listed, e.g. Email/Admin POC/Leave, is DROPPED)
    "date": "date", "meeting description": "title", "speaker": "speaker", "theme/tag": "theme", "theme": "theme",
    "sector": "sector", "skill tag": "skill", "skill": "skill", "ai category": "category", "category": "category",
    "media": "media", "admin status": "status", "status": "status", "paper link": "paper",
}
SKIP_THEMES = {"admin"}
SKIP_STATUS = {"hold", "n/a", "cancelled", "to be rescheduled"}
SKILL_NORM = {"bleeding edge": "Bleeding Edge", "advanced": "Advanced", "intermediate": "Intermediate", "basic": "Basic"}


def norm(s):
    return re.sub(r"\s+", " ", str(s or "").strip().lower())


EMAIL = re.compile(r"<?[\w.+-]+@[\w-]+(\.[\w-]+)+>?")
NONTALK = re.compile(r"^\s*(no meeting|hold|n/?a|-+|tbd|tbc)\s*$|\bmeeting\b|\badmin\b|\bcoordination\b", re.I)


def clean(v):
    """Public-safe text: drop emails / <addr>, collapse whitespace."""
    return re.sub(r"\s+", " ", EMAIL.sub("", str(v or ""))).strip(" ,;")


def cell_date(v):
    if isinstance(v, datetime): return v.date()
    if isinstance(v, date): return v
    for fmt in ("%m/%d/%y", "%m/%d/%Y", "%Y-%m-%d"):
        try: return datetime.strptime(str(v).strip(), fmt).date()
        except ValueError: pass
    return None


def parse(wb):
    talks = []
    for ws in wb.worksheets:
        if not re.fullmatch(r"\d{4}", ws.title.strip()):
            continue
        rows = list(ws.iter_rows())
        hdr_i = next((i for i, r in enumerate(rows[:15]) if {"date", "speaker"} <= {norm(c.value) for c in r}), None)
        if hdr_i is None:
            print(f"skip tab {ws.title}: no header", file=sys.stderr); continue
        idx = {}
        for j, c in enumerate(rows[hdr_i]):
            f = COLS.get(norm(c.value))
            if f and f not in idx: idx[f] = j
        for r in rows[hdr_i + 1:]:
            g = lambda f: r[idx[f]] if f in idx and idx[f] < len(r) else None
            d = cell_date(g("date").value if g("date") else None)
            sp = clean(g("speaker").value) if g("speaker") else ""
            th = str(g("theme").value or "").strip() if g("theme") else ""
            st = str(g("status").value or "").strip() if g("status") else ""
            ttl = clean(g("title").value) if g("title") else ""
            if not d or not sp or NONTALK.search(sp) or NONTALK.search(ttl or "x") or norm(th) in SKIP_THEMES or norm(st) in SKIP_STATUS or "[hold]" in norm(sp + str(g("title").value if g("title") else "")):
                continue
            media = None
            if g("media") is not None and g("media").hyperlink:
                media = g("media").hyperlink.target
                if not re.search(r"youtu\.?be", media or ""):
                    media = None  # only recording links are public; drafts/drawings/tweets stay in the sheet
            sector = str(g("sector").value or "").strip() if g("sector") else ""
            talks.append({
                "date": d.isoformat(), "year": d.year,
                "title": ttl or sp,
                "speaker": sp, "theme": th or "Unspecified",
                "sector": sector if sector and norm(sector) != "admin" else "Unspecified",
                "skill": SKILL_NORM.get(norm(g("skill").value if g("skill") else ""), "Unspecified"),
                "category": str(g("category").value or "").strip() or "Unspecified" if g("category") else "Unspecified",
                "status": st or None, "media": media,
            })
    return sorted(talks, key=lambda t: t["date"])


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--sheet-id", default=SHEET); a = ap.parse_args()
    try:
        import openpyxl
        url = f"https://docs.google.com/spreadsheets/d/{a.sheet_id}/export?format=xlsx"
        with urllib.request.urlopen(url, timeout=120) as r:
            wb = openpyxl.load_workbook(io.BytesIO(r.read()), data_only=True)
        talks = parse(wb)
    except Exception as e:
        print(f"warn: sheet sync failed ({e}); keeping {OUT.name}", file=sys.stderr); return 0
    if not talks:
        print("no rows parsed; keeping existing file"); return 0
    OUT.write_text(json.dumps({"source": f"google-sheet {a.sheet_id} (all year tabs)", "talks": talks}, indent=1, ensure_ascii=False))
    print(f"synced {len(talks)} lectures from {len({t['year'] for t in talks})} year tabs")


if __name__ == "__main__":
    sys.exit(main())

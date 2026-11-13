#!/usr/bin/env python3
"""Build public feeds + generated pages from data/.

Inputs : data/events/*.yml, data/lectures/*.yml
Outputs: docs/feeds/{events.xml, events.ics, events.json, lectures.ics, lectures.json}
         docs/events/index.md, docs/lectures/index.md, docs/_generated/{next.md, upcoming.md}

usage: python scripts/build_feeds.py [--site-url https://geoai-working-group.github.io/website/] [--today 2026-11-11]
"""
import argparse, json, sys, uuid
from datetime import date, datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
CT, ET = ZoneInfo("America/Chicago"), ZoneInfo("America/New_York")
NS = uuid.UUID("6f1c2c3e-4b7a-4c1e-9a55-0a6e0c9e1a11")


def d(x):
    return x if isinstance(x, date) and not isinstance(x, datetime) else date.fromisoformat(str(x)[:10])


def load(dirname):
    out = []
    for p in sorted((ROOT / "data" / dirname).glob("*.yml")):
        doc = yaml.safe_load(p.read_text())
        out.extend(doc if isinstance(doc, list) else [doc])
    return out


def validate_events(events):
    import jsonschema
    schema = json.loads((ROOT / "schema/event.schema.json").read_text())
    v = jsonschema.Draft202012Validator(schema)
    ids, errs = set(), []
    for e in events:
        doc = json.loads(json.dumps(e, default=str))
        errs += [f"{e.get('id')}: {x.message}" for x in v.iter_errors(doc)]
        if e["id"] in ids:
            errs.append(f"duplicate id {e['id']}")
        ids.add(e["id"])
    return errs


def esc_ics(s):
    return str(s or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def fold(line):  # RFC 5545 75-octet folding
    b = line.encode()
    if len(b) <= 75:
        return line
    parts, cur = [], b""
    for ch in line:
        c = ch.encode()
        if len(cur) + len(c) > (75 if not parts else 74):
            parts.append(cur.decode()); cur = b""
        cur += c
    parts.append(cur.decode())
    return "\r\n ".join(parts)


def ics(name, vevents):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Geo-AI WG//website//EN", "CALSCALE:GREGORIAN",
             f"X-WR-CALNAME:{name}", "X-WR-TIMEZONE:America/Chicago"]
    for ev in vevents:
        lines += ["BEGIN:VEVENT", f"DTSTAMP:{stamp}"] + [fold(f"{k}:{v}") for k, v in ev] + ["END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def event_vevents(events):
    for e in events:
        s, en = d(e["start"]), d(e.get("end") or e["start"])
        yield [("UID", f"{e['id']}@geoai-wg"), ("DTSTART;VALUE=DATE", f"{s:%Y%m%d}"),
               ("DTEND;VALUE=DATE", f"{en + timedelta(days=1):%Y%m%d}"), ("SUMMARY", esc_ics(e["title"])),
               ("LOCATION", esc_ics(e.get("location"))), ("URL", e["url"]),
               ("DESCRIPTION", esc_ics(f"{e.get('org', '')} — {e['url']}"))]
        for dl in e.get("deadlines") or []:
            dd = d(dl["date"])
            yield [("UID", f"{e['id']}-{dd:%Y%m%d}-deadline@geoai-wg"), ("DTSTART;VALUE=DATE", f"{dd:%Y%m%d}"),
                   ("DTEND;VALUE=DATE", f"{dd + timedelta(days=1):%Y%m%d}"),
                   ("SUMMARY", esc_ics(f"⏰ {dl['label']}: {e['title']}")), ("URL", e["url"])]


def lecture_vevents(lectures):
    for t in lectures:
        if t["status"] not in ("confirmed", "recorded"):
            continue
        s = datetime.fromisoformat(t["start"]).astimezone(timezone.utc)
        en = s + timedelta(minutes=t.get("duration_min") or 60)
        sp = t.get("speaker") or {}
        yield [("UID", f"lecture-{t['id']}@geoai-wg"), ("DTSTART", f"{s:%Y%m%dT%H%M%SZ}"),
               ("DTEND", f"{en:%Y%m%dT%H%M%SZ}"),
               ("SUMMARY", esc_ics(f"Geo-AI WG: {t.get('title') or 'TBA'} — {sp.get('name', 'TBA')}")),
               ("LOCATION", t.get("meeting_url", "")), ("URL", t.get("meeting_url", "")),
               ("DESCRIPTION", esc_ics(t.get("abstract")))]


def rss(site, events, lectures, today):
    items = []
    for e in events:
        pub = datetime.combine(d(e.get("verified_on") or today), datetime.min.time(), timezone.utc)
        when = d(e["start"]).strftime("%b %d, %Y") + (f" – {d(e['end']):%b %d, %Y}" if e.get("end") else "")
        dls = "; ".join(f"{x['label']}: {d(x['date']):%b %d, %Y}" for x in e.get("deadlines") or [])
        desc = f"{when} · {e.get('location', '')} · {e.get('org', '')}" + (f" · Deadlines — {dls}" if dls else "")
        items.append((pub, e["title"], e["url"], desc, f"event-{e['id']}", "Event"))
    for t in lectures:
        if t["status"] not in ("confirmed", "recorded"):
            continue
        sp = (t.get("speaker") or {}).get("name", "TBA")
        pub = datetime.fromisoformat(t["start"]).astimezone(timezone.utc) - timedelta(days=14)
        link = t.get("recording_url") or f"{site}lectures/"
        items.append((min(pub, datetime.now(timezone.utc)), f"Geo-AI WG Lecture: {t.get('title')} — {sp}", link,
                      fmt_ct_et(t["start"]) + " · " + (t.get("abstract") or ""), f"lecture-{t['id']}", "WG Lecture"))
    items.sort(key=lambda x: x[0], reverse=True)
    x = ['<?xml version="1.0" encoding="UTF-8"?>',
         '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom"><channel>',
         "<title>Geo-AI Working Group — Events &amp; Lectures</title>", f"<link>{escape(site)}</link>",
         f'<atom:link href="{escape(site)}feeds/events.xml" rel="self" type="application/rss+xml"/>',
         "<description>Geospatial AI conferences, deadlines, and Geo-AI WG lectures.</description>",
         f"<lastBuildDate>{format_datetime(datetime.now(timezone.utc))}</lastBuildDate>"]
    for pub, title, link, desc, guid, cat in items:
        x.append(f"<item><title>{escape(title)}</title><link>{escape(link)}</link>"
                 f"<guid isPermaLink=\"false\">{guid}</guid><category>{cat}</category>"
                 f"<pubDate>{format_datetime(pub)}</pubDate><description>{escape(desc)}</description></item>")
    x.append("</channel></rss>")
    return "\n".join(x) + "\n"


def fmt_ct_et(iso):
    s = datetime.fromisoformat(iso)
    c, e = s.astimezone(CT), s.astimezone(ET)
    return f"{c:%a %b %d, %Y} · {c:%-I:%M %p} {c.tzname()[0]}T / {e:%-I:%M %p} {e.tzname()[0]}T"


def md_events(events, today):
    up = [e for e in events if d(e.get("end") or e["start"]) >= today]
    past = [e for e in events if d(e.get("end") or e["start"]) < today]
    dls = sorted(((d(x["date"]), x["label"], e) for e in events for x in e.get("deadlines") or [] if d(x["date"]) >= today),
                 key=lambda r: r[0])
    o = ["# Geo-AI Events", "",
         "Conferences, workshops and deadlines relevant to geospatial AI. "
         "Subscribe: [:material-rss: RSS](../feeds/events.xml) · [:material-calendar: ICS](../feeds/events.ics) · "
         "[JSON](../feeds/events.json)", "",
         "[:material-plus: Submit an event](https://github.com/GeoAI-Working-Group/website/issues/new?template=submit-event.yml){ .md-button .md-button--primary }", ""]
    if dls:
        o += ["## Upcoming deadlines", "", "| Date | Deadline | Event |", "|---|---|---|"]
        o += [f"| {dd:%b %d, %Y} | {lab} | [{e['title']}]({e['url']}) |" for dd, lab, e in dls] + [""]
    o += ["## Upcoming", "", "| Dates | Event | Where | Org |", "|---|---|---|---|"]
    for e in sorted(up, key=lambda e: d(e["start"])):
        rng = f"{d(e['start']):%b %d}" + (f"–{d(e['end']):%b %d, %Y}" if e.get("end") else f", {d(e['start']).year}")
        o.append(f"| {rng} | [{e['title']}]({e['url']}) | {e.get('location', '')} | {e.get('org', '')} |")
    if past:
        o += ["", "??? note \"Past events\"", ""]
        o += [f"    - {d(e['start']):%b %Y} — [{e['title']}]({e['url']})" for e in sorted(past, key=lambda e: d(e['start']), reverse=True)]
    return "\n".join(o) + "\n"


def md_lectures(lectures, today):
    o = ["# Lecture Series", "",
         "Geo-AI WG talks on Google Meet. Add to calendar: [:material-calendar: ICS](../feeds/lectures.ics) · "
         "Past talks: [YouTube playlist](https://www.youtube.com/playlist?list=PLKlxghiZuIM59XVSjuye43qcHXRZLwQNN)", "",
         "| Date (CT / ET) | Speaker | Talk |", "|---|---|---|"]
    for t in sorted(lectures, key=lambda t: t["start"]):
        if t["status"] == "cancelled":
            continue
        sp = t.get("speaker") or {}
        who = f"**{sp['name']}**<br>{sp.get('affiliation', '')}" if sp.get("name") else "_Open slot_"
        if t["status"] == "recorded" and t.get("recording_url"):
            talk = f"[{t['title']}]({t['recording_url']}) :material-youtube:"
        elif t.get("title"):
            talk = t["title"]
        else:
            talk = "[Want to speak? Propose a talk](../join.md)"
        o.append(f"| {fmt_ct_et(t['start'])} | {who} | {talk} |")
    return "\n".join(o) + "\n"


def md_next(lectures, events, today):
    nxt = next((t for t in sorted(lectures, key=lambda t: t["start"])
                if t["status"] == "confirmed" and d(t["start"]) >= today), None)
    if nxt:
        sp = nxt["speaker"]
        s = (f"!!! tip \"Next lecture — {fmt_ct_et(nxt['start'])}\"\n    **{nxt['title']}**  \n"
             f"    {sp.get('name')}, {sp.get('affiliation', '')}  \n    [:material-video: Join on Google Meet]({nxt['meeting_url']})\n")
    else:
        s = "!!! tip \"Next lecture\"\n    Schedule coming soon — [see open 2027 slots](lectures/index.md).\n"
    up = sorted([e for e in events if d(e.get("end") or e["start"]) >= today], key=lambda e: d(e["start"]))[:5]
    u = "\n".join(f"- **{d(e['start']):%b %d, %Y}** — [{e['title']}]({e['url']})" for e in up)
    return s, u + "\n\n[All events →](events/index.md)\n"


def load_talks():
    pl = ROOT / "data/talks/playlist.yml"
    ov = ROOT / "data/talks/overrides.yml"
    vids = (yaml.safe_load(pl.read_text()) or {}).get("videos", []) if pl.exists() else []
    over = (yaml.safe_load(ov.read_text()) or {}) if ov.exists() else {}
    out = []
    for v in vids:
        v = {**v, **(over.get(v["id"]) or {})}
        if v.get("hide"):
            continue
        title = v["title"]
        if "speaker" not in v and " | " in title:
            t, sp = title.rsplit(" | ", 1)
            v["talk"], v["speaker"] = t.strip(), sp.strip()
        v.setdefault("talk", title)
        out.append(v)
    return sorted(out, key=lambda v: v.get("date") or "", reverse=True)


def md_talks(talks):
    pl = "https://www.youtube.com/playlist?list=PLKlxghiZuIM59XVSjuye43qcHXRZLwQNN"
    o = ["---", "hide: [navigation]", "---", "", "# Talk archive", "",
         f"**{len(talks)} recorded talks** from the Geo-AI Working Group. "
         f"Full playlist on [:fontawesome-brands-youtube: YouTube]({pl}). Synced automatically from the playlist on every site build.", ""]
    if not talks:
        return "\n".join(o + [f"_Playlist sync pending — [watch on YouTube]({pl})._"]) + "\n"
    year = None
    for v in talks:
        y = (v.get("date") or "Undated")[:4]
        if y != year:
            if year is not None:
                o.append("</div>\n")
            o += [f"## {y}", "", '<div class="talk-grid" markdown>', ""]
            year = y
        url = f"https://www.youtube.com/watch?v={v['id']}&list=PLKlxghiZuIM59XVSjuye43qcHXRZLwQNN"
        meta = " · ".join(x for x in (v.get("speaker"), v.get("date")) if x)
        extra = f' · [Slides]({v["slides"]})' if v.get("slides") else ""
        o += [f'<a class="talk-card" href="{url}" target="_blank" rel="noopener">'
              f'<img loading="lazy" src="https://i.ytimg.com/vi/{v["id"]}/mqdefault.jpg" alt="">'
              f'<span class="talk-title">{escape(v["talk"])}</span><span class="talk-meta">{escape(meta)}</span></a>'
              + (f"\n{extra}" if extra else ""), ""]
    o.append("</div>")
    return "\n".join(o) + "\n"


def md_stats(talks, lectures, events, today):
    up = sum(1 for e in events if d(e.get("end") or e["start"]) >= today)
    n = len(talks) or 68
    return (f'<div class="stats" markdown>\n'
            f'<div><span class="num">{n}</span><span class="lbl">recorded talks</span></div>\n'
            f'<div><span class="num">12</span><span class="lbl">book chapters (planned)</span></div>\n'
            f'<div><span class="num">{up}</span><span class="lbl">upcoming events tracked</span></div>\n'
            f'<div><span class="num">2019</span><span class="lbl">running since</span></div>\n'
            f'</div>\n')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site-url", default="https://geoai-working-group.github.io/website/")
    ap.add_argument("--today", default=None)
    a = ap.parse_args()
    today = d(a.today) if a.today else date.today()
    events, lectures = load("events"), load("lectures")
    errs = validate_events(events)
    if errs:
        print("\n".join(errs)); return 1
    (DOCS / "feeds").mkdir(parents=True, exist_ok=True)
    (DOCS / "_generated").mkdir(parents=True, exist_ok=True)
    w = lambda p, s: (DOCS / p).write_text(s)
    w("feeds/events.xml", rss(a.site_url, events, lectures, today))
    w("feeds/events.ics", ics("Geo-AI Events", list(event_vevents(events))))
    w("feeds/lectures.ics", ics("Geo-AI WG Lectures", list(lecture_vevents(lectures))))
    w("feeds/events.json", json.dumps(sorted(events, key=lambda e: str(e["start"])), default=str, indent=1))
    w("feeds/lectures.json", json.dumps(sorted(lectures, key=lambda t: t["start"]), default=str, indent=1))
    w("events/index.md", md_events(events, today))
    w("lectures/index.md", md_lectures(lectures, today))
    nxt, up = md_next(lectures, events, today)
    w("_generated/next.md", nxt); w("_generated/upcoming.md", up)
    talks = load_talks()
    (DOCS / "talks").mkdir(exist_ok=True)
    w("talks/index.md", md_talks(talks))
    w("_generated/stats.md", md_stats(talks, lectures, events, today))
    w("_generated/latest-talks.md", "\n".join(
        f'<a class="talk-card" href="https://www.youtube.com/watch?v={v["id"]}" target="_blank" rel="noopener">'
        f'<img loading="lazy" src="https://i.ytimg.com/vi/{v["id"]}/mqdefault.jpg" alt="">'
        f'<span class="talk-title">{escape(v["talk"])}</span><span class="talk-meta">{escape(v.get("speaker") or v.get("date") or "")}</span></a>'
        for v in talks[:3]) + "\n")
    print(f"built feeds: {len(events)} events, {len(lectures)} lecture slots")


if __name__ == "__main__":
    sys.exit(main())

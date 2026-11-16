#!/usr/bin/env python3
"""Sync the Geo-AI WG YouTube playlist -> data/talks/playlist.yml (runs in CI; GitHub runners can reach YouTube).

Order of attempts: YouTube Data API (if YT_API_KEY set) -> yt-dlp flat playlist -> keep existing file.
Manual extras (slides, speaker affiliation overrides) live in data/talks/overrides.yml keyed by video id.

usage: python scripts/sync_playlist.py [--playlist PLKlxghiZuIM59XVSjuye43qcHXRZLwQNN]
"""
import argparse, json, os, subprocess, sys, urllib.parse, urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/talks/playlist.yml"
PLAYLIST = "PLKlxghiZuIM59XVSjuye43qcHXRZLwQNN"


def via_api(pl, key):
    items, token = [], ""
    while True:
        q = urllib.parse.urlencode({"part": "snippet,contentDetails", "playlistId": pl, "maxResults": 50,
                                    "key": key, **({"pageToken": token} if token else {})})
        with urllib.request.urlopen(f"https://www.googleapis.com/youtube/v3/playlistItems?{q}", timeout=60) as r:
            j = json.load(r)
        for it in j["items"]:
            s, c = it["snippet"], it["contentDetails"]
            if s.get("title") in ("Private video", "Deleted video"):
                continue
            items.append({"id": c["videoId"], "title": s["title"],
                          "date": (c.get("videoPublishedAt") or s["publishedAt"])[:10],
                          "description": (s.get("description") or "")[:600]})
        token = j.get("nextPageToken")
        if not token:
            return items


def via_ytdlp(pl, flat=True):
    # --flat-playlist = one request for the whole list (robust on CI IPs); dates come from the sheet join / RSS
    cmd = ["yt-dlp", "--skip-download", "--ignore-errors", "--no-warnings", *(["--flat-playlist"] if flat else []),
           "--print", "%(id)s\t%(upload_date)s\t%(title)s", f"https://www.youtube.com/playlist?list={pl}"]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=1800).stdout
    items = []
    for line in out.splitlines():
        parts = line.split("\t", 2)
        if len(parts) == 3 and parts[0] and parts[2] not in ("[Private video]", "[Deleted video]"):
            vid, ud, title = parts
            items.append({"id": vid, "title": title,
                          "date": f"{ud[:4]}-{ud[4:6]}-{ud[6:]}" if ud and ud != "NA" else None})
    return items


def fill_dates(items, limit=120):
    """One yt-dlp call over only the still-undated videos (cached dates are reused, so later runs are tiny)."""
    todo = [it["id"] for it in items if not it.get("date")][:limit]
    if not todo:
        return
    cmd = ["yt-dlp", "--skip-download", "--ignore-errors", "--no-warnings", "--sleep-requests", "1",
           "--print", "%(id)s\t%(upload_date)s", *[f"https://www.youtube.com/watch?v={i}" for i in todo]]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=1500).stdout
    except Exception as e:
        print(f"warn: per-video dates: {e}", file=sys.stderr); return
    got = {}
    for line in out.splitlines():
        vid, _, ud = line.partition("\t")
        if len(ud) == 8 and ud.isdigit():
            got[vid] = f"{ud[:4]}-{ud[4:6]}-{ud[6:]}"
    for it in items:
        if not it.get("date") and it["id"] in got:
            it["date"] = got[it["id"]]
    print(f"dated {len(got)}/{len(todo)} videos via per-video lookup")


def add_rss_dates(pl, items):
    """Playlist RSS gives exact publish dates for the newest ~15 videos; keep any date we already have."""
    import xml.etree.ElementTree as ET
    try:
        with urllib.request.urlopen(f"https://www.youtube.com/feeds/videos.xml?playlist_id={pl}", timeout=30) as r:
            root = ET.fromstring(r.read())
        ns = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}
        dates = {e.findtext("yt:videoId", namespaces=ns): e.findtext("a:published", namespaces=ns)[:10] for e in root.findall("a:entry", ns)}
        for it in items:
            if not it.get("date") and it["id"] in dates:
                it["date"] = dates[it["id"]]
    except Exception as e:
        print(f"warn: rss dates: {e}", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--playlist", default=PLAYLIST)
    a = ap.parse_args()
    items, src = [], None
    key = os.environ.get("YT_API_KEY")
    try:
        if key:
            items, src = via_api(a.playlist, key), "api"
        if not items:
            items, src = via_ytdlp(a.playlist), "yt-dlp-flat"
        if items and OUT.exists():
            old = {v["id"]: v for v in (yaml.safe_load(OUT.read_text()) or {}).get("videos", [])}
            for it in items:
                if not it.get("date") and old.get(it["id"], {}).get("date"):
                    it["date"] = old[it["id"]]["date"]
        if items:
            add_rss_dates(a.playlist, items)
            if src != "api":
                fill_dates(items)
    except Exception as e:
        print(f"warn: sync failed ({e}); keeping existing {OUT.name}", file=sys.stderr)
    if not items:
        print("no items fetched; existing playlist.yml kept")
        return 0
    if OUT.exists():
        old = {v["id"]: v for v in (yaml.safe_load(OUT.read_text()) or {}).get("videos", [])}
        for it in items:
            if not it.get("date") and old.get(it["id"], {}).get("date"):
                it["date"] = old[it["id"]]["date"]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(yaml.safe_dump({"playlist": a.playlist, "source": src, "count": len(items), "videos": items},
                                  sort_keys=False, allow_unicode=True, width=200))
    print(f"synced {len(items)} videos via {src}")


if __name__ == "__main__":
    sys.exit(main())

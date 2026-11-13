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


def via_ytdlp(pl):
    # full metadata (not --flat-playlist) so upload_date is populated
    cmd = ["yt-dlp", "--skip-download", "--ignore-errors", "--no-warnings", "--print",
           "%(id)s\t%(upload_date)s\t%(title)s", f"https://www.youtube.com/playlist?list={pl}"]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=1800).stdout
    items = []
    for line in out.splitlines():
        parts = line.split("\t", 2)
        if len(parts) == 3 and parts[0] and parts[2] not in ("[Private video]", "[Deleted video]"):
            vid, ud, title = parts
            items.append({"id": vid, "title": title,
                          "date": f"{ud[:4]}-{ud[4:6]}-{ud[6:]}" if ud and ud != "NA" else None})
    return items


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
            items, src = via_ytdlp(a.playlist), "yt-dlp"
    except Exception as e:
        print(f"warn: sync failed ({e}); keeping existing {OUT.name}", file=sys.stderr)
    if not items:
        print("no items fetched; existing playlist.yml kept")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(yaml.safe_dump({"playlist": a.playlist, "source": src, "count": len(items), "videos": items},
                                  sort_keys=False, allow_unicode=True, width=200))
    print(f"synced {len(items)} videos via {src}")


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Convert a 'Submit a Geo-AI event' issue-form body (stdin) to data/events/<year>-<id>.yml. Prints the path."""
import re, sys, unicodedata
from datetime import date
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
LABELS = {"Event name": "title", "Official URL": "url", "Start date (YYYY-MM-DD)": "start",
          "End date (YYYY-MM-DD, optional)": "end", "Location (or \"Online\")": "location", "Format": "format",
          "Type": "type", "Organizer / society": "org",
          "Deadlines (optional, one per line as \"YYYY-MM-DD Label\")": "deadlines", "Tags (comma-separated)": "tags"}


def slug(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:60]


def parse(body):
    out = {}
    for block in re.split(r"^### ", body, flags=re.M)[1:]:
        head, _, val = block.partition("\n")
        val = val.strip()
        if head.strip() in LABELS and val and val != "_No response_":
            out[LABELS[head.strip()]] = val
    return out


def main():
    f = parse(sys.stdin.read())
    start = date.fromisoformat(f["start"])
    ev = {"id": f"{slug(f['title'])}" if str(start.year) in f["title"] else f"{slug(f['title'])}-{start.year}",
          "title": f["title"], "start": start}
    if f.get("end"): ev["end"] = date.fromisoformat(f["end"])
    for k in ("location", "format", "type", "org", "url"):
        if f.get(k): ev[k] = f[k]
    ev.setdefault("type", "other")
    if f.get("deadlines"):
        ev["deadlines"] = [{"label": l[11:].strip() or "Deadline", "date": date.fromisoformat(l[:10])}
                           for l in f["deadlines"].splitlines() if re.match(r"\d{4}-\d{2}-\d{2}", l.strip())]
    if f.get("tags"): ev["tags"] = [t.strip() for t in f["tags"].split(",") if t.strip()]
    ev["added_by"] = "community"
    p = ROOT / "data/events" / f"{start.year}-{ev['id']}.yml"
    p.write_text(yaml.safe_dump(ev, sort_keys=False, allow_unicode=True))
    print(p.relative_to(ROOT))


if __name__ == "__main__":
    main()

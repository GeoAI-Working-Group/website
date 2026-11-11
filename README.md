# website (public)

Geo-AI WG website — MkDocs Material on GitHub Pages, modeled on [gee-community-catalog.org](https://gee-community-catalog.org/). The EarthRISE book is the central feature.

| Path | What |
|---|---|
| `data/events/*.yml` | Events feed source (one file per event edition; schema `schema/event.schema.json`) |
| `data/lectures/<year>.yml` | **Generated** by `lecture-series` → `export-to-website` (don't hand-edit) |
| `scripts/build_feeds.py` | → `docs/feeds/{events.xml,events.ics,events.json,lectures.ics,lectures.json}` + Events/Lectures pages |
| `scripts/issue_to_event.py` | Issue form → event YAML (used by `event-from-issue.yml`) |
| `docs/talks/` | Rehosted slides/materials |

Public feeds (after deploy): `/feeds/events.xml` (RSS), `/feeds/events.ics`, `/feeds/lectures.ics`, `/feeds/events.json`.

```bash
pip install mkdocs-material pyyaml jsonschema
python scripts/build_feeds.py && mkdocs serve
```
Setup: Settings → Pages → Source: **GitHub Actions**.
Custom domain (later): add `docs/CNAME` with the domain, set `site_url` in `mkdocs.yml`, set the DNS CNAME → `geoai-working-group.github.io`, then update `group-context.md` in wg-skills so invites use it. v2 (later): LLM search / agentic chatbot.

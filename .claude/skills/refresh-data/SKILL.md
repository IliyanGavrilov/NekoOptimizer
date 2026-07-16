---
name: refresh-data
description: How to refresh Neko Optimizer's committed game data (unit catalogue, gacha schedule/pools, stats, tier list) from the BCData mirror + godfat and import it into the DB. Use when re-fetching or updating units.json / gacha_events.json / gacha_pools.json / stats.json / tiers.json, or when the BCData mirror's expired TLS cert blocks a fetch.
---

# Refreshing game data

Two stages: **fetch** (network → committed JSON) then **import** (JSON → DB). Run every command as `.venv/Scripts/python.exe manage.py <cmd>`. The web app never hits the network — these offline management commands are the only fetch path, and their JSON output is committed to the repo.

## Stage 1 — fetch into `neko/data/*.json`

| Command | Writes | Source |
|---|---|---|
| `fetch_units` | `units.json` | BCData mirror tarball (`--tarball PATH` to use a local one) |
| `fetch_gacha` | `gacha_events.json` + `gacha_pools.json` | godfat event TSVs (schedule) + BCData pools |
| `fetch_stats` | `stats.json` | BCData mirror + battlecatsinfo (`--tarball PATH` supported) |
| `fetch_tiers` | `tiers.json` | battlecatstierlist.com |

### Gotcha: the BCData mirror's TLS cert is expired
`git.battlecatsmodding.org` presents an expired chain that **Python/OpenSSL (urllib) rejects** — so `fetch_units` and `fetch_stats` fail locally with `certificate has expired`. `curl.exe` uses Windows schannel and accepts it. Workaround: download the tarball with curl, then feed it via `--tarball`.

```bash
BASE=https://git.battlecatsmodding.org/fieryhenry/BCData
curl.exe -sL "$BASE/raw/metadata.json" -o metadata.json
# release URL is data-driven: base_url + versions[en][latest]  (see neko/bcdata.py release_url/latest_version)
URL=$(.venv/Scripts/python.exe -c "import json; m=json.load(open('metadata.json')); v=max(m['versions']['en'], key=lambda s: tuple(map(int, s.split('.')))); print(m['base_url'] + m['versions']['en'][v])")
curl.exe -sL "$URL" -o bcdata.tar.xz
.venv/Scripts/python.exe manage.py fetch_units --tarball bcdata.tar.xz
.venv/Scripts/python.exe manage.py fetch_stats --tarball bcdata.tar.xz
```

`fetch_gacha` (godfat TSVs) and `fetch_tiers` (tier-list site) don't use the BCData mirror, so they run normally without the workaround.

## Stage 2 — import into the DB (order matters)

1. `import_units` — loads `units.json` into DB `Unit` rows. **Run first**: this is the canonical catalogue; owned/wishlist are keyed to `unit_id` and survive re-imports.
2. `import_catalogue` — populates every scheduled banner's cats from the gacha pools (needs the gacha data from stage 1). This is the full, schedule-driven cat import.
3. `reconcile_units` — merges provisional stand-in units into their now-canonical namesakes; prints any still-orphaned names.
4. `match_units` — read-only report: which imported cat names map to a canonical unit and which don't. Use it to sanity-check the import.

`import_cats <seed>` is the older seed-based variant (populates only the banners active for one seed) — `import_catalogue` supersedes it for a full refresh.

## After a refresh

- The regenerated JSON changes the roll data, so run the gate before committing: `ruff check` + `ruff format --check` + `pytest -q`. The **golden test (seed 1893568593)** is the one that proves byte-parity with godfat still holds after new data — if it fails, the parser/data drifted, don't commit.
- Commit the regenerated JSON per the usual conventions (stage by path, plain subject, no traces). Delete the scratch `metadata.json` / `bcdata.tar.xz`.

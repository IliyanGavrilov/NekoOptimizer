---
name: refresh-data
description: How to refresh Neko Optimizer's committed game data (unit catalogue, gacha schedule/pools, stats, tier list) from the BCData mirror + godfat and import it into the DB. Use when re-fetching or updating units.json / gacha_events.json / gacha_pools.json / stats.json / tiers.json, or when the BCData mirror's expired TLS cert blocks a fetch.
---

# Refreshing game data

Two stages: **fetch** (network → committed JSON) then **import** (JSON → DB). Run every command as `.venv/Scripts/python.exe manage.py <cmd>`. The web app never hits the network — these offline management commands are the only fetch path, and their JSON output is committed to the repo.

**Everything is per game version.** `--region {en,jp,tw,kr}` (default `en`) picks which one; region-scoped files live in `neko/data/<region>/`, and the DB keeps one set of rows per region (`Unit`, `Cat`, `Banner`, `CannonPlan`, `Seed`). A full refresh means running each stage once per region.

## Stage 1 — fetch into `neko/data/<region>/*.json`

| Command | Writes | Source |
|---|---|---|
| `fetch_units` | `<region>/units.json` | BCData mirror tarball (`--tarball PATH` to use a local one) |
| `fetch_gacha` | `<region>/gacha_events.json` + `gacha_pools.json` + `gacha_series.json` | godfat event TSVs (schedule) + BCData pools |
| `fetch_stats` | `<region>/stats.json` | BCData mirror + battlecatsinfo (`--tarball PATH` supported) |
| `fetch_gamedata` | `<region>/combos.json` + `talents.json` + `evolve.json` + `items.json` + `cannon.json` | BCData mirror (`--tarball PATH` supported) |
| `fetch_guide` | `guide_order.json` (all regions, one file) | wiki Cat_Guide/Units page; resolves each region's names against **that region's** committed catalogue, so run it after every `fetch_units` |
| `fetch_tiers` | `tiers.json` (shared, EN-sourced) | battlecatstierlist.com - the cumulative list plus every per-set list its nav links (41 of them) |
| `fetch_icons` | `planner/static/planner/icons/u/<id>/<form>.png` (gitignored) | battlecatsinfo's image CDN; only fetches what's missing, so re-runs are cheap. Once the directory exists `settings.ICON_BASE` serves it instead of hotlinking - `NEKO_ICON_BASE` overrides either way |

Order within a region: `fetch_units` first (`fetch_stats` reads its records), then the rest.

### Gotcha: the BCData mirror's TLS cert is expired
`git.battlecatsmodding.org` presents an expired chain that **Python/OpenSSL (urllib) rejects** — so `fetch_units` and `fetch_stats` fail locally with `certificate has expired`. `curl.exe` uses Windows schannel and accepts it. Workaround: download the tarball with curl, then feed it via `--tarball`.

```bash
BASE=https://git.battlecatsmodding.org/fieryhenry/BCData
curl.exe -sL "$BASE/raw/metadata.json" -o metadata.json
# The metadata keys each version by our own region codes; the release URL is data-driven:
# base_url + versions[region][latest]  (see neko/bcdata.py release_url/latest_version)
for R in en jp tw kr; do
  URL=$(.venv/Scripts/python.exe -c "import json,sys; m=json.load(open('metadata.json')); r=sys.argv[1]; v=max(m['versions'][r], key=lambda s: tuple(map(int, s.split('.')))); print(m['base_url'] + m['versions'][r][v])" "$R")
  curl.exe -sL "$URL" -o "$R.tar.xz"
  .venv/Scripts/python.exe manage.py fetch_units    --region "$R" --tarball "$R.tar.xz"
  .venv/Scripts/python.exe manage.py fetch_gamedata --region "$R" --tarball "$R.tar.xz"
  .venv/Scripts/python.exe manage.py fetch_stats    --region "$R" --tarball "$R.tar.xz"
  .venv/Scripts/python.exe manage.py fetch_gacha    --region "$R" --tarball "$R.tar.xz"
done
```

`fetch_gacha` (godfat TSVs), `fetch_tiers` (tier-list site) and `fetch_icons` (image CDN) don't use the BCData mirror, so they run normally without the workaround.

A tier-list name the catalogue can't place keeps its community spelling and loses its icon; `neko/tierdata.py`'s `_ALIASES` is where a fixable one gets pinned to a unit id. Most leftovers are units the EN catalogue genuinely lacks (JP-only, Ancient Egg nicknames).

## Stage 2 — import into the DB (order matters, `--region` on every step)

1. `import_units` — loads that region's `units.json` into DB `Unit` rows. **Run first**: this is the canonical catalogue; owned/wishlist are keyed to `unit_id` within the region and survive re-imports.
2. `import_catalogue` — populates every scheduled banner's cats from the gacha pools (needs the gacha data from stage 1). This is the full, schedule-driven cat import.
3. `reconcile_units` — merges provisional stand-in units into their now-canonical namesakes; prints any still-orphaned names.
4. `match_units` — read-only report: which imported cat names map to a canonical unit and which don't. Use it to sanity-check the import.

`import_cats <seed>` is the older seed-based variant (populates only the banners active for one seed) — `import_catalogue` supersedes it for a full refresh.

## After a refresh

- The regenerated JSON changes the roll data, so run the gate before committing: `ruff check` + `ruff format --check` + `pytest -q`. The **golden test (seed 1893568593)** is the one that proves byte-parity with godfat still holds after new data — if it fails, the parser/data drifted, don't commit.
- Commit the regenerated JSON per the usual conventions (stage by path, plain subject, no traces). Delete the scratch `metadata.json` / `bcdata.tar.xz`.

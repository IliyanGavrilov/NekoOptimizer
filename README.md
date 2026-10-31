# Neko Optimizer

[![CI](https://github.com/IliyanGavrilov/NekoOptimizer/actions/workflows/ci.yml/badge.svg)](https://github.com/IliyanGavrilov/NekoOptimizer/actions/workflows/ci.yml)
[![CodeQL](https://github.com/IliyanGavrilov/NekoOptimizer/actions/workflows/codeql.yml/badge.svg)](https://github.com/IliyanGavrilov/NekoOptimizer/actions/workflows/codeql.yml)
[![Security](https://github.com/IliyanGavrilov/NekoOptimizer/actions/workflows/security.yml/badge.svg)](https://github.com/IliyanGavrilov/NekoOptimizer/actions/workflows/security.yml)
![Python 3.14+](https://img.shields.io/badge/python-3.14%2B-blue)
![Django 6.1](https://img.shields.io/badge/Django-6.1-092E20)

**Live: [neko-optimizer.vercel.app](https://neko-optimizer.vercel.app/)** - free to use, no sign-up needed (an account just keeps your collection across devices).

A planning tool for *The Battle Cats* gacha. Given a set of target cats and a
budget of tickets and catfood, it computes **where and when to pull, in which
order, for the lowest resource cost**.

Battle Cats drives every banner from a single shared XOR-shift PRNG seed, so the
entire future pull sequence is deterministic once the seed is known. Neko
Optimizer rolls that sequence locally with its own engine, treats the pulls as a
state graph, and searches it (A\* / beam) for the cheapest path that collects the
wishlist.

## Layout

| Path | Purpose |
|------|---------|
| `neko/` | Pure-Python core - RNG, roll engine, models, graph builder, A\*/beam search, subset solver, and the game-data loaders. Django-independent and unit-testable in isolation. |
| `neko/data/` | Committed game data as JSON, one directory per game version (`en/`, `jp/`, `tw/`, `kr/`) - the unit catalogue plus the gacha schedule, pools, series, stats and materials data - alongside the version-independent files (multi-roll configs, Cat Guide order, tier list). Lets the app run fully offline. |
| `planner/` | The Django app - views, forms, models, `services.py` (the roll-to-plan glue), templates, static JS, and the data-fetch/import management commands. |
| `planner/static/planner/neko.wasm` | The compiled browser engine (built from `wasm/`), run in Web Workers by the page's JS. |
| `wasm/` | Rust crate behind `neko.wasm` - the planner engine (rolls, graph, search), the seed finder's sieve over all 2^32 seeds, and the Cat Guide screenshot reader. |
| `nekosite/` | Django project configuration (settings, URLs, WSGI/ASGI). |
| `manage.py` | Django entry point. |
| `vercel.json`, `build.sh` | Vercel deploy config and build step (icons, migrations, deploy checks). |

## Prerequisites

- **[Python](https://www.python.org/) 3.14+**
- **[Git](https://git-scm.com/)** (to clone)
- No database server for local use - the app falls back to file-based
  [SQLite](https://www.sqlite.org/) when `DATABASE_URL` is unset.
- [Rust](https://www.rust-lang.org/) with the `wasm32-unknown-unknown` target only
  if you change `wasm/`; the compiled `neko.wasm` is committed.
- Internet access is only needed to *refresh* the game data; the committed files
  in `neko/data/` are enough to run everything offline.

## Setup

From a clean clone:

```bash
# 1. Clone
git clone <repo-url>
cd NekoOptimizer

# 2. Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate            # Windows (PowerShell/cmd)
# source .venv/bin/activate       # Linux / macOS

# 3. Install dependencies (requirements.txt alone is enough to run the site)
pip install -r requirements-dev.txt

# 4. Create the local database
python manage.py migrate

# 5. Load the unit catalogue and cats into the database
python manage.py import_units       # from the committed neko/data/en/units.json
python manage.py import_catalogue    # populate cats from every scheduled banner
```

Every command that touches game data takes `--region {en,jp,tw,kr}` (default `en`).
Each version keeps its own catalogue rows and its own collection, so repeat steps 5
for any other version you want to plan for.

## Running it

```bash
python manage.py runserver          # dev server at http://127.0.0.1:8000/
pytest                              # run the test suite
ruff check .                        # lint
ruff format .                       # format (2-space indent, 100 cols)
```

### Rebuilding the browser engine

```bash
cd wasm
cargo build --release --target wasm32-unknown-unknown
cp target/wasm32-unknown-unknown/release/nekowasm.wasm ../planner/static/planner/neko.wasm
cargo test --release                # the Rust tests
```

### Translations

Each game version's pages speak its players' language (`/jp/` Japanese, `/tw/` Traditional
Chinese, `/kr/` Korean); the header's language picker overrides it. The catalogues live in
`planner/locale/`, with the shared terms in `planner/locale/GLOSSARY.md`; the guides and the
About page are whole templates per language under `planner/templates/planner/<language>/`.
After changing any text, refresh the catalogues, fill in the new strings, and compile them -
the compiled `.mo` files are committed, since the deploy has no `msgfmt`:

```bash
cd planner
python ../manage.py makemessages -l ja -l zh_Hant -l ko
python ../manage.py makemessages -d djangojs -l ja -l zh_Hant -l ko
python ../manage.py compilemessages -l ja -l zh_Hant -l ko
```

gettext before 0.21 can't parse JavaScript template literals and skips strings after them;
`planner/test_translation.py` fails on any script or engine string left untranslated.

### Deploying

Production runs on [Vercel](https://vercel.com/) (region `fra1`, next to its Postgres
database); only `main` deploys. Set `DATABASE_URL` (Postgres) and `DJANGO_SECRET_KEY` in the project; Vercel's own
hostnames are allowed automatically, `DJANGO_ALLOWED_HOSTS` adds a custom domain. `SITE_URL`
(default `https://neko-optimizer.vercel.app`) is the public address canonical links, the
sitemap and link previews use; `GOOGLE_SITE_VERIFICATION` and `BING_SITE_VERIFICATION` add Search Console's and Bing
Webmaster Tools' meta tags. With `DEBUG` off and no `DATABASE_URL` the app
refuses to start rather than silently using SQLite.

### Refreshing the game data (network)

The catalogue and schedule are committed, so these are only needed to pull in a
newer game version:

| Command | What it does |
|---------|--------------|
| `python manage.py fetch_units` | Download the latest unit catalogue from the BCData mirror into `neko/data/<region>/units.json`. |
| `python manage.py fetch_gacha` | Download the gacha schedule (godfat event TSVs) and pools (BCData) into `neko/data/<region>/`. |
| `python manage.py fetch_gamedata` | Download combos, talents, evolution costs, item names, and cannon recipes (BCData) into `neko/data/<region>/`. |
| `python manage.py fetch_guide` | Download the in-game Cat Guide order per region (wiki) into `neko/data/guide_order.json`. |
| `python manage.py fetch_stats` | Download unit stats (BCData + battlecatsinfo) into `neko/data/<region>/stats.json`. |
| `python manage.py fetch_tiers` | Download the cumulative tier list and every per-set one (battlecatstierlist.com) into `neko/data/tiers.json`. |
| `python manage.py fetch_icons` | Download each unit's form icons (battlecatsinfo) into `planner/static/planner/icons/`. Once they are there the site serves its own copies instead of hotlinking; `NEKO_ICON_BASE` overrides the choice. |
| `python manage.py import_units` | Load that region's `units.json` into the database. |
| `python manage.py import_catalogue` | Populate the cat catalogue from every scheduled banner's pool. |
| `python manage.py import_cats <seed>` | Populate the catalogue by rolling the active banners for a seed. |
| `python manage.py match_units` | Report which cat names map to a canonical unit. |
| `python manage.py reconcile_units` | Merge provisional stand-in units into their now-canonical namesakes. |

The `refresh-data` workflow runs the fetches daily: it opens a pull request when the data
changed and merges it once the checks pass. It needs `DATA_PR_TOKEN`, a fine-grained token
for this repository with Contents and Pull requests write access, since a pull request
opened with the workflow's own token runs no checks. `import-data` then loads whatever
data reaches `main`, however it was merged, into the live database (`DATABASE_URL`
secret); run it by hand to backfill. A failure in either opens an issue.

## How to use

1. Open **http://127.0.0.1:8000/** (or the live site).
2. Enter your current shared **seed** - or find it on the **Seed Finder** page
   (`/seek/`): roll in-game, record the cats you got, and it scans every possible
   seed in your browser for the one that deals exactly those.
3. Pick the **target cats** you want, and/or tick **search my wishlist** to
   include everything you have marked wanted.
4. Set your **budget** (tickets + catfood), or switch on **Explore mode** to plan
   without a budget.
5. Hit **Find plan** - you get the cheapest pull path, with the A/B roll tracks
   laid out and each step highlighted, plus guaranteed-Uber columns and
   duplicate-reroll branches.
6. **Apply plan** marks the obtained cats as owned and advances the stored seed,
   so you can plan the next stretch from where you left off.
7. The **Collection** page (`/collection/`) is the full cat dictionary in the
   in-game Cat Guide order (or by rarity / gacha set), where you manage owned /
   wishlist marks and filter by targets, abilities, combos, and talents. Import
   it from Cat Guide screenshots (read in the browser), or export / import it as a file.
8. The **Resources** page (`/resources/`) tracks what to grind: pick cats to
   evolve (catfruit / stones / gems + XP totals), talents to buy (NP totals),
   and cannons to develop (per-part level ranges with material / engineer /
   build-time totals).
9. The **Normal Capsules** page (`/normal/`) predicts the normal-seed machines
   (Catfruit, Catseye, Lucky Tickets...) and plans the pulls that land what you want.
10. The **Tier List** page (`/tiers/`) ranks Ubers and Legends overall and per gacha set.
11. **Sign up / Log in** is optional: without an account your seed, collection and
    plans are kept against a cookie in this browser; with one they follow you across devices.
12. The **EN / JP / TW / KR** switch in the header picks the game version. Each
   version has its own catalogue, schedule, pools and localized names, and keeps
   its own seed and collection - the roll mechanics are identical across all four.

## Tech stack

- [Python 3.14](https://www.python.org/) - `dataclasses`, `heapq`, `csv`, `enum`
  from the standard library carry the core engine.
- [Django 6.1](https://www.djangoproject.com/) - web framework (views, ORM, templates,
  auth, management commands).
- [Rust](https://www.rust-lang.org/) compiled to [WebAssembly](https://webassembly.org/) -
  the engine that rolls, plans, sieves seeds and reads Cat Guide screenshots in the
  browser, in Web Workers, so the server only renders.
- Vanilla JavaScript - no frontend framework or bundler.
- [PostgreSQL](https://www.postgresql.org/) in production via
  [psycopg](https://www.psycopg.org/) and
  [dj-database-url](https://github.com/jazzband/dj-database-url);
  [SQLite](https://www.sqlite.org/) locally.
- [WhiteNoise](https://whitenoise.readthedocs.io/) - compressed, cache-busted static files.
- [Vercel](https://vercel.com/) - hosting (serverless Python).
- [GitHub Actions](https://github.com/features/actions) - CI, CodeQL, security scans,
  Dependabot, scheduled game-data refresh, releases.
- [pytest](https://docs.pytest.org/) + [pytest-django](https://pytest-django.readthedocs.io/) -
  test suite; [wasmtime](https://wasmtime.dev/) runs the shipped `neko.wasm` in the tests.
- [Ruff](https://docs.astral.sh/ruff/) - linter and formatter.

The roll sequences are produced by our own engine, byte-validated against
[bc.godfat.org](https://bc.godfat.org/); the gacha schedule comes from godfat's
open event data and the unit catalogue from the game's own data files.

## Inspiration

Reference projects surveyed for features to borrow. Functionality focus, not
visual design.

### Planners / multipath solvers
- [ubercarry.me](https://ubercarry.me/) & [catcpu.com](https://catcpu.com/) - by [thasmin/bcplanner](https://github.com/thasmin/bcplanner). Roll Planner (next 100 rolls, A/B tracks, rarity colors, guaranteed-Uber, duplicate detection), Uber Planner, Cat Dictionary (800+ units), Tier Lists. Main inspiration.
- [xirba13/Batte-Cats-Gacha-Path-Finder](https://github.com/xirba13/Batte-Cats-Gacha-Path-Finder) - optimal multipath roll calculator. Per-banner action caps, bounded search, plain-text step output.

### Seed trackers
- [bc.godfat.org](https://bc.godfat.org/) - the canonical seed tracker; our roll engine is byte-validated against it.
- [ampuri.github.io](https://ampuri.github.io/) - collected Battle Cats tools, including the modern React [bc-normal-seed-tracking](https://ampuri.github.io/bc-normal-seed-tracking/).
- [theusaf/battlecats-seed-tracker-util](https://github.com/theusaf/battlecats-seed-tracker-util) / [Greasy Fork script](https://greasyfork.org/en/scripts/480239-bc-seed-tracker-util) - godfat overlay showing paths to wanted cats.
- [battlecatsinfo.github.io](https://battlecatsinfo.github.io/) - a large all-in-one toolset: seed tracker, gacha odds, unit database, stat and talent/treasure calculators, and an event schedule.
- [thanksfeanor.pythonanywhere.com](https://thanksfeanor.pythonanywhere.com/) - a hosted collection of Battle Cats utilities.

### Stats, calculators & databases
- [battlecatsstats.com](https://battlecatsstats.com/) - true-damage calculator, talents/abilities, range DPS graphs, unit comparison.
- [battlecats-calc.com](https://battlecats-calc.com/) - a "Manage Cats" checkbox page feeding a "My Cats" view (like our Collection).
- [matthewmarks stat calculator](https://production.matthewmarks.com/battle-cats-stat-calculator/) - stat breakdowns and tier list.
- [Miraheze Cat Stats Tool](https://battlecats.miraheze.org/wiki/Cat_Stats_Tool) - view / compare / filter cats by stats, with True/Ultra-form and talent toggles.
- [battlecatsdata.com](https://www.battlecatsdata.com/) - version-current English enemy database with HP, DPS, range, traits, abilities, immunities, filters, and individual enemy pages.

### Tier lists
- [battlecatstierlist.com](https://www.battlecatstierlist.com/) - tier lists per banner, DPS-to-range, DPS graphs, matchup charts, Top 10, statistics; links to the Miraheze wiki.

### Event schedules & upcoming banners
- [Upcoming events (community doc)](https://docs.google.com/document/d/1ENv1edzJAcsmk3gjLpvhqVFxoQ4Lpde1K5dRTNxH8sA/edit) - a maintained schedule of upcoming gacha and events.
- [mygamatoto.com](https://mygamatoto.com/) - account / collection manager with an event calendar.

### Reference wikis & assets
- [The Battle Cats Wiki (Miraheze)](https://battlecats.miraheze.org/) - primary wiki the tier-list and stat tools link to.
- [Uber & collab art archive (Google Drive)](https://drive.google.com/drive/folders/12Iu_dv8AZWfU3ekRoA_km0dbJA9klNdC) - community gallery of every Uber, collabs included.

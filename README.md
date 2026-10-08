# Neko Optimizer

[![CI](https://github.com/IliyanGavrilov/NekoOptimizer/actions/workflows/ci.yml/badge.svg)](https://github.com/IliyanGavrilov/NekoOptimizer/actions/workflows/ci.yml)
[![CodeQL](https://github.com/IliyanGavrilov/NekoOptimizer/actions/workflows/codeql.yml/badge.svg)](https://github.com/IliyanGavrilov/NekoOptimizer/actions/workflows/codeql.yml)
[![Security](https://github.com/IliyanGavrilov/NekoOptimizer/actions/workflows/security.yml/badge.svg)](https://github.com/IliyanGavrilov/NekoOptimizer/actions/workflows/security.yml)
![Python 3.14+](https://img.shields.io/badge/python-3.14%2B-blue)
![Django 6.0](https://img.shields.io/badge/Django-6.0-092E20)

**Live: [neko-optimizer.onrender.com](https://neko-optimizer.onrender.com)** - free to use, no sign-up needed (an account just keeps your collection across devices). The free server sleeps when idle, so the first visit can take ~50 seconds.

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
| `planner/` | The Django app - views, forms, models, `services.py` (the roll-to-plan glue), templates, and the data-fetch/import management commands. |
| `nekosite/` | Django project configuration (settings, URLs, WSGI/ASGI). |
| `manage.py` | Django entry point. |

## Prerequisites

- **[Python](https://www.python.org/) 3.14+**
- **[Git](https://git-scm.com/)** (to clone)
- No database server or build toolchain - the app uses file-based
  [SQLite](https://www.sqlite.org/), and Python is interpreted (there is no
  compile step).
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

# 3. Install dependencies
pip install -r requirements.txt

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

## How to use

1. Open **http://127.0.0.1:8000/**.
2. Enter your current shared **seed**.
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
   wishlist marks and filter by targets, abilities, combos, and talents.
8. The **Materials** page (`/materials/`) tracks what to grind: pick cats to
   evolve (catfruit / stones / gems + XP totals), talents to buy (NP totals),
   and cannons to develop (per-part level ranges with material / engineer /
   build-time totals).
9. The **EN / JP / TW / KR** switch in the header picks the game version. Each
   version has its own catalogue, schedule, pools and localized names, and keeps
   its own seed and collection - the roll mechanics are identical across all four.

## Tech stack

- [Python 3.14](https://www.python.org/) - `dataclasses`, `heapq`, `csv`, `enum`
  from the standard library carry the core engine.
- [Django](https://www.djangoproject.com/) - web framework (views, ORM, templates,
  management commands).
- [SQLite](https://www.sqlite.org/) - the local datastore for the catalogue and
  ownership.
- [pytest](https://docs.pytest.org/) + [pytest-django](https://pytest-django.readthedocs.io/) -
  test suite.
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

### Tier lists
- [battlecatstierlist.com](https://www.battlecatstierlist.com/) - tier lists per banner, DPS-to-range, DPS graphs, matchup charts, Top 10, statistics; links to the Miraheze wiki.

### Event schedules & upcoming banners
- [Upcoming events (community doc)](https://docs.google.com/document/d/1ENv1edzJAcsmk3gjLpvhqVFxoQ4Lpde1K5dRTNxH8sA/edit) - a maintained schedule of upcoming gacha and events.
- [mygamatoto.com](https://mygamatoto.com/) - account / collection manager with an event calendar.

### Reference wikis & assets
- [The Battle Cats Wiki (Miraheze)](https://battlecats.miraheze.org/) - primary wiki the tier-list and stat tools link to.
- [Uber & collab art archive (Google Drive)](https://drive.google.com/drive/folders/12Iu_dv8AZWfU3ekRoA_km0dbJA9klNdC) - community gallery of every Uber, collabs included.

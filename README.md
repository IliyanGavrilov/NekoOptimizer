# Neko Optimizer

A planning tool for *The Battle Cats* gacha. Given a target set of cats and a
budget of tickets and catfood, it computes **where and when to pull, in which
order, for the lowest resource cost**.

Battle Cats drives every banner from a single shared XOR-shift PRNG seed, so the
entire future pull sequence is deterministic once the seed is known. Neko
Optimizer treats the pulls as a state graph and searches it (A\* / beam) for the
cheapest path that collects the wishlist.

## Layout

| Path | Purpose |
|------|---------|
| `neko/` | Pure-Python core - RNG, models, graph builder, search, subset solver, scraper, SQLite. Django-independent and unit-testable in isolation. |
| `nekosite/` | Django project (settings, urls, wsgi/asgi). The web UI app is added later. |
| `manage.py` | Django entry point. |

## Setup (from a clean clone)

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/macOS
pip install -r requirements.txt
```

## Common commands

```bash
pytest                          # run the test suite
python manage.py runserver      # run the Django dev server
python manage.py migrate        # apply database migrations
```

## Tech stack

Django · aiohttp + asyncio · BeautifulSoup4 · heapq · sqlite3 · dataclasses ·
pytest. Data source for pull sequences: [bc.godfat.org](https://bc.godfat.org).

## Inspiration

Reference projects surveyed for features to borrow. Functionality focus, not visual design.

### Planners / multipath solvers
- [ubercarry.me](https://ubercarry.me/) & [catcpu.com](https://catcpu.com/) — by [thasmin/bcplanner](https://github.com/thasmin/bcplanner). Roll Planner (next 100 rolls, A/B tracks, rarity colors, guaranteed-Uber, duplicate detection), Uber Planner, Cat Dictionary (800+ units), Tier Lists. Main inspiration.
- [xirba13/Batte-Cats-Gacha-Path-Finder](https://github.com/xirba13/Batte-Cats-Gacha-Path-Finder) — optimal multipath roll calculator. `BANNER_LIMITS` (per-banner action caps), search caps `MAX_SEARCH_STEPS`/`MAX_SOLUTIONS`, plain-text step output.
- [bc.godfat.org](https://bc.godfat.org/) — the canonical seed tracker (our parser targets it).
- [ampuri.github.io/bc-normal-seed-tracking](https://ampuri.github.io/bc-normal-seed-tracking/) — modern React normal-seed tracker.
- [theusaf/battlecats-seed-tracker-util](https://github.com/theusaf/battlecats-seed-tracker-util) / [Greasy Fork script](https://greasyfork.org/en/scripts/480239-bc-seed-tracker-util) — godfat overlay showing paths to wanted cats.

### Tier lists / stats / database
- [battlecatstierlist.com](https://www.battlecatstierlist.com/) — tier lists per banner, DPS-to-range, DPS graphs, matchup charts, Top 10, statistics; links to Miraheze wiki.
- [battlecatsstats.com](https://battlecatsstats.com/) — true-damage calculator, talents/abilities, range DPS graphs, unit comparison.
- [battlecats-calc.com](https://battlecats-calc.com/) — "Manage Cats" checkbox page -> "My Cats" view (like our Collection).
- [matthewmarks stat calculator](https://production.matthewmarks.com/battle-cats-stat-calculator/) — stat breakdowns + tier list.
- [Miraheze Cat Stats Tool](https://battlecats.miraheze.org/wiki/Cat_Stats_Tool) — view/compare/filter cats by stats, True/Ultra-form + talent toggles.

### Reference wikis
- [The Battle Cats Wiki (Miraheze)](https://battlecats.miraheze.org/) — primary wiki the tier-list site links to.

### Feature ideas to borrow
- Per-banner action limits as an optimizer constraint (xirba13 `BANNER_LIMITS`).
- Roll-prediction viewer: upcoming A/B rolls for a seed, alongside the plan.
- Cat dictionary page (images, rarity filter, search; wiki links).
- Shareable plan permalink; seed-finder (derive seed from a roll sequence).
- Track-switch (A/B) awareness in plans; duplicate detection.

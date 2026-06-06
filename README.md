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

## Roadmap

Built in dependency order, most-testable core first. Tests are written
alongside each module, not deferred.

- [x] **0. Scaffold** - Django project, `neko` core package, deps, tooling.
- [ ] **1. RNG core** - XOR-shift PRNG, sequence advance, track-switch logic.
- [ ] **2. Data models** - `Banner`, `Pull`, `State`, `Path` dataclasses.
- [ ] **3. Graph builder** - pull graph from RNG output; duplicate-rare track switch.
- [ ] **4. A\* search** - `next_wanted` lookup table, admissible heuristic, `heapq`.
- [ ] **5. Beam search** - top-K mode; optional upper-bound prune pass for A\*.
- [ ] **6. Subset solver** - optimal plan per target subset, sorted by cost.
- [ ] **7. Scraper + cache** - `aiohttp`/`asyncio` fetch, `BeautifulSoup` parse, JSON cache.
- [ ] **8. SQLite collection** - cats, wishlist, seed persistence.
- [ ] **9. Django layer** - views, forms, templates, ORM.
- [ ] **10. Frontend** - plain HTML/CSS/vanilla JS.

## Tech stack

Django · aiohttp + asyncio · BeautifulSoup4 · heapq · sqlite3 · dataclasses ·
pytest. Data source for pull sequences: [bc.godfat.org](https://bc.godfat.org).

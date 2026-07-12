---
name: verify
description: How to launch and drive Neko Optimizer (Django) to verify changes end-to-end.
---

# Verifying Neko Optimizer

Django app; server surface + vanilla-JS pages. NOTE: `.claude/` stays untracked — never commit it.

## Launch

```powershell
python manage.py runserver 8765 --noreload   # background; 8765 avoids the user's own 8000 server
```

`--noreload` means RESTART after Python OR template edits (Django caches templates even in DEBUG).

## Drive

- Server-rendered pages + JSON endpoints: plain HTTP with `urllib` + CookieJar works.
  CSRF: GET the page, regex `name="csrfmiddlewaretoken" value="..."`, send it back as
  the `X-CSRFToken` header on POSTs (cookies must ride along).
- Console prints of banner names need `$env:PYTHONIOENCODING='utf-8'` (names contain ★).
- Golden fixtures for realistic flows: seed `1893568593` on run `2026-06-26_1052`
  (Trixi); `neko.seek.play(seed, banner, n)` generates real pull sequences.
- JS behavior MUST be driven in a real browser — HTTP-contract checks once missed a
  ReferenceError that killed a page silently. Use Playwright with the system Edge
  (`pip install playwright`, no browser download):
  `p.chromium.launch(channel="msedge", headless=True)`, collect `page.on("pageerror")`
  and assert it stays empty, screenshot for the eyeball pass. Don't iframe pages from
  a static harness — X-Frame-Options blocks it.

## Key surfaces

- `/` planner (accepts `?seed=&last=` permalinks), `/tracks/` POST fragment,
  `/seek/` seed finder (`/seek/pool/`, `/seek/start/` POST, `/seek/status/?job=` poll,
  a real search takes ~12s), `/collection/`, `/tiers/`.
- `/normal/` Normal Capsules tracker (its OWN seed, `?seed=&last=` permalinks; seed and
  machine picks live in localStorage, not the DB), `/normal/tracks/` POST fragment,
  `/normal/seek/start/` POST (polls the shared `/seek/status/`). Golden normal seed
  `1515525936` matches `neko/tests/fixtures/normal_golden_*.json` (scraped off ampuri's
  tracker; `neko.normal.play` generates real pull sequences). NOTE: the in-app Browser
  pane's screenshots/a11y reads time out on the 100-row table — use Playwright for the
  eyeball pass.

// ---- Normal Capsules: its own seed, its own tracks, its own finder -----------
// The normal-side gacha shares nothing with the rare seed the planner follows, so
// this page keeps its seed in localStorage (?seed= permalinks override it), renders
// the A/B tracks from the server, and runs the normal seed finder against the same
// polling endpoints the rare finder uses.
const normalForm = document.getElementById("normalForm");
if (normalForm) {
  const token = normalForm.querySelector("[name=csrfmiddlewaretoken]").value;
  const seedEl = document.getElementById("normalSeed");
  const updateBtn = document.getElementById("normalUpdate");
  const countEl = document.getElementById("normalCount");
  const machineEls = [...normalForm.querySelectorAll(".machine-toggle input")];
  const hint = document.getElementById("normalHint");
  const tracksHost = document.getElementById("normalTracks");

  const esc = (text) => text.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);

  // ---- Seed + dupe memory, persisted like the planner's -----------------------
  // ?seed= (a share link or a finder result) wins over the stored seed; the dupe
  // memory rides along as ?last= / storage, since the remembered item can dupe 1A.
  let stored = {};
  try {
    stored = JSON.parse(localStorage.getItem("nekoNormal") || "{}");
  } catch {
    stored = {};
  }
  const save = () => {
    try {
      localStorage.setItem("nekoNormal", JSON.stringify(stored));
    } catch {
      /* private mode: the page still works, it just forgets on reload */
    }
  };

  const linkParams = new URLSearchParams(location.search);
  if (linkParams.has("seed")) {
    stored.seed = linkParams.get("seed");
    stored.last = linkParams.get("last") || "";
    save();
  }
  if (stored.machines) {
    for (const el of machineEls) el.checked = stored.machines.includes(el.value);
  }
  seedEl.value = stored.seed || "";

  // Keep the address bar shareable: the current seed (+ dupe memory) as you move.
  const syncLink = () => {
    const p = new URLSearchParams();
    if (seedEl.value.trim()) p.set("seed", seedEl.value.trim());
    if (stored.last) p.set("last", stored.last);
    const query = p.toString();
    history.replaceState(null, "", query ? `?${query}` : location.pathname);
  };

  const fetchTracks = async () => {
    const seed = seedEl.value.trim();
    const machines = machineEls.filter((el) => el.checked).map((el) => el.value);
    stored.machines = machines;
    save();
    syncLink();
    if (!/^\d+$/.test(seed)) {
      hint.hidden = false;
      tracksHost.innerHTML = "";
      return;
    }
    hint.hidden = true;

    const body = new URLSearchParams({
      seed,
      track_length: countEl.value,
      last_item: stored.last || "",
      csrfmiddlewaretoken: token,
    });
    for (const key of machines) body.append("banners", key);
    let resp;
    try {
      resp = await fetch(normalForm.dataset.tracksUrl, {
        method: "POST",
        headers: { "X-CSRFToken": token },
        body,
      });
    } catch {
      resp = null;
    }
    tracksHost.innerHTML =
      resp && resp.ok
        ? await resp.text()
        : `<p class="field-error">Couldn't load the tracks - is the server still running?</p>`;
  };

  const setSeed = (seed, lastItem) => {
    stored.seed = String(seed);
    stored.last = lastItem || "";
    save();
    seedEl.value = stored.seed;
    fetchTracks();
  };

  updateBtn.addEventListener("click", () => setSeed(seedEl.value.trim(), ""));
  seedEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      setSeed(seedEl.value.trim(), "");
    }
  });
  countEl.addEventListener("change", fetchTracks);
  for (const el of machineEls) el.addEventListener("change", fetchTracks);

  // A cell's dice: "I rolled this" - jump to just after it, remembering what it
  // gave (the next view's first cell can dupe it).
  tracksHost.addEventListener("click", (e) => {
    const btn = e.target.closest(".reseed");
    if (btn) setSeed(btn.dataset.seed, btn.dataset.item || "");
  });

  fetchTracks();

  // ---- The normal seed finder: static pools, the shared polling flow ----------
  const pools = JSON.parse(document.getElementById("normalPools").textContent);
  const nseekForm = document.getElementById("nseekForm");
  const bannerSel = document.getElementById("nseekBanner");
  const rollsEl = document.getElementById("nseekRolls");
  const addRow = document.getElementById("nseekAddRow");
  const goBtn = document.getElementById("nseekGo");
  const errorEl = document.getElementById("nseekError");
  const progressWrap = document.getElementById("nseekProgress");
  const bar = document.getElementById("nseekBar");
  const progressText = document.getElementById("nseekProgressText");
  const results = document.getElementById("nseekResults");
  const MIN = Number(nseekForm.dataset.minRolls);
  const MAX = Number(nseekForm.dataset.maxRolls);
  const START_ROWS = 10;

  const setError = (msg) => (errorEl.textContent = msg || "");

  const optionsHtml = () => {
    const pool = pools[bannerSel.value];
    return (
      `<input type="text" class="pick-search" placeholder="Search items&hellip;"` +
      ` autocomplete="off" autocorrect="off" autocapitalize="off" spellcheck="false">` +
      pool.groups
        .map(
          (g) =>
            `<div class="combo-group">${esc(g.label)}</div>` +
            g.options
              .map(
                (o) =>
                  `<button type="button" class="combo-row" data-value="${o.value}"` +
                  ` data-search="${esc(o.label.toLowerCase())}">` +
                  `<span class="combo-cat">${esc(o.label)}</span></button>`
              )
              .join("")
        )
        .join("") + `<p class="combo-empty" hidden>No items match.</p>`
    );
  };

  // ---- Pull pickers: a dropdown per pull, with a search box inside (seek.js's) --
  const closePanels = () => {
    for (const open of rollsEl.querySelectorAll(".combo-list:not([hidden])")) {
      open.hidden = true;
    }
  };
  document.addEventListener("pointerdown", (e) => {
    if (!e.target.closest(".roll-pick")) closePanels();
  });

  const appendRow = () => {
    const li = document.createElement("li");
    li.innerHTML = `<div class="roll-pick">
      <button type="button" class="roll-trigger">
        <span class="roll-label">Pick an item&hellip;</span><span class="roll-chevron">&#9662;</span>
      </button>
      <input type="hidden" class="seek-roll">
      <div class="combo-list" hidden>${optionsHtml()}</div>
    </div>`;
    rollsEl.append(li);

    const root = li.firstElementChild;
    const trigger = root.querySelector(".roll-trigger");
    const label = root.querySelector(".roll-label");
    const hidden = root.querySelector(".seek-roll");
    const panel = root.querySelector(".combo-list");
    const search = panel.querySelector(".pick-search");
    const empty = panel.querySelector(".combo-empty");

    const filter = () => {
      const query = search.value.trim().toLowerCase();
      let group = null;
      let any = false;
      for (const el of panel.children) {
        if (el.classList.contains("combo-group")) {
          group = el;
          el.hidden = true;
        } else if (el.classList.contains("combo-row")) {
          const show = !query || el.dataset.search.includes(query);
          el.hidden = !show;
          if (show) {
            any = true;
            if (group) group.hidden = false;
          }
        }
      }
      empty.hidden = any;
    };

    const pick = (row) => {
      hidden.value = row.dataset.value;
      label.innerHTML = row.innerHTML;
      label.classList.remove("roll-placeholder");
      panel.hidden = true;
      const rows = [...rollsEl.querySelectorAll(".roll-pick")];
      const next = rows.find((r) => !r.querySelector(".seek-roll").value);
      if (next) next.querySelector(".roll-trigger").focus();
    };

    label.classList.add("roll-placeholder");
    trigger.addEventListener("click", () => {
      const wasOpen = !panel.hidden;
      closePanels();
      if (wasOpen) return;
      search.value = "";
      filter();
      panel.hidden = false;
      search.focus();
    });
    search.addEventListener("input", filter);
    search.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        panel.hidden = true;
        trigger.focus();
      }
      if (e.key === "Enter") {
        e.preventDefault();
        const first = panel.querySelector(".combo-row:not([hidden])");
        if (first) pick(first);
      }
    });
    panel.addEventListener("pointerdown", (e) => {
      const row = e.target.closest(".combo-row");
      if (row) {
        e.preventDefault();
        pick(row);
      }
    });
  };

  const resetRows = () => {
    rollsEl.innerHTML = "";
    for (let i = 0; i < START_ROWS; i++) appendRow();
    addRow.hidden = false;
  };
  bannerSel.addEventListener("change", resetRows);
  resetRows();

  addRow.addEventListener("click", () => {
    if (rollsEl.children.length < MAX) appendRow();
    addRow.hidden = rollsEl.children.length >= MAX;
  });

  // ---- The search itself: start the job, poll until it's done -----------------
  const PASS_LABELS = [
    "Searching the seed space…",
    "No clean match — retrying your first pull as a dupe reroll (below the shadow slot)…",
    "No clean match — retrying your first pull as a dupe reroll (at or above the shadow slot)…",
  ];

  const matchCard = (m, lastItem) => `<div class="seek-match">
      <div class="seek-seed">Your normal seed is now <strong>${m.seed_after}</strong></div>
      <button type="button" class="seek-open seek-use" data-seed="${m.seed_after}"
        data-item="${esc(lastItem || "")}">Show my upcoming rolls &rarr;</button>
      <p class="muted">Seed before those pulls: ${m.seed_before}${
        m.run
          ? " &middot; your first entered pull arrived as a dupe reroll of the roll just before it"
          : ""
      }</p>
    </div>`;

  const render = (data) => {
    progressWrap.hidden = true;
    goBtn.disabled = false;
    results.hidden = false;

    if (data.error) {
      results.innerHTML = `<p class="field-error">Search failed: ${esc(data.error)}</p>`;
      return;
    }
    if (!data.matches.length) {
      results.innerHTML = `<p class="seek-none">No seed deals exactly those pulls. Double-check
        the items and their order, the machine (plain Normal vs Normal+ with Superfeline
        matters), and that the pulls were consecutive.</p>`;
      return;
    }

    let notes = "";
    if (data.truncated) {
      notes = `<p class="field-warning">Far too many seeds match - this window is too
        short to pin yours down. Add a few more rolls and search again; only the first
        ${data.matches.length} are shown.</p>`;
    } else if (data.matches.length > 1) {
      notes = `<p class="field-warning">${data.matches.length} seeds match. Roll a few
        more items, add them, and search again to narrow it down.</p>`;
    }
    results.innerHTML =
      notes + data.matches.map((m) => matchCard(m, data.last_cat)).join("");
  };

  results.addEventListener("click", (e) => {
    const btn = e.target.closest(".seek-use");
    if (!btn) return;
    setSeed(btn.dataset.seed, btn.dataset.item || "");
    document.getElementById("normalFinder").open = false;
    tracksHost.scrollIntoView({ behavior: "smooth", block: "start" });
  });

  const poll = (job) => {
    const tick = async () => {
      let resp;
      try {
        resp = await fetch(`${nseekForm.dataset.statusUrl}?job=${job}`);
      } catch {
        resp = null;
      }
      if (!resp || !resp.ok) {
        progressWrap.hidden = true;
        goBtn.disabled = false;
        setError("Lost the search - is the server still running? Try again.");
        return;
      }
      const data = await resp.json();
      if (data.done) {
        render(data);
        return;
      }
      bar.value = data.progress;
      progressText.textContent = `${PASS_LABELS[data.run]} ${Math.round(data.progress * 100)}%`;
      setTimeout(tick, 500);
    };
    tick();
  };

  nseekForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    setError("");

    const values = [...rollsEl.querySelectorAll(".seek-roll")].map((h) => h.value);
    const last = values.length - 1 - [...values].reverse().findIndex(Boolean);
    const filled = values.filter(Boolean);
    if (filled.length && values.slice(0, last + 1).some((v) => !v)) {
      setError("Fill your pulls in order, top to bottom - no gaps.");
      return;
    }
    if (filled.length < MIN) {
      setError(`Enter at least ${MIN} pulls (8-12 works best).`);
      return;
    }

    const body = new URLSearchParams({ banner: bannerSel.value, csrfmiddlewaretoken: token });
    filled.forEach((v) => body.append("rolls", v));
    const resp = await fetch(nseekForm.dataset.startUrl, {
      method: "POST",
      headers: { "X-CSRFToken": token },
      body,
    });
    if (!resp.ok) {
      setError(await resp.text());
      return;
    }

    results.hidden = true;
    goBtn.disabled = true;
    bar.value = 0;
    progressText.textContent = PASS_LABELS[0];
    progressWrap.hidden = false;
    poll((await resp.json()).job);
  });
}

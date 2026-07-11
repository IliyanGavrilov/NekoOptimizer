// ---- Normal Capsules: its own seed, its own tracks, finder and path planner --
// The normal-side gacha shares nothing with the rare seed the planner follows, so
// this page keeps its seed in localStorage (?seed= permalinks override it), renders
// the A/B tracks from the server, and runs the normal seed finder against the same
// polling endpoints the rare finder uses. Tracks reload live as the seed, machines
// or roll count change, exactly like the planner (the seed field is a number input,
// so app.js's drag-to-scrub picks it up too).
const normalForm = document.getElementById("normalForm");
if (normalForm) {
  const token = normalForm.querySelector("[name=csrfmiddlewaretoken]").value;
  const seedEl = document.getElementById("normalSeed");
  const countEl = document.getElementById("normalCount");
  // The plain capsule is one column with a profile fact attached: once Superfeline
  // joins your pool it never leaves, so "which normal machine" isn't a choice -
  // the toggle records which pool YOUR save rolls, and everything (columns, the
  // finder, the planner) reads it.
  const normalToggle = document.getElementById("machineNormal");
  const superfeline = document.getElementById("superfeline");
  const machineEls = [...normalForm.querySelectorAll(".machine-toggle input[value]")];
  const hint = document.getElementById("normalHint");
  const tracksHost = document.getElementById("normalTracks");

  const normalKey = () => (superfeline.checked ? "np" : "n");

  const esc = (text) => text.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);

  // ---- Seed + dupe memory, persisted like the planner's -----------------------
  // A share link (?seed=&last=&m=) wins over the stored state; the dupe memory
  // rides along since the remembered item can dupe 1A, and the machine set rides
  // so the link shows the same columns.
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
  }
  if (linkParams.has("m")) stored.machines = linkParams.get("m").split(",").filter(Boolean);
  if (linkParams.has("seed") || linkParams.has("m")) save();
  if (stored.machines) {
    for (const el of machineEls) el.checked = stored.machines.includes(el.value);
    normalToggle.checked = stored.machines.includes("n") || stored.machines.includes("np");
    // The machine list carries which capsule flavor this save has (a link shares
    // it too); when the normal column is off, fall back to the remembered flag.
    if (normalToggle.checked) stored.superfeline = stored.machines.includes("np");
  }
  if (stored.superfeline !== undefined) superfeline.checked = stored.superfeline;
  seedEl.value = stored.seed || "";

  const checkedMachines = () => {
    const keys = normalToggle.checked ? [normalKey()] : [];
    return keys.concat(machineEls.filter((el) => el.checked).map((el) => el.value));
  };

  // Keep the address bar shareable: the current seed, dupe memory and machines.
  const syncLink = () => {
    const p = new URLSearchParams();
    if (seedEl.value.trim()) p.set("seed", seedEl.value.trim());
    if (stored.last) p.set("last", stored.last);
    const machines = checkedMachines();
    if (machines.length) p.set("m", machines.join(","));
    const query = p.toString();
    history.replaceState(null, "", query ? `?${query}` : location.pathname);
  };

  const fetchTracks = async () => {
    const seed = seedEl.value.trim();
    const machines = checkedMachines();
    stored.machines = machines;
    stored.superfeline = superfeline.checked;
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

  // ---- Live reload: the seed field (typed or scrubbed), machines, roll count --
  let trackTimer;
  const scheduleTracks = () => {
    clearTimeout(trackTimer);
    trackTimer = setTimeout(fetchTracks, 400);
  };

  const setSeed = (seed, lastItem) => {
    stored.seed = String(seed);
    stored.last = lastItem || "";
    save();
    seedEl.value = stored.seed;
    fetchTracks();
  };

  seedEl.addEventListener("input", () => {
    // A hand-typed (or scrubbed) seed is a fresh arrival: no remembered pull.
    stored.seed = seedEl.value.trim();
    stored.last = "";
    save();
    scheduleTracks();
  });
  countEl.addEventListener("input", scheduleTracks);
  for (const el of machineEls) el.addEventListener("change", fetchTracks);
  normalToggle.addEventListener("change", fetchTracks);
  superfeline.addEventListener("change", () => {
    fetchTracks();
    syncFinderPool(); // the finder searches the flavor's pool - rebuild its pickers
  });

  // A cell's dice: "I rolled this" - jump to just after it, remembering what it
  // gave (the next view's first cell can dupe it).
  tracksHost.addEventListener("click", (e) => {
    const btn = e.target.closest(".reseed");
    if (btn) setSeed(btn.dataset.seed, btn.dataset.item || "");
    const apply = e.target.closest(".plan-apply");
    if (apply) setSeed(apply.dataset.seed, apply.dataset.item || "");
  });

  fetchTracks();

  // ---- The path planner: budgets in, lit path out ------------------------------
  const planPanel = document.getElementById("normalPlanPanel");
  const planGo = document.getElementById("normalPlanGo");
  const planError = document.getElementById("normalPlanError");
  const targetSel = document.getElementById("normalTarget");
  const budgetEls = [...planPanel.querySelectorAll(".plan-budget")];

  // First open: seed the stashes with something sensible - normal tickets are
  // the abundant currency, the lucky kinds precious - so "Find a path" works out
  // of the box.
  planPanel.addEventListener("toggle", () => {
    if (!planPanel.open || budgetEls.some((el) => Number(el.value) > 0)) return;
    const machines = checkedMachines();
    for (const el of budgetEls) {
      if (el.dataset.kind === "normal") {
        el.value = machines.some((k) => k !== "lt" && k !== "ltg") ? 100 : 0;
      } else {
        el.value = machines.includes(el.dataset.kind === "lucky" ? "lt" : "ltg") ? 10 : 0;
      }
    }
  });

  planGo.addEventListener("click", async () => {
    planError.textContent = "";
    const seed = seedEl.value.trim();
    if (!/^\d+$/.test(seed)) {
      planError.textContent = "Enter (or find) your normal seed first.";
      return;
    }
    const tickets = {};
    for (const el of budgetEls) {
      const count = Number(el.value);
      if (count > 0) tickets[el.dataset.kind] = count;
    }
    if (!Object.keys(tickets).length) {
      planError.textContent = "Enter at least one ticket stash.";
      return;
    }

    planGo.disabled = true;
    planGo.textContent = "Searching…";
    const body = new URLSearchParams({
      seed,
      tickets: JSON.stringify(tickets),
      target: targetSel.value,
      track_length: countEl.value,
      last_item: stored.last || "",
      csrfmiddlewaretoken: token,
    });
    for (const key of checkedMachines()) body.append("banners", key);
    let resp;
    try {
      resp = await fetch(normalForm.dataset.planUrl, {
        method: "POST",
        headers: { "X-CSRFToken": token },
        body,
      });
    } catch {
      resp = null;
    }
    planGo.disabled = false;
    planGo.textContent = "Find a path";
    if (!resp || !resp.ok) {
      planError.textContent = resp ? await resp.text() : "Lost the server - try again.";
      return;
    }
    tracksHost.innerHTML = await resp.text();
    tracksHost.scrollIntoView({ behavior: "smooth", block: "start" });
  });

  // ---- The normal seed finder: static pools, the shared polling flow ----------
  const pools = JSON.parse(document.getElementById("normalPools").textContent);
  const nseekForm = document.getElementById("nseekForm");
  const poolLabel = document.getElementById("nseekPool");
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
    const pool = pools[normalKey()];
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
  const syncFinderPool = () => {
    const pool = pools[normalKey()];
    poolLabel.textContent = pool.name + " (" + pool.note + ")";
    resetRows();
  };
  syncFinderPool();

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

  const matchCard = (m, lastItem, machine) => `<div class="seek-match">
      <div class="seek-seed">Your normal seed is now <strong>${m.seed_after}</strong></div>
      <button type="button" class="seek-use" data-seed="${m.seed_after}"
        data-item="${esc(lastItem || "")}" data-machine="${esc(machine)}">Show my upcoming rolls &rarr;</button>
      <p class="muted">Seed before those pulls: ${m.seed_before} &middot;
        <button type="button" class="seek-use" data-seed="${m.seed_before}"
          data-machine="${esc(machine)}">replay them</button>${
        m.run
          ? " &middot; your first entered pull arrived as a dupe reroll, so the replay shows it as its cell's branch value"
          : ""
      }</p>
    </div>`;

  const render = (data, machine) => {
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
      notes + data.matches.map((m) => matchCard(m, data.last_cat, machine)).join("");
  };

  // A result button applies its seed right here: the sought machine joins the
  // shown columns (so what you just rolled is on screen), the finder folds away.
  results.addEventListener("click", (e) => {
    const btn = e.target.closest(".seek-use");
    if (!btn) return;
    normalToggle.checked = true; // the sought pool is always the plain capsule
    superfeline.checked = btn.dataset.machine === "np";
    setSeed(btn.dataset.seed, btn.dataset.item || "");
    document.getElementById("normalFinder").open = false;
    tracksHost.scrollIntoView({ behavior: "smooth", block: "start" });
  });

  const poll = (job, machine) => {
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
        render(data, machine);
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

    const machine = normalKey();
    const body = new URLSearchParams({ banner: machine, csrfmiddlewaretoken: token });
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
    poll((await resp.json()).job, machine);
  });
}

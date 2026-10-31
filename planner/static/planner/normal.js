// ---- Normal Capsules: its own seed, its own tracks, finder and path planner --
// The normal-side gacha shares nothing with the rare seed the planner follows, so
// this page keeps a seed of its own on your profile (?seed= permalinks override it), renders
// the A/B tracks from the server, and runs the normal seed finder through the same
// local sieve the rare finder uses (seekrun.js). Tracks reload live as the seed, machines
// or roll count change, exactly like the planner (the seed field is a number input,
// so app.js's drag-to-scrub picks it up too).
const normalForm = document.getElementById("normalForm");
if (normalForm) {
  // The machines' tables and the path planner run in the page's own engine (neko.wasm,
  // engine.js), a worker each so a long plan never holds up the table.
  const runTables = nekoEngine(normalForm.dataset.wasmUrl, normalForm.dataset.engineWorkerUrl);
  const runPlans = nekoEngine(normalForm.dataset.wasmUrl, normalForm.dataset.engineWorkerUrl);
  const token = normalForm.querySelector("[name=csrfmiddlewaretoken]").value;
  const seedEl = document.getElementById("normalSeed");
  const countEl = document.getElementById("normalCount");
  // The plain capsule comes in two flavors and a save rolls exactly one: once
  // Superfeline joins your pool it never leaves. So Normal and Normal+ are exclusive
  // picks, and the last one picked is the pool the finder searches.
  const machineEls = [...normalForm.querySelectorAll(".machine-toggle input[value]")];
  const flavorEls = machineEls.filter((el) => el.value === "n" || el.value === "np");
  const hint = document.getElementById("normalHint");
  const tracksHost = document.getElementById("normalTracks");
  const backToRolls = document.getElementById("normalBackToRolls");
  // The Rolls display controls, the rare planner's verbatim and on its saved picks:
  // names / icons / both and which form, applied to the cat items the pools drop.
  const rollsRegion = document.getElementById("normalRolls");
  const displayEl = document.getElementById("normalDisplay");
  const rollFormEl = document.getElementById("normalRollForm");
  restorePick(displayEl, DISPLAY_KEY);
  restorePick(rollFormEl, FORM_KEY);
  const applyDisplay = () => {
    const form = Number(rollFormEl.value);
    renameForms(rollsRegion, form);
    syncCatDisplay(rollsRegion, displayEl.value, form);
  };

  const normalKey = () => (stored.superfeline === false ? "n" : "np");
  // Tick one flavor (the other drops) and remember it as this save's pool.
  const pickFlavor = (key) => {
    for (const el of flavorEls) el.checked = el.value === key;
    stored.superfeline = key === "np";
  };

  const esc = (text) => text.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);

  // ---- Seed + dupe memory, kept on your profile like the planner's ------------
  // The seed and the item that landed on it (it can dupe 1A) are stored server-side
  // (seedKeeper); this browser keeps only the machine picks. A share link
  // (?seed=&last=&m=) wins over both, and the machine set rides so the link shows
  // the same columns.
  let stored = {};
  try {
    stored = JSON.parse(localStorage.getItem("nekoNormal") || "{}");
  } catch {
    stored = {};
  }
  const save = () => {
    const { seed, last, ...view } = stored;
    try {
      localStorage.setItem("nekoNormal", JSON.stringify(view));
    } catch {
      /* private mode: the page still works, it just forgets on reload */
    }
  };

  // The seed box's "Find it" opens the finder above instead of only scrolling to it.
  normalForm.querySelector(".seed-find").addEventListener("click", () => {
    document.getElementById("normalFinder").open = true;
  });

  const keeper = seedKeeper(normalForm.querySelector(".seed-keep"), {
    current: () => [seedEl.value.trim(), stored.last || ""],
    onRestore: (seed, last) => setSeed(seed, last),
    linkFor: () => location.href,
  });
  // A seed this browser kept from before seeds were stored on the server is the
  // newest one it knows: upload it once (save() never writes it locally again).
  if (stored.seed) keeper.migrate(String(stored.seed), stored.last || "");
  [stored.seed, stored.last] = keeper.own();

  const linkParams = new URLSearchParams(location.search);
  if (linkParams.has("seed")) {
    stored.seed = linkParams.get("seed");
    stored.last = linkParams.get("last") || "";
    keeper.viewing(stored.seed);
  }
  if (linkParams.has("m")) stored.machines = linkParams.get("m").split(",").filter(Boolean);
  if (linkParams.has("seed") || linkParams.has("m")) save();
  if (stored.machines) {
    for (const el of machineEls) el.checked = stored.machines.includes(el.value);
    // The machine list carries which capsule flavor this save has (a link shares
    // it too); with neither column on, the remembered flag stands.
    const shown = flavorEls.filter((el) => el.checked).map((el) => el.value);
    if (shown.length === 1) stored.superfeline = shown[0] === "np";
    else if (shown.length) pickFlavor(normalKey());
  }
  seedEl.value = stored.seed || "0"; // a first visit starts the tracks from seed 0

  const checkedMachines = () => machineEls.filter((el) => el.checked).map((el) => el.value);

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
    const failed = `<p class="field-error">${gettext("Couldn't load the tracks - is the server still running?")}</p>`;
    tracksHost.innerHTML =
      resp && resp.ok ? await runTables(await resp.text()).catch(() => failed) : failed;
    backToRolls.hidden = true;
    applyDisplay();
  };

  // ---- Live reload: the seed field (typed or scrubbed), machines, roll count --
  let trackTimer;
  const scheduleTracks = () => {
    clearTimeout(trackTimer);
    trackTimer = setTimeout(fetchTracks, 400);
  };

  // ``reload`` false keeps what's on screen (an applied plan's steps still need doing).
  const setSeed = (seed, lastItem, reload = true) => {
    stored.seed = String(seed);
    stored.last = lastItem || "";
    save();
    seedEl.value = stored.seed;
    keeper.push(stored.seed, stored.last);
    if (reload) fetchTracks();
    else syncLink();
  };

  seedEl.addEventListener("input", () => {
    // A hand-typed (or scrubbed) seed is a fresh arrival: no remembered pull.
    stored.seed = seedEl.value.trim();
    stored.last = "";
    save();
    keeper.push(stored.seed, stored.last);
    scheduleTracks();
  });
  countEl.addEventListener("input", scheduleTracks);
  displayEl.addEventListener("change", () => {
    localStorage.setItem(DISPLAY_KEY, displayEl.value);
    applyDisplay();
  });
  rollFormEl.addEventListener("change", () => {
    localStorage.setItem(FORM_KEY, rollFormEl.value);
    applyDisplay();
  });
  for (const el of machineEls) {
    el.addEventListener("change", () => {
      if (flavorEls.includes(el) && el.checked) {
        const flavor = normalKey();
        pickFlavor(el.value);
        // The finder searches the flavor's pool - rebuild its pickers on a switch.
        if (normalKey() !== flavor) syncFinderPool();
      }
      fetchTracks();
    });
  }

  // A line's dice: "I rolled this" - jump to just after it, remembering what it
  // gave (the next view's first cell can dupe it).
  tracksHost.addEventListener("click", (e) => {
    const btn = e.target.closest(".reseed");
    if (btn) setSeed(btn.dataset.seed, btn.dataset.item || "");
  });

  fetchTracks();

  // ---- The path planner: budgets in, lit path out ------------------------------
  const planPanel = document.getElementById("normalPlanPanel");
  const planGo = document.getElementById("normalPlanGo");
  const planError = document.getElementById("normalPlanError");
  const targetSel = document.getElementById("normalTarget");
  const movesSel = document.getElementById("normalMoves");
  const budgetEls = [...planPanel.querySelectorAll(".plan-budget")];

  // Your ticket stashes persist in this browser, like the planner's resources.
  const saveBudgets = () => {
    stored.tickets = Object.fromEntries(budgetEls.map((el) => [el.dataset.kind, el.value]));
    save();
  };
  if (stored.tickets) {
    for (const el of budgetEls) el.value = stored.tickets[el.dataset.kind] ?? el.value;
  }
  for (const el of budgetEls) el.addEventListener("input", saveBudgets);
  // Which stash walks the track between targets, remembered like the stashes.
  if (stored.moves) movesSel.value = stored.moves;
  movesSel.addEventListener("change", () => {
    stored.moves = movesSel.value;
    save();
  });

  // First open with nothing saved: seed the stashes with something sensible - normal
  // tickets are the abundant currency, the lucky kinds precious - so "Find a path"
  // works out of the box.
  planPanel.addEventListener("toggle", () => {
    if (!planPanel.open || stored.tickets) return;
    const machines = checkedMachines();
    for (const el of budgetEls) {
      if (el.dataset.kind === "normal") {
        el.value = machines.some((k) => k !== "lt" && k !== "ltg") ? 100 : 0;
      } else {
        el.value = machines.includes(el.dataset.kind === "lucky" ? "lt" : "ltg") ? 10 : 0;
      }
    }
    saveBudgets();
  });

  // "Apply this plan": you rolled it, so its tickets come off your stashes and the
  // seed moves to just after its final pull. The plan stays on screen - its steps
  // still need doing in game.
  tracksHost.addEventListener("click", (e) => {
    const btn = e.target.closest(".plan-apply");
    if (!btn || btn.disabled) return;
    for (const el of budgetEls) {
      const spent = Number(btn.dataset[el.dataset.kind]) || 0;
      el.value = Math.max(0, (Number(el.value) || 0) - spent);
    }
    saveBudgets();
    setSeed(btn.dataset.seed, btn.dataset.item || "", false);
    btn.disabled = true;
    btn.textContent = gettext("Applied ✓");
  });

  // Drop the plan and browse the plain table again, without a page reload.
  backToRolls.addEventListener("click", fetchTracks);

  planGo.addEventListener("click", async () => {
    planError.textContent = "";
    const seed = seedEl.value.trim();
    if (!/^\d+$/.test(seed)) {
      planError.textContent = gettext("Enter (or find) your normal seed first.");
      return;
    }
    const tickets = {};
    for (const el of budgetEls) {
      const count = Number(el.value);
      if (count > 0) tickets[el.dataset.kind] = count;
    }
    if (!Object.keys(tickets).length) {
      planError.textContent = gettext("Enter at least one ticket stash.");
      return;
    }

    planGo.disabled = true;
    planGo.textContent = gettext("Searching…");
    const body = new URLSearchParams({
      seed,
      tickets: JSON.stringify(tickets),
      target: targetSel.value,
      moves: movesSel.value,
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
    planGo.textContent = gettext("Find a path");
    if (!resp || !resp.ok) {
      planError.textContent = resp ? await resp.text() : gettext("Lost the server - try again.");
      return;
    }
    try {
      tracksHost.innerHTML = await runPlans(await resp.text());
    } catch {
      planError.textContent = gettext("Couldn't work out a path - try again.");
      return;
    }
    backToRolls.hidden = false;
    applyDisplay();
    wireFollowAlong(tracksHost); // step list + track walk together (defined in app.js)
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
      `<input type="text" class="pick-search" placeholder="${gettext("Search items…")}"` +
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
        .join("") + `<p class="combo-empty" hidden>${gettext("No items match.")}</p>`
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
        <span class="roll-label">${gettext("Pick an item…")}</span><span class="roll-chevron">&#9662;</span>
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
    poolLabel.textContent = pool.note ? `${pool.name} (${pool.note})` : pool.name;
    resetRows();
  };
  syncFinderPool();

  addRow.addEventListener("click", () => {
    if (rollsEl.children.length < MAX) appendRow();
    addRow.hidden = rollsEl.children.length >= MAX;
  });

  // ---- The search itself: validate on the server, sieve right here -----------------
  const PASS_LABELS = [
    gettext("Checking every possible seed (step 1 of 3)…"),
    gettext("No exact match yet — checking if your first pull was a reroll (step 2 of 3)…"),
    gettext("No exact match yet — checking if your first pull was a reroll (step 3 of 3)…"),
  ];

  const matchCard = (m, lastItem, machine) => `<div class="seek-match">
      <div class="seek-seed">${interpolate(gettext("Your normal seed is now %s"), [`<strong>${m.seed_after}</strong>`])}</div>
      <button type="button" class="seek-use" data-seed="${m.seed_after}"
        data-item="${esc(lastItem || "")}" data-machine="${esc(machine)}">${gettext("Show my upcoming rolls")} &rarr;</button>
      <p class="muted">${interpolate(gettext("Seed before those pulls: %s"), [m.seed_before])} &middot;
        <button type="button" class="seek-use" data-seed="${m.seed_before}"
          data-machine="${esc(machine)}">${gettext("replay them")}</button>${
        m.run
          ? ` &middot; ${gettext("your first entered pull arrived as a dupe reroll, so the replay shows it as its cell's branch value")}`
          : ""
      }</p>
    </div>`;

  const render = (data, machine) => {
    progressWrap.hidden = true;
    goBtn.disabled = false;
    results.hidden = false;

    if (data.error) {
      results.innerHTML = `<p class="field-error">${interpolate(gettext("Search failed: %s"), [esc(data.error)])}</p>`;
      return;
    }
    if (!data.matches.length) {
      results.replaceChildren(document.getElementById("nseekNoneTpl").content.cloneNode(true));
      return;
    }

    let notes = "";
    if (data.truncated) {
      notes = `<p class="field-warning">${interpolate(
        gettext("Far too many seeds match - this window is too short to pin yours down. Add a few more rolls and search again; only the first %s are shown."),
        [data.matches.length],
      )}</p>`;
    } else if (data.matches.length > 1) {
      notes = `<p class="field-warning">${interpolate(
        gettext("%s seeds match. Roll a few more items, add them, and search again to narrow it down."),
        [data.matches.length],
      )}</p>`;
    }
    results.innerHTML =
      notes + data.matches.map((m) => matchCard(m, data.last_cat, machine)).join("");
  };

  // A result button applies its seed right here: the sought machine joins the
  // shown columns (so what you just rolled is on screen), the finder folds away.
  results.addEventListener("click", (e) => {
    const btn = e.target.closest(".seek-use");
    if (!btn) return;
    pickFlavor(btn.dataset.machine); // the sought pool is always a plain capsule
    setSeed(btn.dataset.seed, btn.dataset.item || "");
    document.getElementById("normalFinder").open = false;
    tracksHost.scrollIntoView({ behavior: "smooth", block: "start" });
  });

  const search = async (spec, machine) => {
    let data;
    try {
      const found = await localSeek(spec, {
        wasmUrl: nseekForm.dataset.wasmUrl,
        workerUrl: nseekForm.dataset.workerUrl,
        onProgress: (run, fraction) => {
          bar.value = fraction;
          progressText.textContent = `${PASS_LABELS[run]} ${Math.round(fraction * 100)}%`;
        },
      });
      data = { ...found, last_cat: spec.last_cat };
    } catch (error) {
      data = { error: error.message };
    }
    render(data, machine);
  };

  nseekForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    setError("");

    const values = [...rollsEl.querySelectorAll(".seek-roll")].map((h) => h.value);
    const last = values.length - 1 - [...values].reverse().findIndex(Boolean);
    const filled = values.filter(Boolean);
    if (filled.length && values.slice(0, last + 1).some((v) => !v)) {
      setError(gettext("Fill your pulls in order, top to bottom - no gaps."));
      return;
    }
    if (filled.length < MIN) {
      setError(interpolate(gettext("Enter at least %s pulls (8-12 works best)."), [MIN]));
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
    search(await resp.json(), machine);
  });
}

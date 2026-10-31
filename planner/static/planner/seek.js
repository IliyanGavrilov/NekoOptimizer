// ---- Seed Finder: enter your real pulls, sieve the seed space locally ---------
// Picking a banner fetches its pools and builds one searchable cat box per pull;
// submitting has the server check the pulls, then this page sieves the whole 2^32
// seed space itself (seekrun.js) until the matching seed(s) come back.
const seekForm = document.getElementById("seekForm");
if (seekForm) {
  const token = seekForm.querySelector("[name=csrfmiddlewaretoken]").value;
  const bannerValue = document.getElementById("seekBannerValue");
  const pickHint = document.getElementById("seekPickHint");
  const entry = document.getElementById("seekEntry");
  const rollsEl = document.getElementById("seekRolls");
  const addRow = document.getElementById("seekAddRow");
  const goBtn = document.getElementById("seekGo");
  const errorEl = document.getElementById("seekError");
  const progressWrap = document.getElementById("seekProgress");
  const bar = document.getElementById("seekBar");
  const progressText = document.getElementById("seekProgressText");
  const results = document.getElementById("seekResults");
  const plannerUrl = seekForm.dataset.plannerUrl;
  const MIN = Number(seekForm.dataset.minRolls);
  const MAX = Number(seekForm.dataset.maxRolls);
  const START_ROWS = 10;

  let optionsHtml = ""; // the selected banner's cats as picker rows, rendered per fetch

  const esc = (text) => text.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);

  const setError = (msg) => (errorEl.textContent = msg || "");

  // ---- Banner list: the planner's picker rows, filtered by the search box ----
  const bannerBox = document.getElementById("seekBanner");
  const bannerSearch = document.getElementById("seekBannerSearch");
  const runRows = [...bannerBox.querySelectorAll(".seek-run")];
  const runGroups = [...bannerBox.querySelectorAll("details.group-drop")];
  const liveHeader = bannerBox.querySelector(".seek-picker > .group");
  const liveRows = runRows.filter((row) => row.parentElement === liveHeader.parentElement);
  const noMatch = bannerBox.querySelector(".seek-no-match");

  bannerSearch.addEventListener("input", () => {
    const query = bannerSearch.value.trim().toLowerCase();
    let any = false;
    for (const row of runRows) {
      row.hidden = Boolean(query) && !row.dataset.search.includes(query);
      any = any || !row.hidden;
    }
    // While searching, groups with a hit open so their matches actually show, the
    // rest disappear header and all; clearing the box folds everything back up.
    for (const group of runGroups) {
      const hit = query && group.querySelector(".seek-run:not([hidden])");
      group.open = Boolean(hit);
      group.hidden = Boolean(query) && !hit;
    }
    liveHeader.hidden = Boolean(query) && !liveRows.some((row) => !row.hidden);
    noMatch.hidden = any;
  });

  bannerBox.addEventListener("click", async (e) => {
    const row = e.target.closest(".seek-run");
    if (!row) return;

    bannerBox.querySelector(".seek-run.selected")?.classList.remove("selected");
    row.classList.add("selected");
    bannerValue.value = row.dataset.value;

    setError("");
    results.hidden = true;
    entry.hidden = true;
    pickHint.hidden = false;
    rollsEl.innerHTML = "";

    let resp;
    try {
      resp = await fetch(
        `${seekForm.dataset.poolUrl}?banner=${encodeURIComponent(bannerValue.value)}`
      );
    } catch {
      resp = null;
    }
    if (!resp || !resp.ok) {
      setError(gettext("Couldn't load that banner's cats - is the server still running?"));
      return;
    }
    const pool = await resp.json();
    optionsHtml =
      `<input type="text" class="pick-search" placeholder="${gettext("Search cats…")}"` +
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
                  `<span class="rarity" data-rarity="${esc(g.rarity)}">${esc(g.label)}</span>` +
                  `<span class="combo-cat">${esc(o.label)}</span></button>`
              )
              .join("")
        )
        .join("") + `<p class="combo-empty" hidden>${gettext("No cats match.")}</p>`;
    for (let i = 0; i < START_ROWS; i++) appendRow();
    pickHint.hidden = true;
    entry.hidden = false;
  });

  // ---- Pull pickers: a dropdown per pull, with a search box inside -----------
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
        <span class="roll-label">${gettext("Pick a cat…")}</span><span class="roll-chevron">&#9662;</span>
      </button>
      <input type="hidden" class="seek-roll">
      <div class="combo-list" hidden>${optionsHtml}</div>
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
      hidden.dataset.name = row.querySelector(".combo-cat").textContent;
      checked = false; // the entry changed: look it over again before searching
      label.innerHTML = row.innerHTML; // rarity chip + name, exactly as listed
      label.classList.remove("roll-placeholder");
      panel.hidden = true;
      // Hop to the next empty pull so a 10-pull entry is one flow (its dropdown
      // stays closed until asked - a stray open panel would cover the buttons).
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
        e.preventDefault(); // pick, never submit the form from inside the panel
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

  addRow.addEventListener("click", () => {
    if (rollsEl.children.length < MAX) appendRow();
    addRow.hidden = rollsEl.children.length >= MAX;
  });

  // ---- The search itself: validate on the server, sieve right here ----------------

  const PASS_LABELS = [
    gettext("Checking every possible seed (step 1 of 3)…"),
    gettext("No exact match yet — checking if your first pull was a reroll (step 2 of 3)…"),
    gettext("No exact match yet — checking if your first pull was a reroll (step 3 of 3)…"),
  ];

  const matchCard = (m, lastCat) => {
    const open = `${plannerUrl}?seed=${m.seed_after}${
      lastCat ? `&last=${encodeURIComponent(lastCat)}` : ""
    }`;
    const replay = `${plannerUrl}?seed=${m.seed_before}`;
    const dupeNote = m.run
      ? ` &middot; ${gettext("your first entered pull arrived as a dupe reroll, so the replay shows it in the R column")}`
      : "";
    const before = interpolate(gettext("Seed before those pulls: %s"), [m.seed_before]);
    return `<div class="seek-match">
      <div class="seek-seed">${interpolate(gettext("Your seed is now %s"), [`<strong>${m.seed_after}</strong>`])}</div>
      <a class="seek-open" href="${open}">${gettext("Open the planner at your position")} &rarr;</a>
      <p class="muted">${before} &middot; <a href="${replay}">${gettext("replay them")}</a>${dupeNote}</p>
    </div>`;
  };

  // One seed left: it's yours, so store it on your profile straight away - and nudge
  // a backup, since the number is the one thing you can't get back without re-rolling.
  const keepFound = async (m, lastCat) => {
    const note = results.querySelector(".seek-kept");
    const body = new URLSearchParams({
      kind: "rare",
      seed: m.seed_after,
      last: lastCat || "",
      csrfmiddlewaretoken: token,
    });
    let ok = false;
    try {
      const resp = await fetch(seekForm.dataset.saveUrl, {
        method: "POST",
        headers: { "X-CSRFToken": token },
        body,
      });
      ok = resp.ok;
    } catch {
      ok = false;
    }
    const seed = `<strong>${m.seed_after}</strong>`;
    const copy = `<button type="button" class="link-btn seek-copy">${gettext("copy a link to it")}</button>`;
    note.innerHTML = ok
      ? interpolate(
          gettext("Saved as your seed ✓ - the planner opens on it from now on. Back it up too: write down %(seed)s, or %(copy)s."),
          { seed, copy },
          true,
        )
      : interpolate(
          gettext("Couldn't save it automatically - write down %(seed)s and open the planner with the link above; it saves from there."),
          { seed },
          true,
        );
  };
  results.addEventListener("click", async (e) => {
    const btn = e.target.closest(".seek-copy");
    if (!btn) return;
    const url = new URL(results.querySelector(".seek-open").href, location.href).href;
    btn.textContent = (await copyToClipboard(url)) ? gettext("link copied ✓") : url;
  });

  const render = (data) => {
    progressWrap.hidden = true;
    goBtn.disabled = false;
    results.hidden = false;

    if (data.error) {
      results.innerHTML = `<p class="field-error">${interpolate(gettext("Search failed: %s"), [esc(data.error)])}</p>`;
      return;
    }
    if (!data.matches.length) {
      results.replaceChildren(document.getElementById("seekNoneTpl").content.cloneNode(true));
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
        gettext("%s seeds match. Roll a few more cats, add them, and search again to narrow it down."),
        [data.matches.length],
      )}</p>`;
    }
    results.innerHTML =
      notes + data.matches.map((m) => matchCard(m, data.last_cat)).join("");
    if (data.matches.length === 1 && !data.truncated) {
      results
        .querySelector(".seek-match")
        .insertAdjacentHTML("beforeend", `<p class="seek-kept muted">${gettext("Saving it as your seed…")}</p>`);
      keepFound(data.matches[0], data.last_cat);
    }
  };

  const search = async (spec) => {
    let data;
    try {
      const found = await localSeek(spec, {
        wasmUrl: seekForm.dataset.wasmUrl,
        workerUrl: seekForm.dataset.workerUrl,
        onProgress: (run, fraction) => {
          bar.value = fraction;
          progressText.textContent = `${PASS_LABELS[run]} ${Math.round(fraction * 100)}%`;
        },
      });
      data = { ...found, last_cat: spec.last_cat };
    } catch (error) {
      data = { error: error.message };
    }
    render(data);
  };

  // ---- Look the entry over before searching: the classic mistakes ----------------
  // Each is a warning, not a block - "Search anyway" goes ahead once they're read.
  const checkEl = document.getElementById("seekCheck");
  let checked = false;
  const RARE = "0";
  const UBERISH = new Set(["2", "3"]); // Uber Super Rare, Legend Rare
  const preflight = (picks) => {
    const notes = [];
    const rarity = (i) => picks[i].value.split(":")[0];
    for (const at of [10, 14]) {
      if (picks.length > at && UBERISH.has(rarity(at))) {
        const message =
          at === 14
            ? gettext("Pull %(n)s is %(cat)s. If that was the <strong>guaranteed Uber</strong> of an 11-draw or a step-up, remove it and everything after it - it isn't part of the normal roll sequence.")
            : gettext("Pull %(n)s is %(cat)s. If that was the <strong>guaranteed Uber</strong> of an 11-draw, remove it and everything after it - it isn't part of the normal roll sequence.");
        notes.push(interpolate(message, { n: at + 1, cat: esc(picks[at].dataset.name) }, true));
      }
    }
    for (let i = 1; i < picks.length; i++) {
      if (rarity(i) === RARE && picks[i].value === picks[i - 1].value) {
        notes.push(
          interpolate(
            gettext("Pulls %(a)s and %(b)s are both %(cat)s. The game never deals the same Rare cat twice in a row (it rerolls the repeat), so one of them is probably mis-picked or out of order."),
            { a: i, b: i + 1, cat: esc(picks[i].dataset.name) },
            true,
          ),
        );
      }
    }
    return notes;
  };

  seekForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    setError("");

    const picks = [...rollsEl.querySelectorAll(".seek-roll")].filter((h) => h.value);
    const notes = checked ? [] : preflight(picks);
    checkEl.hidden = !notes.length;
    if (notes.length) {
      checkEl.innerHTML = `<p>${gettext("Quick check before searching:")}</p><ul>${notes
        .map((n) => `<li>${n}</li>`)
        .join("")}</ul><p>${gettext("Fix it above, or search anyway if it's right.")}</p>`;
      goBtn.textContent = gettext("Search anyway");
      checked = true;
      return;
    }
    goBtn.textContent = gettext("Find my seed");
    checked = false;

    const values = [...rollsEl.querySelectorAll(".seek-roll")].map((h) => h.value);
    const last = values.length - 1 - [...values].reverse().findIndex(Boolean);
    const filled = values.filter(Boolean);
    if (filled.length && values.slice(0, last + 1).some((v) => !v)) {
      setError(gettext("Fill your pulls in order, top to bottom - no gaps."));
      return;
    }
    if (filled.length < MIN) {
      setError(interpolate(gettext("Enter at least %s pulls (around 10 works best)."), [MIN]));
      return;
    }

    const body = new URLSearchParams({ banner: bannerValue.value, csrfmiddlewaretoken: token });
    filled.forEach((v) => body.append("rolls", v));
    const resp = await fetch(seekForm.dataset.startUrl, {
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
    search(await resp.json());
  });
}

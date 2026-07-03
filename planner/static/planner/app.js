// ---- Planner: target selection ---------------------------------------
const picker = document.getElementById("targetPicker");
if (picker) {
  const panel = document.getElementById("selectedPanel");
  const panelChips = document.getElementById("selectedChips");
  const count = document.getElementById("selectedCount");
  const inputs = document.getElementById("targetInputs");
  const selected = new Map(); // pk -> name

  // ---- Persist the form to localStorage (no accounts, so this is the only
  // memory of seed/catfood/tickets/options between visits). Targets and banner
  // selection are NOT persisted; the collection persists server-side.
  const STORE_KEY = "nekoPlanner";
  const seedEl = document.getElementById("id_seed");
  const ticketsEl = document.getElementById("id_tickets");
  const catfoodEl = document.getElementById("id_catfood");
  const wishlistEl = document.getElementById("id_use_wishlist");
  const ticketValueEl = document.getElementById("id_ticket_value");
  const platLegendCapEl = document.getElementById("id_platinum_legend_cap");
  const exploreEl = document.getElementById("id_explore");
  const horizonEl = document.getElementById("id_horizon");
  const horizonRow = document.querySelector(".explore-horizon");
  const budgetFields = document.querySelector(".budget-fields");
  const stored = (() => {
    try {
      return JSON.parse(localStorage.getItem(STORE_KEY)) || {};
    } catch {
      return {};
    }
  })();
  let ready = false; // don't persist until the restore below has run
  // Inline validation messages live next to their field; clear them all as soon
  // as the user changes anything.
  const ERROR_SLOTS = ["seedError", "targetsError", "submitError"];
  function clearError() {
    for (const id of ERROR_SLOTS) {
      const el = document.getElementById(id);
      if (el) el.textContent = "";
    }
  }
  function save() {
    if (!ready) return;
    clearError();
    // Targets and banner selection are deliberately NOT persisted - each visit
    // starts fresh from today's banners and no targets.
    localStorage.setItem(
      STORE_KEY,
      JSON.stringify({
        seed: seedEl.value,
        tickets: ticketsEl.value,
        catfood: catfoodEl.value,
        useWishlist: wishlistEl.checked,
        ticketValue: ticketValueEl.value,
        platLegendCap: platLegendCapEl.value,
        explore: exploreEl.checked,
        horizon: horizonEl.value,
      }),
    );
  }

  const chipsFor = (pk) => picker.querySelectorAll(`.chip[data-pk="${pk}"]`);

  function render() {
    panel.hidden = selected.size === 0;
    count.textContent = selected.size;
    panelChips.replaceChildren();
    inputs.replaceChildren();
    for (const [pk, name] of selected) {
      const tag = document.createElement("button");
      tag.type = "button";
      tag.className = "chip selected removable";
      tag.dataset.pk = pk;
      tag.innerHTML = `${name} <span aria-hidden="true">&times;</span>`;
      tag.addEventListener("click", () => toggle(pk, name));
      panelChips.appendChild(tag);

      const hidden = document.createElement("input");
      hidden.type = "hidden";
      hidden.name = "targets";
      hidden.value = pk;
      inputs.appendChild(hidden);
    }
    updateWarnings();
  }

  function toggle(pk, name) {
    if (selected.has(pk)) selected.delete(pk);
    else selected.set(pk, name);
    const on = selected.has(pk);
    chipsFor(pk).forEach((c) => c.classList.toggle("selected", on));
    render();
    save();
  }

  picker.addEventListener("click", (e) => {
    const chip = e.target.closest(".chip[data-pk]");
    if (chip) toggle(chip.dataset.pk, chip.dataset.name);
  });

  // Banner "session" selection: tapping + on a banner includes it and every
  // banner live on its opening day (what you'd roll together at that time).
  const browser = document.getElementById("targetBrowser");
  const bannerInputs = document.getElementById("bannerInputs");
  const bannerCount = document.getElementById("bannerCount");
  const includes = [...browser.querySelectorAll(".banner-include")];

  // A target can only drop on a banner that carries it, so a target picked while
  // its banner isn't in the selected session can never come out. Flag those
  // (dashed chip + a note) live, recomputed whenever targets or banners change.
  // Cats are keyed by banner NAME and only a name's newest row carries chips (the
  // Past list is one row per rerun), so reachability unions chips across every row
  // sharing a selected banner's name.
  const warnSlot = document.getElementById("targetsWarn");
  function reachablePks() {
    const pks = new Set();
    const names = new Set();
    for (const btn of includes) {
      if (btn.getAttribute("aria-pressed") === "true") names.add(btn.dataset.banner);
    }
    if (!names.size) return pks;
    for (const btn of includes) {
      if (!names.has(btn.dataset.banner)) continue;
      btn.closest(".banner-group").querySelectorAll(".chip[data-pk]").forEach((c) => pks.add(c.dataset.pk));
    }
    return pks;
  }

  // Opening a rerun row without chips borrows them from the name's carrier row, so
  // every Past run is browsable without rendering ~100k chips upfront. ("toggle"
  // doesn't bubble - listen in the capture phase.)
  browser.addEventListener("toggle", (e) => {
    const group = e.target.closest ? e.target.closest(".banner-group") : null;
    if (!group || !e.target.open || group.querySelector(".chip[data-pk]")) return;
    const name = group.querySelector(".banner-include")?.dataset.banner;
    if (!name) return;
    const carrier = includes
      .map((b) => b.closest(".banner-group"))
      .find((g) => g !== group && g.querySelector(".banner-include")?.dataset.banner === name && g.querySelector(".chip[data-pk]"));
    if (!carrier) return;
    for (const row of carrier.querySelectorAll("[data-rarity-row]")) {
      const clone = row.cloneNode(true);
      clone.querySelectorAll(".chip[data-pk]").forEach((c) => c.classList.toggle("selected", selected.has(c.dataset.pk)));
      group.appendChild(clone);
    }
  }, true);

  // The Past group ships as an empty shell - its ~2000 per-run rows are most of the
  // page's bytes and render time - so fetch the rows the first time they're needed
  // (opening the group, or searching, which must cover every run) and fold the new
  // include buttons into the session/warning logic.
  const pastGroup = document.getElementById("pastGroup");
  let pastLoaded = false;
  async function loadPast() {
    if (!pastGroup || pastLoaded) return;
    pastLoaded = true;
    const note = pastGroup.querySelector(".past-loading");
    if (note) note.hidden = false;
    try {
      const resp = await fetch(pastGroup.dataset.pastUrl);
      pastGroup.insertAdjacentHTML("beforeend", await resp.text());
      includes.push(...pastGroup.querySelectorAll(".banner-include"));
      if (note) note.remove();
      updateWarnings();
      applySearch(); // rows that arrived mid-search must obey the current query
    } catch {
      pastLoaded = false; // reopen retries
      if (note) note.textContent = "Couldn't load past banners - close and reopen to retry.";
    }
  }
  if (pastGroup) {
    pastGroup.addEventListener("toggle", () => {
      if (pastGroup.open) loadPast();
    });
  }
  function updateWarnings() {
    if (!warnSlot) return;
    const reach = reachablePks();
    const stranded = [];
    for (const [pk, name] of selected) if (!reach.has(pk)) stranded.push(name);
    panelChips.querySelectorAll(".chip[data-pk]").forEach((c) => {
      c.classList.toggle("unreachable", !reach.has(c.dataset.pk));
    });
    const it = stranded.length === 1 ? "it" : "them";
    warnSlot.hidden = stranded.length === 0;
    warnSlot.textContent = stranded.length
      ? `Won't drop on the selected banners: ${stranded.join(", ")}. Add a banner that carries ${it}, or remove ${it}.`
      : "";
  }

  const rangeOf = (btn) => {
    const d = btn.closest(".banner-group");
    return [d.dataset.start, d.dataset.end];
  };
  // A banner is live on a given day when start <= day < end. Banners switch at
  // the changeover day, so one ending on day X and another starting on X are
  // consecutive, not concurrent (end is exclusive). ISO dates sort lexically.
  const liveOn = (range, day) => !!range[0] && range[0] <= day && day < range[1];

  function setIncluded(btn, on) {
    btn.setAttribute("aria-pressed", on ? "true" : "false");
    btn.textContent = on ? "✓" : "+"; // selecting must not expand the cats
    btn.closest(".banner-group").classList.toggle("included", on);
  }
  function syncBanners() {
    bannerInputs.replaceChildren();
    for (const btn of includes) {
      if (btn.getAttribute("aria-pressed") !== "true") continue;
      const input = document.createElement("input");
      input.type = "hidden";
      input.name = "banners";
      // Pin the exact run: a recurring name (Platinum Capsules) reruns with a
      // different pool, so the server needs the run's start date, not just the name.
      input.value = btn.dataset.run ? `${btn.dataset.run}|${btn.dataset.banner}` : btn.dataset.banner;
      bannerInputs.appendChild(input);
    }
    const n = bannerInputs.childElementCount;
    bannerCount.textContent = n
      ? `Rolling ${n} banner${n === 1 ? "" : "s"}.`
      : "No banners selected.";
    locateIdx = 0;
    syncBannerChips();
    updateWarnings();
    save();
  }
  // One chip per selected banner under the hint, labelled with the banner's set
  // title; clicking a chip scrolls the picker to that banner.
  const bannerChips = document.getElementById("bannerChips");
  function syncBannerChips() {
    bannerChips.replaceChildren();
    for (const btn of includes) {
      if (btn.getAttribute("aria-pressed") !== "true") continue;
      const group = btn.closest(".banner-group");
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "banner-chip";
      chip.textContent = group.dataset.title || btn.dataset.banner;
      chip.title = btn.dataset.banner; // the run's full marketing text
      chip.addEventListener("click", () => locate(group));
      bannerChips.appendChild(chip);
    }
    bannerChips.hidden = !bannerChips.childElementCount;
  }
  // Scroll the picker to a banner and pulse it (opening the group it hides in).
  function locate(group) {
    const drop = group.closest("details.group-drop");
    if (drop) drop.open = true;
    group.scrollIntoView({ behavior: "smooth", block: "center" });
    group.classList.remove("flash-locate");
    void group.offsetWidth; // restart the animation when stepping banner to banner
    group.classList.add("flash-locate");
  }
  // "Rolling N banners." doubles as a locator too: each click steps to the next one.
  let locateIdx = 0;
  bannerCount.addEventListener("click", () => {
    const marked = includes
      .filter((b) => b.getAttribute("aria-pressed") === "true")
      .map((b) => b.closest(".banner-group"));
    if (!marked.length) return;
    locate(marked[locateIdx % marked.length]);
    locateIdx += 1;
  });
  // Platinum/Legend capsules run on scarce tickets, so they're opt-in: never part
  // of a session, and each toggles on its own.
  const CAPPED = /platinum|legend/i;
  const today = () => new Date().toISOString().slice(0, 10);
  const dayBefore = (iso) => {
    const d = new Date(`${iso}T00:00:00Z`);
    d.setUTCDate(d.getUTCDate() - 1);
    return d.toISOString().slice(0, 10);
  };
  // The day a banner's session means: today when the banner is running right now
  // (so a still-open long banner selects TODAY's companions, not the ones from its
  // opening day weeks ago), otherwise the nearest day of its window - a past
  // banner's closing day, an upcoming banner's opening day.
  function sessionDay(range) {
    const now = today();
    if (now < range[0]) return range[0];
    if (now >= range[1]) {
      const last = dayBefore(range[1]);
      return last < range[0] ? range[0] : last;
    }
    return now;
  }
  // Click an unselected banner -> select that banner's time period (every other
  // non-capsule banner live on its session day), replacing whatever period was
  // selected before. Click a selected banner -> unselect just that one. Capsules
  // are opt-in, toggled individually and left alone when a period is selected.
  function toggleSession(btn) {
    if (btn.getAttribute("aria-pressed") === "true") {
      setIncluded(btn, false);
    } else if (CAPPED.test(btn.dataset.banner)) {
      setIncluded(btn, true);
    } else {
      const day = sessionDay(rangeOf(btn));
      for (const other of includes) {
        if (!CAPPED.test(other.dataset.banner)) setIncluded(other, liveOn(rangeOf(other), day));
      }
    }
    syncBanners();
  }
  browser.addEventListener("click", (e) => {
    const btn = e.target.closest(".banner-include");
    if (!btn) return;
    e.preventDefault(); // don't toggle the <details>
    e.stopPropagation();
    toggleSession(btn);
  });
  // Searching matches banners by their set NAME (every run, so a recurring set shows
  // its whole history) and cats by name, side by side; clearing it restores the
  // banner/rarity grouping.
  const search = document.getElementById("targetSearch");
  const searchClear = document.getElementById("targetSearchClear");
  const searchHint = document.getElementById("targetSearchHint");
  const grouped = browser;
  const flat = document.getElementById("targetFlat");
  function applySearch() {
    const query = search.value.trim().toLowerCase();
    const searching = query !== "";
    flat.hidden = !searching;
    // While searching, surface a clear (x) button + hint so it's obvious how to
    // get back to the banner menu without manually deleting the query.
    searchClear.hidden = !searching;
    searchHint.hidden = !searching;
    if (searching && !pastLoaded) loadPast(); // a set's past runs must be findable too
    grouped.querySelectorAll(".banner-group").forEach((group) => {
      group.hidden =
        searching && !(group.dataset.title || "").toLowerCase().includes(query);
    });
    // Group headings collapse away when nothing under them matches; matching drops
    // open so the hits are visible without another click.
    grouped.querySelectorAll("h3.group").forEach((h) => {
      h.hidden = searching;
    });
    grouped.querySelectorAll("details.group-drop").forEach((drop) => {
      const hasMatch = !!drop.querySelector(".banner-group:not([hidden])");
      drop.hidden = searching && !hasMatch;
      if (searching) drop.open = hasMatch;
    });
    if (searching) {
      flat.querySelectorAll("[data-name]").forEach((chip) => {
        chip.hidden = !chip.dataset.name.toLowerCase().includes(query);
      });
    }
  }
  search.addEventListener("input", () => {
    applySearch();
    save();
  });
  // Selecting cats keeps the search open (multi-pick); this is the explicit way back.
  searchClear.addEventListener("click", () => {
    search.value = "";
    applySearch();
    save();
    search.focus();
  });

  // Restore the saved form, then default whatever was never saved.
  if (stored.seed != null && stored.seed !== "") seedEl.value = stored.seed;
  if (stored.tickets != null) ticketsEl.value = stored.tickets;
  if (stored.catfood != null) catfoodEl.value = stored.catfood;
  wishlistEl.checked = !!stored.useWishlist;
  if (stored.ticketValue != null) ticketValueEl.value = stored.ticketValue;
  if (stored.platLegendCap != null) platLegendCapEl.value = stored.platLegendCap;
  if (stored.explore != null) exploreEl.checked = stored.explore; // else keep server default (on)
  if (stored.horizon != null) horizonEl.value = stored.horizon;
  const syncExplore = () => {
    const on = exploreEl.checked;
    horizonRow.hidden = !on;
    if (budgetFields) budgetFields.hidden = on; // explore ignores budget, so hide those fields
  };
  syncExplore();
  ticketsEl.addEventListener("input", save);
  catfoodEl.addEventListener("input", save);
  wishlistEl.addEventListener("change", save);
  ticketValueEl.addEventListener("input", save);
  platLegendCapEl.addEventListener("input", save);
  exploreEl.addEventListener("change", () => {
    syncExplore();
    save();
  });
  horizonEl.addEventListener("input", save);

  render();

  // Targets and banner selection aren't persisted: every visit starts from the
  // banners live today (capsules excluded - they're opt-in) and no targets.
  for (const btn of includes) {
    if (!CAPPED.test(btn.dataset.banner) && liveOn(rangeOf(btn), today())) setIncluded(btn, true);
  }
  ready = true;
  syncBanners();

  const token = document.querySelector("[name=csrfmiddlewaretoken]").value;
  const plannerForm = document.getElementById("plannerForm");
  const solutions = document.getElementById("solutions");
  const browseTrack = document.getElementById("browseTrack");
  const trackHost = document.getElementById("trackHost");
  const resultsRegion = document.getElementById("resultsRegion");
  const planLoading = document.getElementById("planLoading");

  // ---- Track / Steps view switch, scoped to the opened subset solution -----
  solutions.addEventListener("click", (e) => {
    const btn = e.target.closest(".view-btn");
    if (!btn) return;
    const body = btn.closest(".solution-body");
    body.querySelectorAll(".view-btn").forEach((b) => {
      const on = b === btn;
      b.classList.toggle("is-active", on);
      b.setAttribute("aria-selected", on);
    });
    body.querySelectorAll(".view").forEach((v) => {
      v.hidden = v.dataset.view !== btn.dataset.view;
    });
  });
  const post = (url) =>
    fetch(url, { method: "POST", body: new FormData(plannerForm), headers: { "X-CSRFToken": token } });

  // ---- Apply a plan (delegated; solutions are injected by AJAX) --------
  // Own its cats, drop them from the wishlist, and spend its tickets/catfood.
  solutions.addEventListener("click", async (e) => {
    const btn = e.target.closest(".apply-plan");
    if (!btn || btn.disabled) return;
    const results = btn.closest("#planResults");
    const body = new URLSearchParams({ csrfmiddlewaretoken: token });
    (btn.dataset.cats ? btn.dataset.cats.split("|") : []).forEach((n) => body.append("cats", n));
    if (btn.dataset.seedAfter) body.append("seed_after", btn.dataset.seedAfter);
    const resp = await fetch(results.dataset.applyUrl, {
      method: "POST",
      headers: { "X-CSRFToken": token },
      body,
    });
    if (!resp.ok) return;
    const spend = (el, key) =>
      (el.value = Math.max(0, (Number(el.value) || 0) - (Number(btn.dataset[key]) || 0)));
    spend(ticketsEl, "tickets");
    spend(catfoodEl, "catfood");
    save();
    // "You rolled it": the seed advances to just after the plan's final draw. The
    // solution stays on screen (its steps still need doing in game), and the Rolls
    // track re-rolls from the new seed so it shows what comes next.
    if (btn.dataset.seedAfter) {
      setSeed(btn.dataset.seedAfter);
      browseTrack.hidden = false;
      refreshTracks();
    }
    btn.disabled = true;
    btn.textContent = "Applied ✓";
  });

  // ---- Live A/B tracks: reload whenever the seed or banner set changes ----
  // Needs a seed AND at least one selected banner; nothing selected => no track
  // (no implicit "current banners" fallback).
  let trackTimer;
  const anyBanner = () => includes.some((b) => b.getAttribute("aria-pressed") === "true");
  async function refreshTracks() {
    if (!seedEl.value.trim() || !anyBanner()) {
      trackHost.innerHTML = "";
      resultsRegion.hidden = !solutions.firstElementChild;
      return;
    }
    const resp = await post(trackHost.dataset.tracksUrl);
    if (!resp.ok) return;
    trackHost.innerHTML = await resp.text();
    resultsRegion.hidden = !trackHost.firstElementChild;
  }
  async function requestTracks() {
    // Changing the seed/banners invalidates any plan: drop back to browsing the rolls.
    solutions.innerHTML = "";
    browseTrack.hidden = false;
    await refreshTracks();
  }
  const scheduleTracks = () => {
    clearTimeout(trackTimer);
    trackTimer = setTimeout(requestTracks, 400);
  };
  seedEl.addEventListener("input", () => {
    save();
    scheduleTracks();
  });
  browser.addEventListener("click", (e) => {
    if (e.target.closest(".banner-include")) scheduleTracks();
  });

  // ---- Seed navigation: "roll to here" + undo ---------------------------
  // A programmatic seed change (a cell's ↻ button, applying a plan) pushes the
  // old seed onto a persisted undo stack, so the original is never lost; the
  // undo button beside the field walks back one change at a time. Typing a seed
  // by hand doesn't push - undo only covers changes the app made for you.
  const UNDO_KEY = "nekoSeedUndo";
  const seedUndo = document.getElementById("seedUndo");
  const undoStack = (() => {
    try {
      return JSON.parse(localStorage.getItem(UNDO_KEY)) || [];
    } catch {
      return [];
    }
  })();
  function syncUndo() {
    seedUndo.hidden = undoStack.length === 0;
    if (undoStack.length) seedUndo.title = `Back to seed ${undoStack[undoStack.length - 1]}`;
  }
  function setSeed(value) {
    const prev = seedEl.value.trim();
    if (prev && prev !== String(value)) {
      undoStack.push(prev);
      while (undoStack.length > 50) undoStack.shift();
      localStorage.setItem(UNDO_KEY, JSON.stringify(undoStack));
    }
    seedEl.value = value;
    syncUndo();
    save();
  }
  seedUndo.addEventListener("click", () => {
    if (!undoStack.length) return;
    seedEl.value = undoStack.pop();
    localStorage.setItem(UNDO_KEY, JSON.stringify(undoStack));
    syncUndo();
    save();
    requestTracks();
  });
  // "Roll to here" on any track cell (browsing or inside a solution): the seed
  // becomes the state just after that pull, so the next roll is the new 1A.
  resultsRegion.addEventListener("click", (e) => {
    const btn = e.target.closest(".reseed");
    if (!btn) return;
    setSeed(btn.dataset.seed);
    requestTracks();
  });
  syncUndo();

  // ---- Find plan: inline validation next to each field, then overlay the plan
  const flash = (el) => {
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    el.classList.remove("flash-error");
    void el.offsetWidth; // restart the animation if it's already mid-play
    el.classList.add("flash-error");
  };
  const targetsSection = document.getElementById("targetsSection");
  // Show a message in the inline slot beside the offending field, and flash it.
  const setError = (slotId, msg, flashEl) => {
    clearError();
    const slot = document.getElementById(slotId);
    if (slot) slot.textContent = msg;
    if (flashEl) flash(flashEl);
  };
  // Maps a server-side field error to its inline slot + the element to flash.
  const fieldSlot = {
    seed: ["seedError", seedEl],
    tickets: ["submitError", ticketsEl],
    catfood: ["submitError", catfoodEl],
    horizon: ["submitError", horizonEl],
    ticket_value: ["submitError", ticketValueEl],
    platinum_legend_cap: ["submitError", platLegendCapEl],
  };

  plannerForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    // Client-side checks first, with an inline note + flash instead of the
    // browser's "Please fill out this field" popup.
    if (!seedEl.value.trim()) return setError("seedError", "Enter a seed to roll.", seedEl);
    if (!anyBanner()) {
      return setError("targetsError", "Select at least one banner to roll.", targetsSection);
    }
    if (inputs.childElementCount === 0 && !wishlistEl.checked) {
      return setError(
        "targetsError",
        "Pick a target cat, or tick \"search my wishlist\".",
        targetsSection,
      );
    }
    planLoading.hidden = false;
    try {
      const resp = await post(trackHost.dataset.planUrl);
      if (resp.ok) {
        const data = await resp.json();
        // Swap the browse track for the subset-solution accordion.
        solutions.innerHTML = data.solutions_html;
        browseTrack.hidden = true;
        resultsRegion.hidden = !solutions.firstElementChild;
      } else {
        const { errors = {} } = await resp.json().catch(() => ({}));
        const field = Object.keys(errors).find((k) => k in fieldSlot);
        if (field) {
          setError(fieldSlot[field][0], errors[field][0], fieldSlot[field][1]);
        } else {
          const msg = (errors.__all__ || ["Check the form and try again."])[0];
          setError("targetsError", msg, targetsSection);
        }
      }
    } finally {
      planLoading.hidden = true;
    }
  });

  if (seedEl.value.trim()) requestTracks();
}

// ---- Collection: views, filters, instant owned / wishlist toggles ----
const collectionBrowser = document.getElementById("collectionBrowser");
if (collectionBrowser) {
  const token = document.getElementById("csrfToken").value;
  const sections = [...collectionBrowser.querySelectorAll(".collection-section")];
  const noMatches = collectionBrowser.querySelector(".no-matches");

  // Two renderings of the same units (by rarity / by gacha set); one is shown at a
  // time and the choice sticks across visits. Marks are synced between them by pk.
  const VIEW_KEY = "nekoCollectionView";
  const viewBtns = [...document.querySelectorAll("#collectionViews .view-btn")];
  const views = [...collectionBrowser.querySelectorAll(".collection-view")];
  function showView(name) {
    viewBtns.forEach((b) => {
      const on = b.dataset.view === name;
      b.classList.toggle("is-active", on);
      b.setAttribute("aria-selected", on);
    });
    views.forEach((v) => {
      v.hidden = v.dataset.view !== name;
    });
    applyFilters();
  }
  document.getElementById("collectionViews").addEventListener("click", (e) => {
    const btn = e.target.closest(".view-btn");
    if (!btn) return;
    localStorage.setItem(VIEW_KEY, btn.dataset.view);
    showView(btn.dataset.view);
  });

  // Search and the rarity pills combine, applied to the visible view. Every row
  // carries its rarity (a rarity section is one row of itself), so both views
  // filter the same way: hide non-matching chips, then empty rows and sections.
  const search = document.getElementById("collectionSearch");
  const rarityBtns = [...document.querySelectorAll("#rarityFilter button")];
  function applyFilters() {
    const query = search.value.trim().toLowerCase();
    const rarity = rarityBtns.find((b) => b.getAttribute("aria-pressed") === "true").dataset.rarity;
    const active = views.find((v) => !v.hidden);
    for (const section of active.querySelectorAll(".collection-section")) {
      // A query matching the section itself (a set or rarity name) keeps it whole.
      const labelHit = !!query && section.dataset.label.toLowerCase().includes(query);
      for (const row of section.querySelectorAll(".rarity-row")) {
        let shown = 0;
        if (rarity && row.dataset.rarity !== rarity) {
          row.querySelectorAll(".own-chip").forEach((chip) => {
            chip.hidden = true;
          });
        } else {
          row.querySelectorAll(".own-chip").forEach((chip) => {
            const hit =
              !query || labelHit || chip.dataset.name.toLowerCase().includes(query);
            chip.hidden = !hit;
            shown += hit;
          });
        }
        row.hidden = shown === 0;
      }
      section.hidden = !section.querySelector(".rarity-row:not([hidden])");
    }
    noMatches.hidden = !!active.querySelector(".collection-section:not([hidden])");
  }
  search.addEventListener("input", applyFilters);
  document.getElementById("rarityFilter").addEventListener("click", (e) => {
    const btn = e.target.closest("button");
    if (!btn) return;
    rarityBtns.forEach((b) => b.setAttribute("aria-pressed", b === btn ? "true" : "false"));
    applyFilters();
  });

  // "12 / 325 owned" per section header, ignoring filters, refreshed on every change.
  function updateCounts() {
    for (const section of sections) {
      const total = section.querySelectorAll(".own-chip").length;
      const owned = section.querySelectorAll(".own-chip.owned").length;
      section.querySelector(".owned-count").textContent = `${owned} / ${total} owned`;
    }
  }

  // The same unit renders once per view; every change lands on all its copies.
  const copiesOf = (pk) => collectionBrowser.querySelectorAll(`.own-chip[data-pk="${pk}"]`);
  function mark(pk, state) {
    copiesOf(pk).forEach((c) => {
      c.classList.toggle("owned", state.owned);
      c.classList.toggle("wanted", state.wanted);
    });
  }

  collectionBrowser.addEventListener("click", async (e) => {
    const bulk = e.target.closest(".bulk-own, .bulk-star");
    if (bulk) return bulkToggle(bulk);
    const star = e.target.closest(".chip-star");
    if (!star && !e.target.closest(".chip-own")) return;
    const chip = e.target.closest(".own-chip");
    const field = star ? "wanted" : "owned";
    const body = new URLSearchParams({ pk: chip.dataset.pk, field, csrfmiddlewaretoken: token });
    const resp = await fetch(collectionBrowser.dataset.toggleUrl, {
      method: "POST",
      headers: { "X-CSRFToken": token },
      body,
    });
    if (!resp.ok) return;
    mark(chip.dataset.pk, await resp.json());
    updateCounts();
  });

  // Section-header ✓/★: mark the whole section owned/wanted, or clear it when it
  // already is. The server decides which way it goes and skips owned on wishlists.
  async function bulkToggle(btn) {
    const field = btn.classList.contains("bulk-star") ? "wanted" : "owned";
    const chips = [...btn.closest(".collection-section").querySelectorAll(".own-chip")];
    const body = new URLSearchParams({ field, csrfmiddlewaretoken: token });
    chips.forEach((c) => body.append("pk", c.dataset.pk));
    const resp = await fetch(collectionBrowser.dataset.bulkUrl, {
      method: "POST",
      headers: { "X-CSRFToken": token },
      body,
    });
    if (!resp.ok) return;
    const { value } = await resp.json();
    for (const chip of chips) {
      const owned = field === "owned" ? value : chip.classList.contains("owned");
      const wanted =
        field === "wanted"
          ? value && !chip.classList.contains("owned")
          : chip.classList.contains("wanted");
      mark(chip.dataset.pk, { owned, wanted });
    }
    updateCounts();
  }

  updateCounts();
  const savedView = localStorage.getItem(VIEW_KEY);
  showView(savedView === "sets" ? "sets" : "rarity");
}

// ---- Drag-to-scrub number inputs -------------------------------------
// Click-drag up/down anywhere on a number field to step it up/down; a plain
// click (no vertical movement) still focuses the field for typing.
const PX_PER_STEP = 7;
document.querySelectorAll('input[type="number"]').forEach((input) => {
  const step = Number(input.step) || 1;
  const min = input.min === "" ? -Infinity : Number(input.min);
  const max = input.max === "" ? Infinity : Number(input.max);
  let dragging = false;
  let moved = false;
  let startY = 0;
  let startVal = 0;

  input.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
    dragging = true;
    moved = false;
    startY = e.clientY;
    startVal = Number(input.value) || 0;
    input.setPointerCapture(e.pointerId);
  });

  input.addEventListener("pointermove", (e) => {
    if (!dragging) return;
    const dy = startY - e.clientY; // up is positive -> increases the value
    if (!moved && Math.abs(dy) < 3) return;
    moved = true;
    e.preventDefault();
    if (document.activeElement === input) input.blur();
    let val = startVal + Math.round(dy / PX_PER_STEP) * step;
    val = Math.min(max, Math.max(min, val));
    if (String(val) !== input.value) {
      input.value = val;
      input.dispatchEvent(new Event("input", { bubbles: true }));
    }
  });

  const end = (e) => {
    if (!dragging) return;
    dragging = false;
    if (input.hasPointerCapture(e.pointerId)) input.releasePointerCapture(e.pointerId);
  };
  input.addEventListener("pointerup", end);
  input.addEventListener("pointercancel", end);
  // Swallow the click that ends a drag so it doesn't drop a caret mid-scrub.
  input.addEventListener("click", (e) => {
    if (moved) e.preventDefault();
  });
});

// ---- Sticky track headers pin below the site header ---------------------
// The header's height varies (it wraps on narrow screens), so measure it into
// a CSS variable the thead's sticky top offset reads.
{
  const siteHeader = document.querySelector(".site-header");
  const setHeaderHeight = () =>
    document.documentElement.style.setProperty("--header-h", `${siteHeader.offsetHeight}px`);
  setHeaderHeight();
  addEventListener("resize", setHeaderHeight);
}

// ---- Theme: light / dark / match-the-device, persisted -----------------
// The <head> bootstrap already applied the saved choice before first paint;
// this wires the header buttons and follows the OS while on "system".
{
  const THEME_KEY = "nekoTheme";
  const buttons = [...document.querySelectorAll(".theme-toggle button")];
  const systemDark = matchMedia("(prefers-color-scheme: dark)");
  const preference = () => {
    const saved = localStorage.getItem(THEME_KEY);
    return saved === "light" || saved === "dark" ? saved : "system";
  };
  const applyTheme = () => {
    const pref = preference();
    document.documentElement.dataset.theme =
      pref === "system" ? (systemDark.matches ? "dark" : "light") : pref;
    buttons.forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.setTheme === pref)));
  };
  for (const btn of buttons) {
    btn.addEventListener("click", () => {
      // "System" clears the override so the OS setting takes over again.
      if (btn.dataset.setTheme === "system") localStorage.removeItem(THEME_KEY);
      else localStorage.setItem(THEME_KEY, btn.dataset.setTheme);
      applyTheme();
    });
  }
  systemDark.addEventListener("change", applyTheme);
  applyTheme();
}

// ---- Cat popup: a unit's forms (icons) + a link to its wiki page ------
// Opened from any cat name (track / steps) or the ⓘ opener on collection/picker
// chips. Form icons are hotlinked per-form from battlecatsinfo's asset repo (via its
// GitHub Pages CDN); ones that 404 (unreleased units) just hide themselves.
const catPopup = document.getElementById("catPopup");
if (catPopup) {
  const ICON_BASE = "https://battlecatsinfo.github.io/img/u";
  const infoUrl = document.body.dataset.unitInfoUrl;
  const nameEl = catPopup.querySelector(".cat-popup-name");
  const rarityEl = catPopup.querySelector(".cat-popup-head .rarity");
  const formsEl = catPopup.querySelector(".cat-popup-forms");
  const wikiEl = catPopup.querySelector(".cat-popup-wiki");
  const cache = new Map(); // name -> Promise<info | null>

  const load = (name) => {
    if (!cache.has(name)) {
      cache.set(
        name,
        fetch(`${infoUrl}?name=${encodeURIComponent(name)}`)
          .then((r) => (r.ok ? r.json() : null))
          .then((d) => (d && d.found ? d : null))
          .catch(() => null),
      );
    }
    return cache.get(name);
  };

  async function openFor(name) {
    const info = await load(name);
    if (!info) return; // a cat not in the catalogue yet: no forms/wiki to show
    nameEl.textContent = info.name;
    rarityEl.textContent = info.rarity;
    rarityEl.dataset.rarity = info.rarity;
    rarityEl.hidden = !info.rarity;
    wikiEl.href = info.wiki;
    formsEl.replaceChildren();
    (info.forms || []).forEach((form, i) => {
      const fig = document.createElement("figure");
      fig.className = "cat-form";
      const img = document.createElement("img");
      img.loading = "lazy";
      img.alt = form;
      img.src = `${ICON_BASE}/${info.unit_id}/${i}.png`;
      img.addEventListener("error", () => fig.classList.add("no-icon"));
      const caption = document.createElement("figcaption");
      caption.textContent = form;
      fig.append(img, caption);
      formsEl.appendChild(fig);
    });
    if (!catPopup.open) catPopup.showModal();
  }

  document.addEventListener("click", (e) => {
    const trigger = e.target.closest(
      ".catlink[data-name], .catinfo[data-name], .cat-pill[data-name]",
    );
    if (!trigger) return;
    e.preventDefault();
    openFor(trigger.dataset.name);
  });
  // Close on the ×, or on a click in the backdrop (outside the dialog's box). Esc is
  // handled natively by showModal().
  catPopup.addEventListener("click", (e) => {
    const box = catPopup.getBoundingClientRect();
    const inside =
      e.clientX >= box.left &&
      e.clientX <= box.right &&
      e.clientY >= box.top &&
      e.clientY <= box.bottom;
    if (!inside || e.target.closest("[data-close]")) catPopup.close();
  });
}

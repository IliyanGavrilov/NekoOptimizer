// ---- Live search over a cat browser ----------------------------------
// <input data-filter="browserId"> filters chips (elements with data-name),
// hides rarity rows that end up empty, and auto-opens/closes <details> banners.
document.querySelectorAll("[data-filter]").forEach((input) => {
  const browser = document.getElementById(input.dataset.filter);
  if (!browser) return;

  input.addEventListener("input", () => {
    const query = input.value.trim().toLowerCase();
    browser.querySelectorAll("[data-name]").forEach((chip) => {
      chip.hidden = query !== "" && !chip.dataset.name.toLowerCase().includes(query);
    });
    browser.querySelectorAll("[data-rarity-row]").forEach((row) => {
      row.hidden = !row.querySelector("[data-name]:not([hidden])");
    });
    browser.querySelectorAll("details.banner-group").forEach((banner) => {
      const hasMatch = !!banner.querySelector("[data-name]:not([hidden])");
      banner.hidden = query !== "" && !hasMatch;
      if (query !== "") banner.open = hasMatch;
    });
  });
});

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
  const preferEl = document.getElementById("id_prefer");
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
        prefer: preferEl.value,
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
  const warnSlot = document.getElementById("targetsWarn");
  function reachablePks() {
    const pks = new Set();
    for (const btn of includes) {
      if (btn.getAttribute("aria-pressed") !== "true") continue;
      btn.closest(".banner-group").querySelectorAll(".chip[data-pk]").forEach((c) => pks.add(c.dataset.pk));
    }
    return pks;
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
    updateWarnings();
    save();
  }
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
  // Searching shows a flat, undivided list of matching cats; clearing it
  // restores the banner/rarity grouping.
  const search = document.getElementById("targetSearch");
  const searchClear = document.getElementById("targetSearchClear");
  const searchHint = document.getElementById("targetSearchHint");
  const grouped = browser;
  const flat = document.getElementById("targetFlat");
  function applySearch() {
    const query = search.value.trim().toLowerCase();
    const searching = query !== "";
    grouped.hidden = searching;
    flat.hidden = !searching;
    // While searching, surface a clear (x) button + hint so it's obvious how to
    // get back to the banner menu without manually deleting the query.
    searchClear.hidden = !searching;
    searchHint.hidden = !searching;
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
  if (stored.prefer != null) preferEl.value = stored.prefer;
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
  preferEl.addEventListener("change", save);
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
    btn.disabled = true;
    btn.textContent = "Applied ✓";
  });

  // ---- Live A/B tracks: reload whenever the seed or banner set changes ----
  // Needs a seed AND at least one selected banner; nothing selected => no track
  // (no implicit "current banners" fallback).
  let trackTimer;
  const anyBanner = () => includes.some((b) => b.getAttribute("aria-pressed") === "true");
  async function requestTracks() {
    // Changing the seed/banners invalidates any plan: drop back to browsing the rolls.
    solutions.innerHTML = "";
    browseTrack.hidden = false;
    if (!seedEl.value.trim() || !anyBanner()) {
      trackHost.innerHTML = "";
      resultsRegion.hidden = true;
      return;
    }
    const resp = await post(trackHost.dataset.tracksUrl);
    if (!resp.ok) return;
    trackHost.innerHTML = await resp.text();
    resultsRegion.hidden = !trackHost.firstElementChild;
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

// ---- Collection: instant owned / wishlist toggles --------------------
const collectionBrowser = document.getElementById("collectionBrowser");
if (collectionBrowser) {
  const url = collectionBrowser.dataset.toggleUrl;
  const token = document.getElementById("csrfToken").value;

  // One tap to wishlist every cat you don't own (completion play); the server marks
  // them, then we star every not-owned chip to match.
  const wishlistAll = document.getElementById("wishlistAll");
  if (wishlistAll) {
    wishlistAll.addEventListener("click", async () => {
      const resp = await fetch(wishlistAll.dataset.url, {
        method: "POST",
        headers: { "X-CSRFToken": token },
      });
      if (!resp.ok) return;
      collectionBrowser
        .querySelectorAll(".own-chip:not(.owned)")
        .forEach((chip) => chip.classList.add("wanted"));
    });
  }

  collectionBrowser.addEventListener("click", async (e) => {
    const own = e.target.closest(".chip-own");
    const star = e.target.closest(".chip-star");
    if (!own && !star) return;
    const chip = e.target.closest(".own-chip");
    const field = star ? "wanted" : "owned";

    const body = new URLSearchParams({ pk: chip.dataset.pk, field, csrfmiddlewaretoken: token });
    const resp = await fetch(url, {
      method: "POST",
      headers: { "X-CSRFToken": token },
      body,
    });
    if (!resp.ok) return;
    const state = await resp.json();
    // A cat can appear under several banners; update every copy.
    collectionBrowser
      .querySelectorAll(`.own-chip[data-pk="${chip.dataset.pk}"]`)
      .forEach((c) => {
        c.classList.toggle("owned", state.owned);
        c.classList.toggle("wanted", state.wanted);
      });
  });
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

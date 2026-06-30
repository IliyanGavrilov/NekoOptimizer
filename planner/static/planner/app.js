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
  // memory of catfood/tickets/targets/banners between visits). Seed and the
  // owned/wishlist collection persist server-side instead.
  const STORE_KEY = "nekoPlanner";
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
  function save() {
    if (!ready) return;
    const banners = includes
      .filter((b) => b.getAttribute("aria-pressed") === "true")
      .map((b) => b.dataset.banner);
    localStorage.setItem(
      STORE_KEY,
      JSON.stringify({
        tickets: ticketsEl.value,
        catfood: catfoodEl.value,
        useWishlist: wishlistEl.checked,
        prefer: preferEl.value,
        ticketValue: ticketValueEl.value,
        platLegendCap: platLegendCapEl.value,
        explore: exploreEl.checked,
        horizon: horizonEl.value,
        search: search.value,
        targets: [...selected.keys()],
        banners,
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
      input.value = btn.dataset.banner;
      bannerInputs.appendChild(input);
    }
    const n = bannerInputs.childElementCount;
    bannerCount.textContent = n
      ? `Rolling ${n} banner${n === 1 ? "" : "s"}.`
      : "Rolling current banners.";
    save();
  }
  // A "session" is a moment in time: clicking a banner selects every banner
  // live on its opening day - the rotation you'd roll together right then -
  // not everything its run overlaps. A whole-period event banner (or the
  // months-long Platinum/Legend capsules) overlaps dozens of distinct 3-day
  // rotations; anchoring on a single day keeps the session to ~the 3 featured
  // banners plus the always-on capsules instead of every overlapping banner.
  function toggleSession(btn) {
    const on = btn.getAttribute("aria-pressed") !== "true";
    const [day] = rangeOf(btn);
    for (const other of includes) {
      if (liveOn(rangeOf(other), day)) setIncluded(other, on);
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
  const grouped = browser;
  const flat = document.getElementById("targetFlat");
  function applySearch() {
    const query = search.value.trim().toLowerCase();
    const searching = query !== "";
    grouped.hidden = searching;
    flat.hidden = !searching;
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

  // Restore the saved form, then default whatever was never saved.
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

  for (const pk of stored.targets || []) {
    const chip = picker.querySelector(`.chip[data-pk="${pk}"]`);
    if (chip && !selected.has(pk)) {
      selected.set(pk, chip.dataset.name);
      chipsFor(pk).forEach((c) => c.classList.add("selected"));
    }
  }
  render();

  if (stored.search) {
    search.value = stored.search;
    applySearch();
  }

  // An empty list means "I cleared every banner"; only a never-saved session
  // falls back to whatever is live today.
  if (stored.banners) {
    const wanted = new Set(stored.banners);
    for (const btn of includes) setIncluded(btn, wanted.has(btn.dataset.banner));
  } else {
    const today = new Date().toISOString().slice(0, 10);
    for (const btn of includes) {
      if (liveOn(rangeOf(btn), today)) setIncluded(btn, true);
    }
  }
  ready = true;
  syncBanners();

  // ---- Apply a plan: own its cats, drop them from the wishlist, and spend
  // the plan's tickets/catfood from the saved budget.
  const planResults = document.getElementById("planResults");
  if (planResults) {
    const token = document.querySelector("[name=csrfmiddlewaretoken]").value;
    planResults.addEventListener("click", async (e) => {
      const btn = e.target.closest(".apply-plan");
      if (!btn || btn.disabled) return;
      const body = new URLSearchParams({ csrfmiddlewaretoken: token });
      (btn.dataset.cats ? btn.dataset.cats.split("|") : []).forEach((n) => body.append("cats", n));
      const resp = await fetch(planResults.dataset.applyUrl, {
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
  }
}

// ---- Planner: loading overlay ----------------------------------------
// The form is a blocking full-page POST; show a spinner from submit until the
// results page renders. Hide it on bfcache restore so the back button never
// lands on a stuck overlay.
const plannerForm = document.getElementById("plannerForm");
const planLoading = document.getElementById("planLoading");
if (plannerForm && planLoading) {
  plannerForm.addEventListener("submit", () => {
    planLoading.hidden = false;
  });
  window.addEventListener("pageshow", () => {
    planLoading.hidden = true;
  });
}

// ---- Collection: instant owned / wishlist toggles --------------------
const collectionBrowser = document.getElementById("collectionBrowser");
if (collectionBrowser) {
  const url = collectionBrowser.dataset.toggleUrl;
  const token = document.getElementById("csrfToken").value;

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

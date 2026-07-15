// ---- Follow-along: walk a plan's steps, lighting each on the track beside it -------
// Shared by the planner solutions and the Normal Capsules plan - both render a
// .plan-follow holding a .plan-steps card list and a .plan-track, with each step card
// and each lit track cell tagged data-step. Selecting a step lights its cells, dims the
// steps already done, and drops a "you are here" marker on its first cell. Until you
// pick one, the whole plan stays lit (the plain result) and nothing is dimmed.
function wireFollowAlong(root) {
  root.querySelectorAll(".plan-follow").forEach(setupFollowAlong);
}

function setupFollowAlong(follow) {
  if (follow.dataset.follow) return; // rendered fresh each time, but guard re-wiring
  follow.dataset.follow = "1";
  const cards = [...follow.querySelectorAll(".step-card")];
  const track = follow.querySelector(".plan-track");
  if (!cards.length || !track) return;
  const count = follow.querySelector(".step-count");
  const max = cards.length;
  let cur = 0; // 0 = the whole plan lit (overview); 1..max = walking that step

  const stepCells = (n) => track.querySelectorAll(`.entry[data-step="${n}"]`);

  const render = (scroll) => {
    cards.forEach((c) => {
      const n = Number(c.dataset.step);
      c.classList.toggle("is-current", n === cur);
      c.classList.toggle("is-done", cur > 0 && n < cur);
    });
    track.querySelectorAll(".entry[data-step]").forEach((e) => {
      const n = Number(e.dataset.step);
      e.classList.toggle("is-here", cur > 0 && n === cur);
      e.classList.toggle("is-done", cur > 0 && n < cur);
    });
    follow.querySelector(".step-here")?.remove();
    if (count) count.textContent = cur > 0 ? `${cur} / ${max}` : `${max} step${max === 1 ? "" : "s"}`;
    const first = cur > 0 ? stepCells(cur)[0] : null;
    if (first) {
      const pin = document.createElement("span");
      pin.className = "step-here";
      pin.textContent = "you are here";
      first.appendChild(pin);
      if (scroll) first.scrollIntoView({ block: "center", behavior: "smooth" });
    }
  };

  // cur clamps to [0, max]: 0 is the overview (whole plan lit, nothing dimmed), so
  // stepping back off step 1 - or hitting "show whole plan" - returns to it.
  const setStep = (n, scroll) => {
    cur = Math.max(0, Math.min(max, n));
    render(scroll);
  };

  follow.addEventListener("click", (e) => {
    const card = e.target.closest(".step-card");
    if (card) {
      const n = Number(card.dataset.step);
      // Click the current step again to deselect - back to the whole plan lit.
      return setStep(n === cur ? 0 : n, n !== cur);
    }
    if (e.target.closest(".step-prev")) return setStep(cur - 1, true);
    if (e.target.closest(".step-next")) return setStep(cur + 1, true);
  });

  render(false);
}

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
  const platCapEl = document.getElementById("id_platinum_cap");
  const legendCapEl = document.getElementById("id_legend_cap");
  const exploreEl = document.getElementById("id_explore");
  const horizonEl = document.getElementById("id_horizon");
  const trackLengthEl = document.getElementById("id_track_length");
  const detailsToggleEl = document.getElementById("detailsToggle");
  const simGuaranteedEl = document.getElementById("simGuaranteed");
  const excludeGuaranteedEl = document.getElementById("excludeGuaranteed");
  const findGuaranteedCtl = document.querySelector(".find-guaranteed-ctl");
  const rollDisplayEl = document.getElementById("rollDisplay");
  const rollFormEl = document.getElementById("rollForm");
  const horizonRow = document.querySelector(".explore-horizon");
  const budgetFields = document.querySelector(".budget-fields");
  // The "Your resources" section by the plan button: rare/catfood budget always, plus
  // the Platinum/Legend rows when that capsule banner is selected.
  const resourcesSection = document.getElementById("resources");
  const capsuleFields = document.getElementById("capsuleFields");
  const platRow = document.getElementById("platRow");
  const legendRow = document.getElementById("legendRow");
  const stored = (() => {
    try {
      return JSON.parse(localStorage.getItem(STORE_KEY)) || {};
    } catch {
      return {};
    }
  })();
  // A shared permalink (?seed=...) reopens your seed + Rolls view - the seed and the
  // display controls (rolls-to-show / names-icons-both / form / details), nothing else.
  // Banners aren't in it: the page opens on today's live banners and you adjust them.
  const linkParams = new URLSearchParams(location.search);
  const fromLink = linkParams.has("seed");
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
        platCap: platCapEl.value,
        legendCap: legendCapEl.value,
        explore: exploreEl.checked,
        horizon: horizonEl.value,
        // The Rolls-table display controls (rolls-to-show, details, guaranteed,
        // future ubers) are deliberately NOT persisted - each visit starts at the
        // defaults (100 rolls, no details, guaranteed off, no future ubers).
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
    // Targets double as "Find next" cats on the browse track - refresh its found list
    // (only while browsing; a shown plan keeps its own tracks).
    if (browseTrack && !browseTrack.hidden) scheduleTracks();
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
    if (n === 0) sessionDayAnchor = null; // nothing selected -> the next pick sets the time
    bannerWarn.hidden = true; // a valid change clears any capsule-mismatch warning
    locateIdx = 0;
    syncBannerChips();
    syncResources();
    updateWarnings();
    save();
  }
  // Whether a selected banner is a Platinum / a Legend capsule run: each capsule's
  // ticket field shows only when its own banner is in the selection.
  const PLAT = /platinum capsules/i;
  const LEG = /legend capsules/i;
  function selectedCapsule(re) {
    return includes.some(
      (btn) => btn.getAttribute("aria-pressed") === "true" && re.test(btn.dataset.banner),
    );
  }
  // The "Your resources" section: rare/catfood budget hides in explore mode, and each
  // capsule row shows only when its banner is selected (regardless of explore mode, since
  // capsule tickets are always budget-scarce). The whole section hides when nothing shows.
  function syncResources() {
    const platOn = selectedCapsule(PLAT);
    const legOn = selectedCapsule(LEG);
    platRow.hidden = !platOn;
    legendRow.hidden = !legOn;
    capsuleFields.hidden = !(platOn || legOn);
    if (budgetFields) budgetFields.hidden = exploreEl.checked;
    resourcesSection.hidden = (!budgetFields || budgetFields.hidden) && capsuleFields.hidden;
  }
  // One chip per selected banner under the hint, labelled with the banner's set
  // title; clicking a chip scrolls the picker to that banner.
  const bannerChips = document.getElementById("bannerChips");
  const bannerWarn = document.getElementById("bannerWarn");
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
  // of a session, and each toggles on its own. Match the ticket-capsule PHRASE, not a
  // bare "legend"/"platinum" - ordinary banners (Evangelion's "Limited Legend", the
  // fests' "Legend Rare drop rate") mention the word without being capsule runs.
  const CAPPED = /platinum capsules|legend capsules/i;
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
  // The day the current selection sits on. A capsule can only join a session it was
  // actually live during, so every selected banner (regular or capsule) shares this day.
  let sessionDayAnchor = null;
  function rejectCapsule(group) {
    bannerWarn.textContent =
      "That Platinum/Legend Capsules run wasn't live during the selected banners' time. " +
      "Pick the run that overlaps them, or clear the selection first.";
    bannerWarn.hidden = false;
    group.classList.remove("flash-blocked");
    void group.offsetWidth; // restart the pulse on a repeat click
    group.classList.add("flash-blocked");
  }
  // Click an unselected banner -> select that banner's time period (every other
  // non-capsule banner live on its session day), replacing whatever period was
  // selected before. Click a selected banner -> unselect just that one. Capsules are
  // opt-in, toggled individually - but only the run live during the selected session,
  // so you can't pair an upcoming banner with a stale (or future) capsule run.
  function toggleSession(btn) {
    const range = rangeOf(btn);
    if (btn.getAttribute("aria-pressed") === "true") {
      setIncluded(btn, false);
    } else if (CAPPED.test(btn.dataset.banner)) {
      const day = sessionDayAnchor ?? sessionDay(range);
      if (!liveOn(range, day)) return rejectCapsule(btn.closest(".banner-group"));
      sessionDayAnchor ??= day; // a lone capsule sets the session's time itself
      setIncluded(btn, true);
    } else {
      const day = sessionDay(range);
      sessionDayAnchor = day;
      for (const other of includes) {
        const on = liveOn(rangeOf(other), day);
        // Regulars: the whole concurrent session. Capsules: keep only if still live now,
        // dropping a capsule left over from a different period.
        if (!CAPPED.test(other.dataset.banner)) setIncluded(other, on);
        else if (!on) setIncluded(other, false);
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
      // Cats match on any of their form names, not just the base one.
      flat.querySelectorAll("[data-name]").forEach((chip) => {
        chip.hidden = !(chip.dataset.forms || chip.dataset.name).toLowerCase().includes(query);
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

  // Restore the saved form, then default whatever was never saved. A permalink
  // overrides only the seed here (its view controls are applied further down); the
  // budget/options still come from your saved form, since a link reopens a view, not
  // a whole plan.
  if (stored.seed != null && stored.seed !== "") seedEl.value = stored.seed;
  if (stored.tickets != null) ticketsEl.value = stored.tickets;
  if (stored.catfood != null) catfoodEl.value = stored.catfood;
  wishlistEl.checked = !!stored.useWishlist;
  if (stored.ticketValue != null) ticketValueEl.value = stored.ticketValue;
  if (stored.platCap != null) platCapEl.value = stored.platCap;
  if (stored.legendCap != null) legendCapEl.value = stored.legendCap;
  if (stored.explore != null) exploreEl.checked = stored.explore; // else keep server default (on)
  if (stored.horizon != null) horizonEl.value = stored.horizon;
  if (fromLink) seedEl.value = linkParams.get("seed");
  // The Rolls display controls (rolls-to-show / details) keep their HTML defaults
  // here; the display mode and form restore from localStorage below. A permalink
  // overrides any of them for its one opening (see the fromLink block after them).
  const syncExplore = () => {
    horizonRow.hidden = !exploreEl.checked;
    syncResources(); // explore hides the rare/catfood budget; capsule rows stay banner-driven
  };
  syncExplore();
  ticketsEl.addEventListener("input", save);
  catfoodEl.addEventListener("input", save);
  wishlistEl.addEventListener("change", () => {
    save();
    // The wishlist feeds the browse "Find next" list too (when "search my wishlist" is on).
    if (browseTrack && !browseTrack.hidden) scheduleTracks();
  });
  ticketValueEl.addEventListener("input", save);
  platCapEl.addEventListener("input", save);
  legendCapEl.addEventListener("input", save);
  exploreEl.addEventListener("change", () => {
    syncExplore();
    save();
  });
  horizonEl.addEventListener("input", save);
  // Changing how many rolls to show only affects the Rolls table, so re-fetch it.
  // (Wrapped so the reference to scheduleTracks - declared below - resolves at call time.)
  trackLengthEl.addEventListener("input", () => {
    scheduleTracks();
    syncUrlIfLinked();
  });
  // Simulating a guaranteed multi changes the server-side roll, so re-fetch the table.
  simGuaranteedEl.addEventListener("change", () => scheduleTracks());
  // Skipping the guaranteed column changes which positions "Find next" reports.
  excludeGuaranteedEl.addEventListener("change", () => scheduleTracks());

  render();

  // Targets and banner selection aren't persisted: every visit starts from the
  // banners live today (capsules excluded - they're opt-in) and no targets. A
  // permalink opens here too - it carries only a seed + view, never a banner set.
  sessionDayAnchor = today(); // the default selection sits on today
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

  // ---- Details view: reveal each cell's raw RNG seeds -------------------
  // Pure display toggle (the seeds are always in the rendered cells, hidden by
  // CSS), so it just flips a class on the results region - no re-fetch needed,
  // and it covers both the browse track and any solution's track.
  const syncDetails = () => resultsRegion.classList.toggle("details", detailsToggleEl.checked);
  syncDetails();
  detailsToggleEl.addEventListener("change", () => {
    syncDetails();
    syncUrlIfLinked();
  });

  // ---- Rolls display mode: names / form icons / both -------------------
  // The icons are hotlinked per-cell from battlecatsinfo (like the cat popup), so we
  // only inject them once a mode that shows them is picked - text mode stays image-free.
  // Each cell carries its catalogue id (data-uid); loading="lazy" keeps off-screen rows
  // from fetching, and identical cats share one cached URL. The form picker chooses
  // WHICH form shows, icon AND name (godfat's name=N): a unit without the picked form
  // steps down to the last one it has (404s are remembered, so a re-pick never
  // re-probes), and a cell with no icon at all (an uncatalogued unit) keeps its name.
  const ICON_BASE = "https://battlecatsinfo.github.io/img/u";
  const missingIcons = new Set(); // "uid/form" pairs that 404'd
  const bestForm = (uid, form) => {
    while (form > 0 && missingIcons.has(`${uid}/${form}`)) form -= 1;
    return form;
  };
  const setIconForm = (btn, img) => {
    const uid = btn.dataset.uid;
    const form = bestForm(uid, Number(rollFormEl.value));
    if (missingIcons.has(`${uid}/${form}`)) {
      btn.classList.add("no-icon");
      return;
    }
    if (img.dataset.form === String(form)) return;
    img.dataset.form = form;
    btn.classList.remove("no-icon");
    img.src = `${ICON_BASE}/${uid}/${form}.png`;
  };
  const injectIcons = (root) => {
    root.querySelectorAll(".entry > .catlink[data-uid]").forEach((btn) => {
      let img = btn.querySelector(".cat-icon");
      if (!img) {
        img = document.createElement("img");
        img.className = "cat-icon";
        img.loading = "lazy";
        img.alt = "";
        img.addEventListener("error", () => {
          missingIcons.add(`${btn.dataset.uid}/${img.dataset.form}`);
          setIconForm(btn, img); // step down a form, or give up to the name
        });
        btn.prepend(img);
      }
      setIconForm(btn, img);
    });
  };
  // Unlike the other Rolls controls (which reset each visit by request), the display
  // mode and icon form are persisted preferences - restore the last picks before the
  // first render.
  const restorePick = (el, key) => {
    const saved = localStorage.getItem(key);
    if (saved && [...el.options].some((o) => o.value === saved)) el.value = saved;
  };
  const ROLL_DISPLAY_KEY = "neko:rollDisplay";
  const ROLL_FORM_KEY = "neko:rollForm";
  restorePick(rollDisplayEl, ROLL_DISPLAY_KEY);
  restorePick(rollFormEl, ROLL_FORM_KEY);
  // Renaming needs each unit's form names: they come down once, lazily, the first
  // time a non-base form is picked. Cells re-rendered later just reuse the map.
  let formNames = null; // {unit_id: [form names]}, null until fetched
  let formNamesRequest = null;
  const loadFormNames = () => {
    formNamesRequest =
      formNamesRequest ||
      fetch(document.body.dataset.unitFormsUrl)
        .then((r) => (r.ok ? r.json() : {}))
        .catch(() => ({}))
        .then((names) => {
          formNames = names;
          applyFormNames(resultsRegion); // rename the cells already on screen
        });
  };
  const applyFormNames = (root) => {
    const form = Number(rollFormEl.value);
    if (form > 0 && formNames === null) loadFormNames();
    root.querySelectorAll(".entry > .catlink[data-uid] > .catname").forEach((span) => {
      const btn = span.parentElement;
      const forms = form > 0 && formNames ? formNames[btn.dataset.uid] : null;
      span.textContent =
        forms && forms.length ? forms[Math.min(form, forms.length - 1)] : btn.dataset.name;
    });
  };
  const syncRollDisplay = () => {
    const mode = rollDisplayEl.value;
    resultsRegion.classList.toggle("rolls-icons", mode === "icons");
    resultsRegion.classList.toggle("rolls-both", mode === "both");
    if (mode !== "text") injectIcons(resultsRegion);
    applyFormNames(resultsRegion);
  };
  syncRollDisplay();
  rollDisplayEl.addEventListener("change", () => {
    localStorage.setItem(ROLL_DISPLAY_KEY, rollDisplayEl.value);
    syncRollDisplay();
    syncUrlIfLinked();
  });
  rollFormEl.addEventListener("change", () => {
    localStorage.setItem(ROLL_FORM_KEY, rollFormEl.value);
    syncRollDisplay();
    syncUrlIfLinked();
  });

  // A permalink's view wins over the saved display picks for this one opening (it
  // doesn't overwrite them in localStorage - your usual preferences stay put).
  if (fromLink) {
    if (linkParams.has("rolls")) trackLengthEl.value = linkParams.get("rolls");
    if (linkParams.has("display")) rollDisplayEl.value = linkParams.get("display");
    if (linkParams.has("form")) rollFormEl.value = linkParams.get("form");
    detailsToggleEl.checked = linkParams.get("details") === "1";
    syncDetails();
    syncRollDisplay();
  }

  // The Rolls-table display controls live outside the form (they sit with the table),
  // so fold their current values into every roll/plan post.
  const post = (url) => {
    const body = new FormData(plannerForm);
    body.set("track_length", trackLengthEl.value);
    body.set("simulate_guaranteed", simGuaranteedEl.value);
    body.set("exclude_guaranteed", excludeGuaranteedEl.checked ? "1" : "0");
    // Future-uber padding is per banner: each legend stepper covers the run names of
    // the banner group it sits on (the server re-renders the values it applied).
    const future = {};
    trackHost.querySelectorAll(".future-ubers").forEach((input) => {
      const count = Math.max(0, Math.min(99, Number(input.value) || 0));
      for (const name of JSON.parse(input.dataset.names)) future[name] = count;
    });
    body.set("future_ubers", JSON.stringify(future));
    if (traceState) {
      body.set("trace_tag", traceState.tag);
      body.set("trace_idx", traceState.idx);
      if (traceState.guaranteed) body.set("trace_guaranteed", "1");
    }
    return fetch(url, { method: "POST", body, headers: { "X-CSRFToken": token } });
  };

  // ---- Shareable permalink: your seed + Rolls view as a URL -------------------
  // Just the seed and the display controls; everything at its default stays out, so
  // links stay short. Banners/targets/budget are deliberately absent - a link reopens
  // a view, not a plan. Opening one applies these in the fromLink blocks above.
  const permalink = () => {
    const p = new URLSearchParams();
    p.set("seed", seedEl.value.trim());
    if (trackLengthEl.value !== trackLengthEl.defaultValue) p.set("rolls", trackLengthEl.value);
    if (rollDisplayEl.value !== "text") p.set("display", rollDisplayEl.value);
    if (rollFormEl.value !== "0") p.set("form", rollFormEl.value);
    if (detailsToggleEl.checked) p.set("details", "1");
    return `${location.pathname}?${p}`;
  };

  // Once a permalink is in the address bar (opened, or copied via the button), keep
  // it matching the current seed + view as you tweak them, so a bookmark or re-copy
  // is always current. Fresh visits with a clean URL stay clean until Copy link.
  const syncUrlIfLinked = () => {
    if (location.search) history.replaceState(null, "", permalink());
  };

  // "Copy link" beside Find plan: copy the permalink straight to the clipboard, and
  // drop it in the address bar too (so it's still shareable if the clipboard API is
  // blocked - e.g. over plain HTTP).
  const copyToClipboard = async (text) => {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.cssText = "position:fixed;top:0;left:0;opacity:0";
      document.body.appendChild(ta);
      ta.select();
      let ok = false;
      try {
        ok = document.execCommand("copy");
      } catch {
        ok = false;
      }
      ta.remove();
      return ok;
    }
  };
  const shareLink = document.getElementById("shareLink");
  let shareTimer;
  shareLink.addEventListener("click", async () => {
    const url = new URL(permalink(), location.href).href;
    history.replaceState(null, "", url);
    const copied = await copyToClipboard(url);
    shareLink.textContent = copied ? "Link copied ✓" : "Link is in the address bar";
    clearTimeout(shareTimer);
    shareTimer = setTimeout(() => (shareLink.textContent = "Copy link"), 2000);
  });

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
    spend(platCapEl, "platinum"); // capsule tickets are their own pools; spend them too
    spend(legendCapEl, "legend");
    save();
    // "You rolled it": the seed advances to just after the plan's final draw. The
    // solution stays on screen (its steps still need doing in game), and the Rolls
    // track re-rolls from the new seed so it shows what comes next.
    if (btn.dataset.seedAfter) {
      setSeed(btn.dataset.seedAfter, btn.dataset.lastCat || "");
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
  let traceState = null; // the traced cell, kept only across its own re-render
  let pendingFind = null; // a "Find next" position to scroll to once the table re-renders
  const anyBanner = () => includes.some((b) => b.getAttribute("aria-pressed") === "true");
  // The banner legend sticks under the site header; the sticky thead sits just below it,
  // so measure the visible legend's height into --legend-h whenever a track is (re)rendered.
  const setLegendHeight = () => {
    const legend = [...document.querySelectorAll(".track-legend")].find((el) => el.offsetParent);
    document.documentElement.style.setProperty("--legend-h", legend ? `${legend.offsetHeight}px` : "0px");
  };
  addEventListener("resize", setLegendHeight);
  async function refreshTracks(keepTrace = false) {
    // Any refresh besides a trace click means the rolls changed: drop the trace.
    if (!keepTrace) traceState = null;
    if (!seedEl.value.trim() || !anyBanner()) {
      trackHost.innerHTML = "";
      resultsRegion.hidden = !solutions.firstElementChild;
      return;
    }
    const resp = await post(trackHost.dataset.tracksUrl);
    if (!resp.ok) return;
    trackHost.innerHTML = await resp.text();
    resultsRegion.hidden = !trackHost.firstElementChild;
    // These steppers are (re)rendered with the fragment, so wire up drag-to-scrub
    // each time - the page-load pass never saw them.
    trackHost.querySelectorAll(".future-ubers").forEach(scrubNumberInput);
    syncRollDisplay(); // re-inject icons if the fresh cells need them
    setLegendHeight();
    // "Skip guaranteed in Find" only makes sense when the track has guaranteed columns.
    if (findGuaranteedCtl) findGuaranteedCtl.hidden = !trackHost.querySelector(".guaranteed-col");
    // A Find-position click that had to grow the table scrolls once the rows are here.
    if (pendingFind) {
      const { idx, guaranteed } = pendingFind;
      pendingFind = null;
      scrollToFind(idx, guaranteed);
    }
  }
  // Scroll the browse track to a found cat's cell and flash it. When the position sits past
  // the rows on screen, first grow "Show N rolls" to reach it (the seed is rolled deep
  // server-side, but only N rows render), then scroll once the fresh table arrives.
  function scrollToFind(idx, guaranteed) {
    const pos = Math.floor(idx / 2) + 1;
    if (pos > Number(trackLengthEl.value)) {
      trackLengthEl.value = Math.min(pos, 999);
      pendingFind = { idx, guaranteed };
      requestTracks();
      return;
    }
    const tbody = trackHost.querySelector(".track tbody");
    const row = tbody && tbody.children[pos - 1];
    if (!row) return;
    const sel = guaranteed ? "td.cell.guaranteed-col" : "td.cell:not(.guaranteed-col)";
    const cell = row.querySelectorAll(sel)[idx & 1 ? 1 : 0] || row;
    cell.scrollIntoView({ behavior: "smooth", block: "center" });
    cell.classList.remove("flash-locate");
    void cell.offsetWidth; // restart the pulse on a repeat click
    cell.classList.add("flash-locate");
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
    // A hand-typed seed may be one the app has visited before (copied back from
    // notes, say) - restore its remembered pull so dupes still flag.
    applyLastCat(seedEl.value.trim(), "");
    syncBack();
    save();
    scheduleTracks();
    syncUrlIfLinked();
  });
  browser.addEventListener("click", (e) => {
    if (e.target.closest(".banner-include")) scheduleTracks();
  });
  // The per-banner future-ubers steppers live inside the server-rendered legend, so
  // listen on the host; changing one re-rolls the table with the new padding.
  trackHost.addEventListener("input", (e) => {
    if (e.target.closest(".future-ubers")) scheduleTracks();
  });
  // "Find next" position chip: scroll the track to that cell (growing the table first if
  // the position is past what's on screen).
  trackHost.addEventListener("click", (e) => {
    const chip = e.target.closest(".find-pos");
    if (chip) scrollToFind(Number(chip.dataset.idx), chip.dataset.guaranteed === "1");
  });

  // ---- Click-to-trace: plan-style marks for the rolls UP TO a cell --------
  // godfat's pick(): click a banner's line (its name-free space - names open the
  // popup, dice jump the seed) and the server re-renders the table with the walk
  // from 1A to that cell lit exactly like a plan: gold pill on the cell, and the
  // shared dashes on other banners that could roll a step without changing the
  // path. Clicking the same line again clears it.
  trackHost.addEventListener("click", (e) => {
    if (e.target.closest("button, a, input, label, .arrow")) return;
    const entry = e.target.closest(".entry");
    if (!entry || !entry.dataset.idx) return;
    // A guaranteed-column click traces the uber that column's multi would award instead.
    const guaranteed = !!entry.closest(".guaranteed-col");
    const same =
      traceState &&
      traceState.tag === entry.dataset.tag &&
      traceState.idx === entry.dataset.idx &&
      traceState.guaranteed === guaranteed;
    traceState = same ? null : { tag: entry.dataset.tag, idx: entry.dataset.idx, guaranteed };
    refreshTracks(true);
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
  // Dupe memory: what the pull just before each visited seed obtained. A dice jump
  // or applied plan knows what it rolled, so remember it per seed - landing on a
  // seed any way at all (dice, undo, retyping it, a reload) then restores the cat,
  // and the server can dupe a first cell repeating it. Recency-capped pairs, not a
  // plain object: seeds are numeric keys, which objects reorder.
  const SEED_CATS_KEY = "nekoSeedCats";
  const lastCatEl = document.getElementById("lastCat");
  const seedCats = (() => {
    try {
      return JSON.parse(localStorage.getItem(SEED_CATS_KEY)) || [];
    } catch {
      return [];
    }
  })();
  const recallCat = (seed) => (seedCats.find(([s]) => s === String(seed)) || [])[1] || "";
  // Set the dupe memory for a seed just landed on: the cat its jump obtained when
  // known, else whatever an earlier visit recorded for that seed.
  function applyLastCat(seed, cat) {
    if (cat) {
      const idx = seedCats.findIndex(([s]) => s === String(seed));
      if (idx !== -1) seedCats.splice(idx, 1);
      seedCats.push([String(seed), cat]);
      while (seedCats.length > 200) seedCats.shift();
      localStorage.setItem(SEED_CATS_KEY, JSON.stringify(seedCats));
    }
    lastCatEl.value = cat || recallCat(seed);
  }
  function syncUndo() {
    seedUndo.hidden = undoStack.length === 0;
    if (undoStack.length) seedUndo.title = `Back to seed ${undoStack[undoStack.length - 1]}`;
  }
  function setSeed(value, cat) {
    const prev = seedEl.value.trim();
    if (prev && prev !== String(value)) {
      undoStack.push(prev);
      while (undoStack.length > 50) undoStack.shift();
      localStorage.setItem(UNDO_KEY, JSON.stringify(undoStack));
    }
    seedEl.value = value;
    applyLastCat(value, cat || "");
    syncUndo();
    save();
  }
  seedUndo.addEventListener("click", () => {
    if (!undoStack.length) return;
    seedEl.value = undoStack.pop();
    localStorage.setItem(UNDO_KEY, JSON.stringify(undoStack));
    applyLastCat(seedEl.value, "");
    syncUndo();
    save();
    requestTracks();
  });
  // Seed dice (browsing or inside a solution). Two kinds share the handler, each
  // carrying its seed in data-seed: a cell's docked dice re-anchors so that cell is
  // the next pull; an inline dice beside a cat (either branch of a dupe reroll, or a
  // guaranteed multi's award) jumps to just AFTER obtaining it.
  resultsRegion.addEventListener("click", (e) => {
    const btn = e.target.closest(".reseed");
    if (!btn) return;
    setSeed(btn.dataset.seed, btn.dataset.cat || "");
    requestTracks();
  });
  syncUndo();

  // ---- Backtrack: step the seed back one roll (godfat's Backtrack) --------
  // Inverting the RNG is Python's job (one source of truth for the stream), so
  // ask the server for the earlier seed, then land on it like any app-made seed
  // change - onto the undo stack, dupe memory cleared (the pull before is now
  // unknown). Enabled only when there's a seed to step back from.
  const seedBack = document.getElementById("seedBack");
  const syncBack = () => (seedBack.disabled = !seedEl.value.trim());
  seedBack.addEventListener("click", async () => {
    const seed = seedEl.value.trim();
    if (!seed) return;
    const body = new URLSearchParams({ seed, csrfmiddlewaretoken: token });
    const resp = await fetch(trackHost.dataset.backtrackUrl, {
      method: "POST",
      headers: { "X-CSRFToken": token },
      body,
    });
    if (!resp.ok) return;
    setSeed(String((await resp.json()).seed), "");
    requestTracks();
  });
  syncBack();

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
    platinum_cap: ["submitError", platCapEl],
    legend_cap: ["submitError", legendCapEl],
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
        syncRollDisplay(); // the solution tracks carry icons too
        wireFollowAlong(solutions); // step list + track walk together
        setLegendHeight();
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

  // A seed on load - restored from your form or handed in by a permalink - restores
  // its remembered pull and browses its rolls straight away. Banners are whatever's
  // live today. A link can also carry the pull that landed on its seed (the Seed
  // Finder's "open at your position" does): record it as the dupe memory.
  if (seedEl.value.trim()) {
    applyLastCat(seedEl.value.trim(), (fromLink && linkParams.get("last")) || "");
    requestTracks();
  }
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
  const statusBtns = [...document.querySelectorAll("#statusFilter button")];
  // Ownership filter: "wishlist" means still-wanted, so it drops cats you own -
  // matching how the planner reads the wishlist (owned cats are never on it).
  const statusHit = (chip, status) =>
    status === "owned"
      ? chip.classList.contains("owned")
      : status === "wishlist"
        ? chip.classList.contains("wanted") && !chip.classList.contains("owned")
        : true;
  function applyFilters() {
    const query = search.value.trim().toLowerCase();
    const rarity = rarityBtns.find((b) => b.getAttribute("aria-pressed") === "true").dataset.rarity;
    const status = statusBtns.find((b) => b.getAttribute("aria-pressed") === "true").dataset.status;
    // Any active filter overrides a section's collapsed state, so matches can't
    // hide inside a folded-up section.
    collectionBrowser.classList.toggle("filtering", !!(query || rarity || status));
    const active = views.find((v) => !v.hidden);
    for (const section of active.querySelectorAll(".collection-section")) {
      // A query matching the section itself (a set or rarity name) keeps it whole.
      const labelHit = !!query && section.dataset.label.toLowerCase().includes(query);
      for (const row of section.querySelectorAll(".rarity-row")) {
        let shown = 0;
        const rarityHidesRow = rarity && row.dataset.rarity !== rarity;
        row.querySelectorAll(".own-chip").forEach((chip) => {
          // Match on any form name (data-forms carries them all), so "Mohawk"
          // finds the Cat whatever form the picker is showing.
          const names = chip.dataset.forms || chip.dataset.name;
          const hit =
            !rarityHidesRow &&
            (!query || labelHit || names.toLowerCase().includes(query)) &&
            statusHit(chip, status);
          chip.hidden = !hit;
          shown += hit;
        });
        row.hidden = shown === 0;
      }
      section.hidden = !section.querySelector(".rarity-row:not([hidden])");
    }
    noMatches.hidden = !!active.querySelector(".collection-section:not([hidden])");
  }
  search.addEventListener("input", applyFilters);
  const bindFilter = (id, btns) =>
    document.getElementById(id).addEventListener("click", (e) => {
      const btn = e.target.closest("button");
      if (!btn) return;
      btns.forEach((b) => b.setAttribute("aria-pressed", b === btn ? "true" : "false"));
      applyFilters();
    });
  bindFilter("rarityFilter", rarityBtns);
  bindFilter("statusFilter", statusBtns);

  // "12 / 325 owned" per section header plus one grand total, both ignoring
  // filters and refreshed on every change. The grand total counts each unit once
  // by reading only the rarity view (every cat lives in exactly one rarity bin).
  const totalEl = document.getElementById("collectionTotal");
  const rarityView = views.find((v) => v.dataset.view === "rarity");
  function updateCounts() {
    for (const section of sections) {
      const total = section.querySelectorAll(".own-chip").length;
      const owned = section.querySelectorAll(".own-chip.owned").length;
      section.querySelector(".owned-count").textContent = `${owned} / ${total} owned`;
    }
    const chips = [...rarityView.querySelectorAll(".own-chip")];
    const owned = chips.filter((c) => c.classList.contains("owned")).length;
    const wished = chips.filter((c) => c.classList.contains("wanted") && !c.classList.contains("owned")).length;
    totalEl.textContent = `${owned} / ${chips.length} owned${wished ? ` · ${wished} wishlisted` : ""}`;
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
    // The bulk own/wishlist buttons live in the header; let them win before the
    // header-wide collapse click below claims the rest of the bar.
    const bulk = e.target.closest(".bulk-own, .bulk-star");
    if (bulk) return bulkToggle(bulk);
    // Clicking anywhere else on a section header (label, count, chevron) folds it.
    const header = e.target.closest(".collection-section > h3");
    if (header) {
      const section = header.closest(".collection-section");
      const open = section.classList.toggle("collapsed");
      header.querySelector(".section-toggle").setAttribute("aria-expanded", !open);
      return;
    }
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
  // already is. The server decides which way it goes; bulk star hits every cat,
  // owned included, so it matches tapping each star by hand.
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
    const other = field === "owned" ? "wanted" : "owned";
    for (const chip of chips) {
      mark(chip.dataset.pk, { [field]: value, [other]: chip.classList.contains(other) });
    }
    updateCounts();
  }

  // Import/export. Export is a plain download link; import uploads a snapshot and
  // replaces every mark, so it confirms first and reloads to show the restored state.
  const importBtn = document.getElementById("collectionImport");
  const importFile = document.getElementById("collectionImportFile");
  const ioMsg = document.getElementById("collectionIoMsg");
  const showIoMsg = (text) => {
    ioMsg.textContent = text;
    ioMsg.hidden = false;
  };
  importBtn.addEventListener("click", () => importFile.click());
  importFile.addEventListener("change", async () => {
    const file = importFile.files[0];
    if (!file) return;
    const ok = confirm(
      "Replace your collection with this file? Your current owned and wishlist marks will be overwritten.",
    );
    importFile.value = "";
    if (!ok) return;
    const body = new FormData();
    body.append("file", file);
    const resp = await fetch(collectionBrowser.dataset.importUrl, {
      method: "POST",
      headers: { "X-CSRFToken": token },
      body,
    });
    if (!resp.ok) return showIoMsg("Import failed — that isn't a Neko collection file.");
    const { owned, wanted, missing } = await resp.json();
    const skipped = missing.length ? `, ${missing.length} not in the catalogue` : "";
    showIoMsg(`Imported ${owned} owned, ${wanted} wishlisted${skipped}. Reloading…`);
    location.reload();
  });

  // Form picker: every chip renames to the picked form. It shares the Rolls table's
  // persisted pick, so the whole site shows cats the same way.
  const formSel = document.getElementById("collectionForm");
  const saved = localStorage.getItem("neko:rollForm");
  if (saved && [...formSel.options].some((o) => o.value === saved)) formSel.value = saved;
  const applyForm = () => {
    const form = Number(formSel.value);
    collectionBrowser.querySelectorAll(".own-chip").forEach((chip) => {
      const forms = chip.dataset.forms ? chip.dataset.forms.split("|") : [];
      chip.querySelector(".catname").textContent = forms.length
        ? forms[Math.min(form, forms.length - 1)]
        : chip.dataset.name;
    });
  };
  applyForm();
  formSel.addEventListener("change", () => {
    localStorage.setItem("neko:rollForm", formSel.value);
    applyForm();
  });

  updateCounts();
  const savedView = localStorage.getItem(VIEW_KEY);
  showView(savedView === "sets" ? "sets" : "rarity");
}

// ---- Tier list: the form picker renames each unit and swaps its icon ----
// Same persisted pick as the Rolls table and Collection; an icon a unit doesn't
// have (404) falls back to its base form's.
const tierTable = document.querySelector(".tier-table");
if (tierTable) {
  const ICON_BASE = "https://battlecatsinfo.github.io/img/u";
  const formSel = document.getElementById("tierForm");
  const saved = localStorage.getItem("neko:rollForm");
  if (saved && [...formSel.options].some((o) => o.value === saved)) formSel.value = saved;
  tierTable.querySelectorAll(".tier-unit[data-uid] img").forEach((img) => {
    img.addEventListener("error", () => {
      const base = `${ICON_BASE}/${img.closest(".tier-unit").dataset.uid}/0.png`;
      if (!img.src.endsWith("/0.png")) img.src = base;
    });
  });
  const applyForm = () => {
    const form = Number(formSel.value);
    tierTable.querySelectorAll(".tier-unit[data-uid]").forEach((btn) => {
      const forms = (btn.dataset.forms || "").split("|").filter(Boolean);
      const index = forms.length ? Math.min(form, forms.length - 1) : 0;
      btn.querySelector(".tier-unit-name").textContent = forms[index] || btn.dataset.name;
      const src = `${ICON_BASE}/${btn.dataset.uid}/${index}.png`;
      const img = btn.querySelector("img");
      if (img && !img.src.endsWith(`/${index}.png`)) img.src = src;
    });
  };
  applyForm();
  formSel.addEventListener("change", () => {
    localStorage.setItem("neko:rollForm", formSel.value);
    applyForm();
  });
}

// ---- Drag-to-scrub number inputs -------------------------------------
// Click-drag up/down anywhere on a number field to step it up/down; a plain
// click (no vertical movement) still focuses the field for typing. Exposed so
// the AJAX-rendered future-ubers steppers can be wired up as they arrive.
const PX_PER_STEP = 7;
function scrubNumberInput(input) {
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
}
document.querySelectorAll('input[type="number"]').forEach(scrubNumberInput);

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

// ---- Cat popup: a unit's forms (icons), stats + a link to its wiki page ------
// Opened from any cat name (track / steps) or the ⓘ opener on collection/picker
// chips. Form icons are hotlinked per-form from battlecatsinfo's asset repo (via its
// GitHub Pages CDN); ones that 404 (unreleased units) just hide themselves. Clicking
// a form icon shows that form's stat block and ability chips (quoted at the level
// baked into stats.json).
const catPopup = document.getElementById("catPopup");
if (catPopup) {
  const ICON_BASE = "https://battlecatsinfo.github.io/img/u";
  const infoUrl = document.body.dataset.unitInfoUrl;
  const nameEl = catPopup.querySelector(".cat-popup-name");
  const rarityEl = catPopup.querySelector(".cat-popup-head .rarity");
  const tierEl = catPopup.querySelector(".cat-popup-tier");
  const formsEl = catPopup.querySelector(".cat-popup-forms");
  const wikiEl = catPopup.querySelector(".cat-popup-wiki");
  const statsEl = catPopup.querySelector(".cat-popup-stats");
  const gridEl = catPopup.querySelector(".cat-stats-grid");
  const chipsEl = catPopup.querySelector(".cat-popup-chips");
  const noteEl = catPopup.querySelector(".cat-stats-note");
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

  const chip = (text, kind) => {
    const span = document.createElement("span");
    span.className = kind ? `cat-chip ${kind}` : "cat-chip";
    span.textContent = text;
    return span;
  };

  const statCell = (label, value) => {
    const cell = document.createElement("div");
    cell.className = "cat-stat";
    const name = document.createElement("span");
    name.className = "label";
    name.textContent = label;
    const val = document.createElement("span");
    val.className = "value";
    val.textContent = value;
    cell.append(name, val);
    return cell;
  };

  // The selected form's stat block. HP/attack/DPS are level-30, max-treasure quotes
  // (the level rides in with stats.json); a ? means battlecatsinfo doesn't carry the
  // form's animation yet, so its true attack rate is unknown.
  function renderStats(info, index) {
    const fmt = (n) => n.toLocaleString("en-US");
    const form = info.stats ? info.stats.forms[index] : undefined;
    statsEl.hidden = !form;
    [...formsEl.children].forEach((fig, i) => fig.classList.toggle("selected", !!form && i === index));
    if (!form) return;
    gridEl.replaceChildren(
      statCell("HP", fmt(form.hp)),
      statCell("Attack", fmt(form.atk)),
      statCell("DPS", form.dps === null ? "?" : fmt(form.dps)),
      statCell("Attack rate", form.freq === null ? "?" : `${form.freq}s`),
      statCell("Range", form.range),
      statCell("Attack type", form.area ? "Area" : "Single"),
      statCell("Recharge", `${form.recharge}s`),
      statCell("Speed", form.speed),
      statCell("Knockbacks", form.kb),
      statCell("Cost", fmt(form.cost)),
    );
    chipsEl.replaceChildren();
    form.targets.forEach((trait) => chipsEl.appendChild(chip(trait, "target")));
    form.effects.forEach((effect) => chipsEl.appendChild(chip(effect)));
    if (form.immune.length) {
      chipsEl.appendChild(chip(`Immune: ${form.immune.join(", ")}`, "immune"));
    }
    noteEl.textContent = `Lv ${info.stats.level} stats with max treasures; cost in chapter 2.`;
  }

  async function openFor(name) {
    const info = await load(name);
    if (!info) return; // a cat not in the catalogue yet: no forms/wiki to show
    nameEl.textContent = info.name;
    rarityEl.textContent = info.rarity;
    rarityEl.dataset.rarity = info.rarity;
    rarityEl.hidden = !info.rarity;
    tierEl.hidden = !info.tier;
    if (info.tier) {
      tierEl.dataset.band = info.tier.tier[0];
      tierEl.textContent = info.tier.up
        ? `Tier ${info.tier.tier} · ${info.tier.up_note}`
        : `Tier ${info.tier.tier}`;
    }
    wikiEl.href = info.wiki;
    formsEl.replaceChildren();
    (info.forms || []).forEach((form, i) => {
      const fig = document.createElement("figure");
      fig.className = "cat-form";
      const img = document.createElement("img");
      img.alt = form;
      img.src = `${ICON_BASE}/${info.unit_id}/${i}.png`;
      img.addEventListener("error", () => fig.classList.add("no-icon"));
      const caption = document.createElement("figcaption");
      caption.textContent = form;
      fig.append(img, caption);
      fig.addEventListener("click", () => renderStats(info, i));
      formsEl.appendChild(fig);
    });
    const last = info.stats ? info.stats.forms.length - 1 : 0;
    renderStats(info, last);
    if (!catPopup.open) catPopup.showModal();
  }

  document.addEventListener("click", (e) => {
    const trigger = e.target.closest(
      ".catlink[data-name], .catinfo[data-name], .cat-pill[data-name], .tier-unit[data-name]",
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

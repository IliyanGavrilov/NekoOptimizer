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
  }

  picker.addEventListener("click", (e) => {
    const chip = e.target.closest(".chip[data-pk]");
    if (chip) toggle(chip.dataset.pk, chip.dataset.name);
  });

  // Banner "session" selection: tapping + on a banner includes it and every
  // banner whose run overlaps it (what you'd see live at that time).
  const browser = document.getElementById("targetBrowser");
  const bannerInputs = document.getElementById("bannerInputs");
  const bannerCount = document.getElementById("bannerCount");
  const includes = [...browser.querySelectorAll(".banner-include")];
  const rangeOf = (btn) => {
    const d = btn.closest(".banner-group");
    return [d.dataset.start, d.dataset.end];
  };
  // Banners switch at the changeover day, so one ending on day X and another
  // starting on day X are consecutive, not concurrent — compare strictly.
  const overlaps = (a, b) => a[0] && b[0] && a[0] < b[1] && a[1] > b[0]; // ISO dates sort lexically

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
  }
  function toggleSession(btn) {
    const on = btn.getAttribute("aria-pressed") !== "true";
    const range = rangeOf(btn);
    for (const other of includes) {
      if (overlaps(rangeOf(other), range)) setIncluded(other, on);
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
  // Default to the session live today.
  const today = new Date().toISOString().slice(0, 10);
  for (const btn of includes) {
    const [start, end] = rangeOf(btn);
    if (start && start <= today && today <= end) setIncluded(btn, true);
  }
  syncBanners();

  // Searching shows a flat, undivided list of matching cats; clearing it
  // restores the banner/rarity grouping.
  const search = document.getElementById("targetSearch");
  const grouped = browser;
  const flat = document.getElementById("targetFlat");
  search.addEventListener("input", () => {
    const query = search.value.trim().toLowerCase();
    const searching = query !== "";
    grouped.hidden = searching;
    flat.hidden = !searching;
    if (searching) {
      flat.querySelectorAll("[data-name]").forEach((chip) => {
        chip.hidden = !chip.dataset.name.toLowerCase().includes(query);
      });
    }
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

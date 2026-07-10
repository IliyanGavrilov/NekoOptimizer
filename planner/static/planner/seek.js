// ---- Seed Finder: enter your real pulls, poll the background search ----------
// Picking a banner fetches its pools and builds the roll pickers; submitting
// starts a server-side sieve of the whole 2^32 seed space and this page polls its
// progress until the matching seed(s) come back.
const seekForm = document.getElementById("seekForm");
if (seekForm) {
  const token = seekForm.querySelector("[name=csrfmiddlewaretoken]").value;
  const bannerEl = document.getElementById("seekBanner");
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

  let optionsHtml = ""; // the selected banner's pools, rendered once per fetch

  const esc = (text) =>
    text.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);

  const setError = (msg) => (errorEl.textContent = msg || "");

  const appendRow = () => {
    const li = document.createElement("li");
    li.innerHTML = `<select class="seek-roll"><option value="">&mdash;</option>${optionsHtml}</select>`;
    rollsEl.append(li);
  };

  const pickHint = document.getElementById("seekPickHint");

  bannerEl.addEventListener("change", async () => {
    setError("");
    results.hidden = true;
    entry.hidden = true;
    pickHint.hidden = false;
    rollsEl.innerHTML = "";
    if (!bannerEl.value) return;

    let resp;
    try {
      resp = await fetch(`${seekForm.dataset.poolUrl}?banner=${encodeURIComponent(bannerEl.value)}`);
    } catch {
      resp = null;
    }
    if (!resp || !resp.ok) {
      setError("Couldn't load that banner's cats - is the server still running?");
      return;
    }
    const pool = await resp.json();
    names.clear();
    optionsHtml = pool.groups
      .map(
        (g) =>
          `<optgroup label="${esc(g.rarity)}">` +
          g.options.map((o) => `<option value="${o.value}">${esc(o.label)}</option>`).join("") +
          "</optgroup>"
      )
      .join("");
    for (let i = 0; i < START_ROWS; i++) appendRow();
    pickHint.hidden = true;
    entry.hidden = false;
  });

  addRow.addEventListener("click", () => {
    if (rollsEl.children.length < MAX) appendRow();
    addRow.hidden = rollsEl.children.length >= MAX;
  });

  // ---- The search itself: start the job, poll until it's done ----------------

  const PASS_LABELS = [
    "Searching the seed space…",
    "No clean match — retrying your first pull as a dupe reroll (below the shadow slot)…",
    "No clean match — retrying your first pull as a dupe reroll (at or above the shadow slot)…",
  ];

  const matchCard = (m, lastCat) => {
    const open = `${plannerUrl}?seed=${m.seed_after}${
      lastCat ? `&last=${encodeURIComponent(lastCat)}` : ""
    }`;
    const replay = `${plannerUrl}?seed=${m.seed_before}`;
    const dupeNote = m.run
      ? " &middot; your first entered pull arrived as a dupe reroll, so the replay shows it in the R column"
      : "";
    return `<div class="seek-match">
      <div class="seek-seed">Your seed is now <strong>${m.seed_after}</strong></div>
      <a class="seek-open" href="${open}">Open the planner at your position &rarr;</a>
      <p class="muted">Seed before those pulls: ${m.seed_before} &middot; <a href="${replay}">replay them</a>${dupeNote}</p>
    </div>`;
  };

  const render = (data) => {
    progressWrap.hidden = true;
    goBtn.disabled = false;
    results.hidden = false;

    if (data.error) {
      results.innerHTML = `<p class="field-error">Search failed: ${esc(data.error)}</p>`;
      return;
    }
    if (!data.matches.length) {
      results.innerHTML = `<p class="seek-none">No seed deals exactly those pulls. Double-check the
        cats and their order, that this is the right banner run, and that the pulls
        were consecutive (nothing rolled in between, no guaranteed uber included).</p>`;
      return;
    }

    let notes = "";
    if (data.truncated) {
      notes = `<p class="field-warning">Far too many seeds match - this window is too
        short to pin yours down. Add a few more rolls and search again; only the first
        ${data.matches.length} are shown.</p>`;
    } else if (data.matches.length > 1) {
      notes = `<p class="field-warning">${data.matches.length} seeds match. Roll a few
        more cats, add them, and search again to narrow it down.</p>`;
    }
    results.innerHTML =
      notes + data.matches.map((m) => matchCard(m, data.last_cat)).join("");
  };

  const poll = (job) => {
    const tick = async () => {
      let resp;
      try {
        resp = await fetch(`${seekForm.dataset.statusUrl}?job=${job}`);
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

  seekForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    setError("");

    const values = [...rollsEl.querySelectorAll("select")].map((s) => s.value);
    const last = values.length - 1 - [...values].reverse().findIndex(Boolean);
    const filled = values.filter(Boolean);
    if (filled.length && values.slice(0, last + 1).some((v) => !v)) {
      setError("Fill your pulls in order, top to bottom - no gaps.");
      return;
    }
    if (filled.length < MIN) {
      setError(`Enter at least ${MIN} pulls (around 10 works best).`);
      return;
    }

    const body = new URLSearchParams({ banner: bannerEl.value, csrfmiddlewaretoken: token });
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
    poll((await resp.json()).job);
  });
}

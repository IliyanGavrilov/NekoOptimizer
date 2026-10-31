// ---- Collection from Cat Guide screenshots ---------------------------------------
// The player screenshots every page of the in-game Cat Guide. neko.wasm reads each one
// right here - where it sits in the guide, and which cells are owned or still a gray
// "?" - and the server checks the set against our guide before it replaces the owned
// marks, so a guide from another game version is turned away rather than misread.
const guideBtn = document.getElementById("guideImport");
if (guideBtn) {
  const guideFiles = document.getElementById("guideImportFiles");
  const ioMsg = document.getElementById("collectionIoMsg");
  const token = document.getElementById("csrfToken").value;
  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  let reader = null;

  const esc = (text) => text.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
  const say = (html) => {
    ioMsg.innerHTML = html;
    ioMsg.hidden = false;
  };
  const sayErrors = (errors) =>
    say(`<b>${gettext("Not imported:")}</b><ul>${errors.map((e) => `<li>${esc(e)}</li>`).join("")}</ul>`);

  const load = async () => {
    if (!reader) {
      const bytes = await (await fetch(guideBtn.dataset.wasmUrl)).arrayBuffer();
      const instance = await WebAssembly.instantiate(await WebAssembly.compile(bytes), {
        env: { progress() {} },
      });
      reader = instance.exports;
    }
    return reader;
  };

  // Decode a screenshot into the module's memory; ``use`` gets its pointer and size, and
  // the pixels are freed after.
  const withPixels = async (ex, file, use) => {
    const bitmap = await createImageBitmap(file);
    const { width, height } = bitmap;
    canvas.width = width;
    canvas.height = height;
    ctx.drawImage(bitmap, 0, 0);
    bitmap.close();
    const { data } = ctx.getImageData(0, 0, width, height);
    const ptr = ex.alloc(data.length);
    new Uint8Array(ex.memory.buffer, ptr, data.length).set(data);
    try {
      return use(ptr, width, height);
    } finally {
      ex.dealloc(ptr, data.length);
    }
  };

  const post = (shots, apply) =>
    fetch(guideBtn.dataset.url, {
      method: "POST",
      headers: { "X-CSRFToken": token, "Content-Type": "application/json" },
      body: JSON.stringify({ shots, apply }),
    });

  const read = async (files) => {
    const ex = await load();
    // Pass 1: each shot's place in the guide and, on a page with enough cells, its grid.
    const measured = [];
    for (const file of files) {
      measured.push(
        await withPixels(ex, file, (ptr, width, height) => {
          const found = ex.guide_measure(ptr, width, height);
          const page = new Float64Array(ex.memory.buffer, ex.guide_page(), 9).slice();
          return { found, page, size: `${width}x${height}` };
        }),
      );
    }
    // Pass 2: every shot under one grid, a full page's - they all came off one screen.
    const full = measured.find((m) => m.found & 2 && m.page[7] === 6 && m.page[8] === 4);
    if (!full) return { error: gettext("None of these shows a full Cat Guide page - is it the right screen?") };
    if (measured.some((m) => m.size !== full.size)) {
      return { error: gettext("Take every screenshot on the same device, in the same orientation.") };
    }
    const grid = Array.from(full.page.slice(1, 7));
    const shots = [];
    for (const [i, file] of files.entries()) {
      const marks = await withPixels(ex, file, (ptr, width, height) => {
        const at = ex.guide_read(ptr, width, height, ...grid); // before taking the buffer
        return Array.from(new Uint8Array(ex.memory.buffer, at, 24), (m) => ".?O"[m]).join("");
      });
      const { found, page } = measured[i];
      shots.push({ name: file.name, position: found & 1 ? page[0] : null, marks, taken: file.lastModified });
    }
    return { shots };
  };

  guideBtn.addEventListener("click", () => guideFiles.click());
  guideFiles.addEventListener("change", async () => {
    const files = [...guideFiles.files];
    guideFiles.value = "";
    if (!files.length) return;

    say(interpolate(ngettext("Reading %s screenshot…", "Reading %s screenshots…", files.length), [files.length]));
    const { shots, error } = await read(files).catch(() => ({ error: gettext("Couldn't open those images.") }));
    if (error) return sayErrors([error]);

    const check = await post(shots, false);
    if (!check.ok) return sayErrors([gettext("Those screenshots couldn't be read.")]);
    const verdict = await check.json();
    if (verdict.errors.length) return sayErrors(verdict.errors);

    const ok = confirm(
      interpolate(
        gettext("The Cat Guide shows %(owned)s of %(total)s cats owned. Mark exactly those as owned? Your wishlist stays as it is."),
        verdict,
        true,
      ),
    );
    if (!ok) return say(gettext("Import cancelled - nothing changed."));

    const result = await (await post(shots, true)).json();
    if (!result.applied) return sayErrors(result.errors);
    say(interpolate(gettext("Marked %s cats owned from your Cat Guide. Reloading…"), [result.owned]));
    location.reload();
  });
}

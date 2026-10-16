// ---- Local seed search: the Rust sieve (neko.wasm) on every core ---------------
// The server only validates the pulls and hands back the search; the 2^32 sweep runs
// here, one worker per core, each scanning a slice of the pass. Slices come back in
// seed-space order, so concatenating them gives exactly what one sweep would - the
// same matches, in the same order, as neko/seek.py.
let seekModule = null;

async function localSeek(search, { wasmUrl, workerUrl, onProgress }) {
  seekModule ??= WebAssembly.compile(await (await fetch(wasmUrl)).arrayBuffer());
  const module = await seekModule;
  const words = [
    search.sizes.length,
    ...search.sizes,
    ...search.bands,
    search.rerollable.reduce((mask, pool) => mask | (1 << pool), 0),
    search.cats.length,
    ...search.cats.flat(),
  ];
  // Pass sizes come from the module itself, so the slicing can't drift from the sieve.
  const sizer = (await WebAssembly.instantiate(module, { env: { progress() {} } })).exports;
  new Uint32Array(sizer.memory.buffer, sizer.seek_input(), words.length).set(words);

  const count = Math.max(1, Math.min(navigator.hardwareConcurrency || 4, 16));
  const workers = Array.from({ length: count }, () => new Worker(workerUrl));

  // One pass, split across the workers; resolves to its first ``cap`` matches.
  const pass = (run, cap) => {
    const total = sizer.seek_pass_size(run);
    if (!total) return Promise.resolve([]);
    const step = Math.ceil(total / count);
    const done = new Array(count).fill(0);
    return Promise.all(
      workers.map(
        (worker, i) =>
          new Promise((resolve, reject) => {
            worker.onerror = (e) => reject(new Error(e.message || "the search worker failed"));
            worker.onmessage = ({ data }) => {
              if (data.error) return reject(new Error(data.error));
              if (data.matches) return resolve(data.matches);
              done[i] = data.progress;
              onProgress(run, done.reduce((a, b) => a + b, 0) / count);
            };
            const from = Math.min(total, i * step);
            worker.postMessage({ module, words, run, from, to: Math.min(total, from + step), cap });
          }),
      ),
    ).then((slices) => slices.flat().slice(0, cap));
  };

  // The clean reading first; only when it finds nothing, the two dupe-repick readings.
  try {
    const limit = search.limit;
    let matches = await pass(0, limit + 1);
    if (!matches.length) {
      for (const run of [1, 2]) {
        matches = matches.concat(await pass(run, Math.max(limit + 1 - matches.length, 1)));
      }
    }
    return { matches, truncated: matches.length > limit };
  } finally {
    workers.forEach((worker) => worker.terminate());
  }
}

// One slice of a seed-search pass, off the page's thread (see seekrun.js).
let sieve = null;

onmessage = async ({ data }) => {
  try {
    const { module, words, run, from, to, cap } = data;
    sieve ??= (
      await WebAssembly.instantiate(module, {
        env: { progress: (_run, fraction) => postMessage({ progress: fraction }) },
      })
    ).exports;
    new Uint32Array(sieve.memory.buffer, sieve.seek_input(), words.length).set(words);
    const n = sieve.seek_search(run, from, to, cap);
    const out = new Uint32Array(sieve.memory.buffer, sieve.seek_output(), 3 * n);
    const matches = [];
    for (let i = 0; i < n; i++) {
      matches.push({ seed_before: out[3 * i], seed_after: out[3 * i + 1], run: out[3 * i + 2] });
    }
    postMessage({ matches });
  } catch (error) {
    postMessage({ error: String(error) });
  }
};

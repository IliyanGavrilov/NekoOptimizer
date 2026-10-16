// The planner engine (neko.wasm) off the page's thread: a request in, its response out.
// Rolling a table or solving a plan can take a while, and the page stays live meanwhile.
let ready = null;

const load = async (url) => {
  const bytes = await (await fetch(url)).arrayBuffer();
  const instance = await WebAssembly.instantiate(await WebAssembly.compile(bytes), {
    env: { progress() {} },
  });
  return instance.exports;
};

onmessage = async ({ data: { id, url, request } }) => {
  try {
    ready ??= load(url);
    const ex = await ready;
    const bytes = new TextEncoder().encode(request);
    const ptr = ex.alloc(bytes.length);
    new Uint8Array(ex.memory.buffer, ptr, bytes.length).set(bytes);
    ex.engine(ptr, bytes.length);
    ex.dealloc(ptr, bytes.length);
    const out = new Uint8Array(ex.memory.buffer, ex.engine_out(), ex.engine_out_len());
    postMessage({ id, response: new TextDecoder().decode(out) });
  } catch (error) {
    postMessage({ id, error: String(error) });
  }
};

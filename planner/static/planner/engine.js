// The page's own engine (neko.wasm) in a worker, so the page stays live while it rolls or
// solves: the server sends a request, this hands it over and resolves to what it renders.
// nekoEngine(wasmUrl, workerUrl) starts one worker and returns its call function.
function nekoEngine(wasmUrl, workerUrl) {
  const worker = new Worker(workerUrl);
  const pending = new Map();
  let calls = 0;
  worker.onmessage = ({ data }) => {
    const call = pending.get(data.id);
    pending.delete(data.id);
    if (data.error || data.response.startsWith('{"error"')) {
      call.reject(new Error(data.error || data.response));
    } else {
      call.resolve(data.response);
    }
  };
  return (request) =>
    new Promise((resolve, reject) => {
      calls += 1;
      pending.set(calls, { resolve, reject });
      worker.postMessage({ id: calls, url: wasmUrl, request });
    });
}

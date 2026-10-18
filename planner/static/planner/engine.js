// The page's own engine (neko.wasm) in a worker, so the page stays live while it rolls or
// solves: the server sends a request, this hands it over and resolves to what it renders.
// nekoEngine(wasmUrl, workerUrl) returns a call function; its worker starts on the first
// call, so a page nobody rolls on never loads one.
function nekoEngine(wasmUrl, workerUrl) {
  let worker = null;
  const pending = new Map();
  let calls = 0;
  const start = () => {
    worker = new Worker(workerUrl);
    worker.onmessage = ({ data }) => {
      const call = pending.get(data.id);
      pending.delete(data.id);
      if (data.error || data.response.startsWith('{"error"')) {
        call.reject(new Error(data.error || data.response));
      } else {
        call.resolve(data.response);
      }
    };
    return worker;
  };
  return (request) =>
    new Promise((resolve, reject) => {
      calls += 1;
      pending.set(calls, { resolve, reject });
      (worker ?? start()).postMessage({ id: calls, url: wasmUrl, request });
    });
}

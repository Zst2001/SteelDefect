// No Vite config, .env, network, browser, or generated build files.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const requireWeb = createRequire(path.join(root, "apps/web/package.json"));
const ts = requireWeb("typescript");
const sfc = requireWeb("@vue/compiler-sfc");
function compile(file) {
  const result = ts.transpileModule(fs.readFileSync(path.join(root, file), "utf8"), {
    fileName: file, reportDiagnostics: true,
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, esModuleInterop: true },
  });
  assert.equal((result.diagnostics ?? []).filter(d => d.category === ts.DiagnosticCategory.Error).length, 0);
  return result.outputText;
}
const context = { exports: {} };
vm.runInNewContext(compile("apps/web/src/views/compare/layerView.ts"), context);
const choose = context.exports.chooseLayerView;
const a = { mask: true, overlay: true, cam: true, error: true };
const b = { ...a, error: false, cam: false };
assert.equal(choose("error", a), "error");
assert.equal(choose("error", b), "mask");
assert.equal(choose("error", a), "error");
assert.equal(choose("cam", b), "mask");
assert.equal(choose("error", { mask: false, overlay: true, error: false, cam: false }), "overlay");
assert.equal(choose("mask", { mask: false, overlay: false, error: false, cam: false }), null);
assert.equal(choose("error", b) === "error", false); // no GT / restricted GT URLs
console.log("PASS 7 layer availability assertions (A-B-A, CAM, partial, empty, restricted GT)");

const cams = context.exports.camLayers;
const artifact = (key, id) => ({ kind: "montage", sample_key: key, url: `/authorized/${key}__cam_c${id}.png` });
const partial = [artifact("A", 2), artifact("B", 1)];
let selected = 1;
const urls = key => cams(partial, key, [1, 2, 3]);
assert.equal(choose("cam", { ...b, cam: urls("A").length > 0 }), "cam");
assert.equal(urls("A").find(x => x.id === selected), undefined); // empty selected class, selector stays reachable
selected = 2;
assert.equal(urls("A").find(x => x.id === selected)?.url, partial[0].url);
assert.equal(urls("B").find(x => x.id === selected), undefined);
assert.equal(choose("cam", { ...b, cam: urls("B").length > 0 }), "cam");
assert.equal(urls("A").find(x => x.id === selected)?.url, partial[0].url); // A-B-A restores class 2
assert.equal(cams([artifact("A", 1), artifact("A", 2)], "A", [1, 2, 3]).length, 2);
assert.equal(cams([], "A", [1, 2, 3]).length, 0);
assert.equal(cams(partial, undefined, [1, 2, 3]).length, 0);
assert.equal(cams([{ ...artifact("A", 2), kind: "error" }], "A", [1, 2, 3]).length, 0);
assert.equal(choose("error", { ...b, cam: urls("A").length > 0 }), "mask"); // restricted GT stays unavailable
assert.equal(cams([{ ...artifact("A", 2), url: "/authorized/A__cam_c2.png.backup" }], "A", [2]).length, 0);
console.log("PASS 12 CAM class assertions (missing c1, selectable c2, A-B-A, empty, restricted GT, partial artifacts)");

let request, response, reject, counter = 0;
const fakeHttp = { interceptors: {
  request: { use: fn => { request = fn; } },
  response: { use: (ok, fail) => { response = ok; reject = fail; } },
} };
const axios = { create: () => fakeHttp, isAxiosError: () => true };
vm.runInNewContext(compile("apps/web/src/api/http.ts"), {
  exports: {}, require: () => ({ __esModule: true, default: axios }),
  FormData: class {}, File: class {}, Uint8Array,
  crypto: { getRandomValues: bytes => { bytes.fill(++counter); return bytes; } },
});
function config() { return { method: "post", url: "/tasks/compare", data: { batch_id: "same" }, headers: new Map() }; }
const first = request(config()), duplicate = request(config());
assert.equal(first.headers.get("Idempotency-Key"), duplicate.headers.get("Idempotency-Key"));
await assert.rejects(reject({ config: first }));
assert.equal(request(config()).headers.get("Idempotency-Key"), first.headers.get("Idempotency-Key"));
response({ config: first });
assert.notEqual(request(config()).headers.get("Idempotency-Key"), first.headers.get("Idempotency-Key"));
console.log("PASS 3 idempotency assertions (concurrent submit, uncertain retry, new submission)");

for (const file of ["views/compare/CompareNewView.vue", "views/compare/CompareTaskView.vue", "views/demo/DemoTaskView.vue", "views/records/RecordsView.vue", "views/WorkbenchView.vue"]) {
  const source = fs.readFileSync(path.join(root, "apps/web/src", file), "utf8");
  const { descriptor, errors } = sfc.parse(source, { filename: file });
  assert.equal(errors.length, 0);
  const script = sfc.compileScript(descriptor, { id: file });
  const template = sfc.compileTemplate({ source: descriptor.template.content, filename: file, id: file,
    compilerOptions: { bindingMetadata: script.bindings } });
  assert.equal(template.errors.length, 0);
  const syntax = ts.transpileModule(script.content, { reportDiagnostics: true, compilerOptions: { target: ts.ScriptTarget.ES2022 } });
  assert.equal((syntax.diagnostics ?? []).filter(d => d.category === ts.DiagnosticCategory.Error).length, 0);
  console.log(`PASS SFC + TS syntax ${file}`);
}

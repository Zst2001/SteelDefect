// Local-only Vite check, without .env, API calls, or downloading private files.
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';
import { createServer } from '../apps/web/node_modules/vite/dist/node/index.js';

const repo = fileURLToPath(new URL('../', import.meta.url));
const server = await createServer({
  root: resolve(repo, 'apps/web'),
  envFile: false,
  logLevel: 'silent',
  server: { host: '127.0.0.1', port: 0, open: false },
});
try {
  await server.listen();
  const base = `http://127.0.0.1:${server.httpServer.address().port}`;
  const root = await fetch(base, { method: 'HEAD' });
  assert.equal(root.status, 200);
  const rows = [];
  for (const rel of [
    'assets/PCB_segment/pcb_seg_meiwei_v2_formal_v1.zip',
    'assets/PCB_segment/pcb_seg_meiwei_v2_formal_v1.zip.sha256',
    'assets/pcb/meiwei_v2_formal_v1/models/unet/weights.pth',
    'assets/pcb/meiwei_v2_formal_v1/reference_vectors/unet_logits.npy',
    'assets/pcb/meiwei_v2_formal_v1/source/trusted_models.py',
  ]) {
    const fsPath = resolve(repo, rel).replaceAll('\\', '/');
    const response = await fetch(`${base}/@fs/${fsPath}`, { method: 'HEAD' });
    assert.equal(response.status, 403, `Private asset is exposed: ${rel}`);
    rows.push({ path: rel, status: response.status });
  }
  console.log(JSON.stringify({ status: 'PASS', root: root.status, privateAssetRequests: rows,
    note: 'Isolated current Vite configuration; HEAD only, no private payload fetched.' }, null, 2));
} finally {
  await server.close();
}

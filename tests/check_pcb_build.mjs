// Current frontend production build in a disposable directory; never reads .env.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import net from 'node:net';
import { createRequire } from 'node:module';
import { fileURLToPath, pathToFileURL } from 'node:url';
import {probePrivateAssets, boundedRequest} from './pcb_private_get_probe.mjs';
import {classificationPrivatePaths} from './pcb_classification_private_paths.mjs';
const root = fileURLToPath(new URL('../', import.meta.url));
const require = createRequire(path.join(root, 'apps/web/package.json'));
const { build, preview } = await import(pathToFileURL(require.resolve('vite')));
const scratch = await fs.mkdtemp(path.join(os.tmpdir(), 'steel-pcb-build-'));
const evidence = process.argv[2] ? path.resolve(process.argv[2]) : null;
let server;
try {
  const config = {root: path.join(root, 'apps/web'), configFile: path.join(root,'apps/web/vite.config.ts'),
    envFile: false, envDir: scratch, build: { outDir: path.join(scratch, 'dist'), emptyOutDir: false }, logLevel: 'warn'};
  await build(config);
  const files = await fs.readdir(path.join(scratch, 'dist/assets'));
  assert(files.some(name => /^PcbNewView-.*\.js$/.test(name)));
  assert(files.some(name => /^PcbTaskView-.*\.js$/.test(name)));
  if (process.argv.includes('--classification')) {
    assert(files.some(name => /^PcbClassifyNewView-.*\.js$/.test(name)));
    assert(files.some(name => /^PcbClassifyTaskView-.*\.js$/.test(name)));
  }
  assert(!files.some(name => /\.pth$|\.zip$|\.npy$|trusted_models/.test(name)));
  const allFiles=await fs.readdir(path.join(scratch,'dist'),{recursive:true});
  assert(!allFiles.some(name=>/\.pth$|\.zip$|\.npy$|\.py$|admission\.json|ASSET_MANIFEST|MODEL_REGISTRY/.test(name)));
  const reservation=net.createServer();
  await new Promise(resolve=>reservation.listen(0,'127.0.0.1',resolve));
  const port=reservation.address().port;
  await new Promise(resolve=>reservation.close(resolve));
  server=await preview({...config,preview:{host:'127.0.0.1',port,strictPort:true,open:false}});
  const origin=`http://127.0.0.1:${server.httpServer.address().port}`;
  assert.equal((await boundedRequest(origin,'/','GET')).status,200);
  assert.equal((await boundedRequest(origin,'/assets/'+files.find(name=>/^PcbTaskView-.*\.js$/.test(name)),'HEAD')).status,200);
  const matrix=await probePrivateAssets({origin,root,surface:'build-preview',output:path.join(evidence||scratch,'private-get-build.json')});
  if (process.argv.includes('--classification')) await probePrivateAssets({origin,root,surface:'build-preview-classification',
    paths:classificationPrivatePaths,output:path.join(evidence||scratch,'private-classification-build.json')});
  if(evidence){await fs.mkdir(evidence,{recursive:true});await fs.writeFile(path.join(evidence,'build.json'),JSON.stringify({status:'PASS',files:allFiles,privateAssetsAbsent:true,rootStatus:200,pcbChunkStatus:200,securityRequests:matrix.requests,vueTsc:'NOT_RUN'},null,2));}
  console.log(`PASS Vite build, recursive private asset exclusion, root/chunk positive controls, ${matrix.requests} preview GET/HEAD denials. No full vue-tsc typecheck claimed.`);
} finally {
  if(server) await new Promise((resolve,reject)=>server.httpServer.close(error=>error?reject(error):resolve()));
  const target = await fs.realpath(scratch);
  const tempRoot = await fs.realpath(os.tmpdir());
  assert(path.dirname(target) === tempRoot && path.basename(target).startsWith('steel-pcb-build-'));
  await fs.rm(target, { recursive: true });
}

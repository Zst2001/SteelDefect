// Standalone real Vite GET/HEAD regression; no API/data access.
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import net from 'node:net';
import {fileURLToPath} from 'node:url';
import {createServer} from '../apps/web/node_modules/vite/dist/node/index.js';
import {probePrivateAssets} from './pcb_private_get_probe.mjs';
const root=fileURLToPath(new URL('../',import.meta.url));
const output=path.resolve(process.argv[2] || 'docs/report/pcb-stage4-closeout-20261030/private-get-vite.json');
const scratch=await fs.mkdtemp(path.join(os.tmpdir(),'steel-pcb-get-'));
const reservation=net.createServer();
await new Promise(resolve=>reservation.listen(0,'127.0.0.1',resolve));
const port=reservation.address().port;
await new Promise(resolve=>reservation.close(resolve));
const server=await createServer({root:path.join(root,'apps/web'),configFile:path.join(root,'apps/web/vite.config.ts'),
  envFile:false,envDir:scratch,cacheDir:path.join(scratch,'cache'),logLevel:'silent',
  server:{host:'127.0.0.1',port,strictPort:true,open:false}});
try {
  await server.listen();
  const origin=`http://127.0.0.1:${server.httpServer.address().port}`;
  const report=await probePrivateAssets({origin,root,surface:'Vite',output,assertSafe:!process.argv.includes('--observe')});
  console.log(JSON.stringify({status:report.status,requests:report.requests,failures:report.rows.filter(r=>!r.pass).length,output}));
} finally {
  await server.close();
  const target=await fs.realpath(scratch),temp=await fs.realpath(os.tmpdir());
  if(path.dirname(target)!==temp || !path.basename(target).startsWith('steel-pcb-get-'))throw new Error('Unsafe scratch cleanup');
  await fs.rm(target,{recursive:true});
}

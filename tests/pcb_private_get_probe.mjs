// Bounded loopback-only checks. Never save private response contents.
import assert from 'node:assert/strict';
import http from 'node:http';
import fs from 'node:fs/promises';
import path from 'node:path';

export const privatePaths = [
  'assets/PCB_segment/pcb_seg_meiwei_v2_formal_v1.zip',
  'assets/PCB_segment/pcb_seg_meiwei_v2_formal_v1.zip.sha256',
  ...['unet','unet_resnet18','unetpp_resnet18'].flatMap(id => [
    `assets/pcb/meiwei_v2_formal_v1/models/${id}/weights.pth`,
    `assets/pcb/meiwei_v2_formal_v1/reference_vectors/${id}_logits.npy`,
  ]),
  ...['source/trusted_models.py','source/pcb_preprocess.py','source/pcb_postprocess.py',
    'ASSET_MANIFEST.json','MODEL_REGISTRY.json'].map(p => `assets/pcb/meiwei_v2_formal_v1/${p}`),
  'assets/pcb/meiwei_v2_formal_v1.admission.json',
];

export function boundedRequest(origin, requestPath, method = 'GET') {
  const base = new URL(origin);
  assert.equal(base.hostname, '127.0.0.1');
  assert.equal(base.protocol, 'http:');
  assert(![8000,5173].includes(Number(base.port)), 'never probe the daily services');
  return new Promise((resolve, reject) => {
    const req = http.request({hostname:base.hostname,port:base.port,path:requestPath,method,
      headers:method === 'GET' ? {Range:'bytes=0-511'} : {},timeout:5000}, response => {
      const chunks = []; let bytes = 0, done = false;
      const finish = () => {
        if (done) return; done = true;
        const content = Buffer.concat(chunks).subarray(0,4096);
        resolve({status:response.statusCode,contentType:response.headers['content-type'] || '',
          location:response.headers.location || '',prefix:content.toString('utf8'),capturedBytes:content.length});
        response.destroy();
      };
      response.on('data', chunk => { chunks.push(chunk.subarray(0,4096-bytes));bytes+=Math.min(chunk.length,4096-bytes);if(bytes>=4096)finish(); });
      response.on('end',finish); response.on('error',error => {if(!done)reject(error);});
    });
    req.on('timeout',()=>req.destroy(new Error('local security probe timed out')));
    req.on('error',reject);req.end();
  });
}

export async function probePrivateAssets({origin,root,surface,output,assertSafe=true,paths=privatePaths}) {
  const rows=[];
  requests: for(const relative of paths) {
    const absolute=path.resolve(root,relative).replaceAll('\\','/');
    const encoded='/' + relative.replaceAll('/','%2F');
    const variants=[['relative','/'+relative],['fs','/@fs/'+absolute],['encoded',encoded],
      ['double-encoded',encoded.replaceAll('%','%25')],['query','/'+relative+'?raw'],
      ['dot-segment',relative.startsWith('assets/') ? '/assets/pcb/../'+relative.slice('assets/'.length) : '/packages/../'+relative],
      ['windows-assets-dot','/@fs/'+absolute.replace('/assets/','/assets./')],
      ['windows-assets-space','/@fs/'+absolute.replace('/assets/','/assets%20/')],
      ['windows-private-dot','/@fs/'+absolute.replace(/(\/assets\/[^/]+)\//,'$1./')],
      ['windows-private-space','/@fs/'+absolute.replace(/(\/assets\/[^/]+)\//,'$1%20/')]];
    for(const [variant,url] of variants) for(const method of ['GET','HEAD']) {
      let result;
      try { result=await boundedRequest(origin,url,method); }
      catch {
        rows.push({surface,asset:relative,variant,method,url,pass:false,error:'bounded local request failed'});
        break requests;
      }
      const internalPath=/(?:^|[^A-Za-z0-9])[A-Za-z]:[\\/]|outside of Vite serving allow list/i.test(result.prefix+' '+result.location);
      const denied=[403,404].includes(result.status);
      // Only known fixed denial payloads are persisted; never arbitrary bytes.
      const safeBody=/^(Forbidden\.?\s*|Not Found\s*|\{"detail":"Not Found"\})$/.test(result.prefix);
      rows.push({surface,asset:relative,variant,method,url,status:result.status,
        contentType:result.contentType,location:internalPath?'[REDACTED]':result.location,
        capturedBytes:result.capturedBytes,internalPath,denied,
        bodyKind:method==='HEAD'?'empty':result.prefix.trimStart().startsWith('<')?'html':safeBody?'fixed-denial':'withheld',
        bodyPrefix:method==='HEAD'?'':safeBody?result.prefix:'[non-fixed body withheld]',
        pass:denied&&!internalPath&&(method==='HEAD'||safeBody)});
    }
  }
  const report={surface,status:rows.every(row=>row.pass)?'PASS':'FAIL',requests:rows.length,expectedRequests:paths.length*10*2,
    maxCapturedBytes:4096,privateContentPersisted:false,rows};
  await fs.mkdir(path.dirname(output),{recursive:true});
  await fs.writeFile(output,JSON.stringify(report,null,2));
  if(assertSafe) assert.equal(report.status,'PASS',`${surface}: private asset denial failed; see bounded metadata report`);
  return report;
}

// Two real U-Net tasks only. All credentials arrive on stdin and are redacted.
// The parent owns disposable MySQL/Redis/RQ/API; this owns real Vite/Chromium.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import net from 'node:net';
import crypto from 'node:crypto';
import {createRequire} from 'node:module';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {probePrivateAssets} from './pcb_private_get_probe.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
let stdin = '';
for await (const part of process.stdin) {
  stdin += part.toString('utf8');
  assert.ok(Buffer.byteLength(stdin) < 4*1024*1024, 'stdin exceeds limit');
}
const config = JSON.parse(stdin); stdin = '';
const api = new URL(config.apiBase), output = path.resolve(config.output);
assert.ok(api.protocol === 'http:' && api.hostname === '127.0.0.1' && Number(api.port) > 1024 && ![8000,5173].includes(Number(api.port)));
assert.ok(!api.username && !api.password && api.pathname === '/' && !api.search && !api.hash);
assert.deepEqual(config.cases.map(c=>c.key), ['png-gt','jpeg-no-gt']);
assert.deepEqual(Object.keys(config.peers).sort(), ['advisor','peer']);
const secrets = [config.credentials.password, ...Object.values(config.peers)];
const redact = value => secrets.reduce((s,secret)=>s.split(secret).join('[REDACTED]'), String(value));
const requireWeb = createRequire(path.join(root, 'apps/web/package.json'));
const {chromium} = createRequire(path.join(path.resolve(process.argv[2]), 'package.json'))('./');
const {createServer} = await import(pathToFileURL(requireWeb.resolve('vite')));
const scratch = await fs.mkdtemp(path.join(os.tmpdir(), 'steel-pcb-closeout-ui-'));
const checks = [], createdTasks = [], blockedRequests = [], browserErrors = [], apiFailures = [], securityChecks = [];
let server, browser, page, context, frontOrigin, success = false;
const check = (condition, message) => {assert.ok(condition,message); checks.push(message); console.log(`PASS ${message}`);};
const checkEqual = (actual, expected, message) => {assert.deepEqual(actual,expected,message); checks.push(message); console.log(`PASS ${message}`);};
const write = (name, data) => fs.writeFile(path.join(output,name), JSON.stringify(data,null,2),'utf8');
const pngSize = bytes => {
  assert.ok(bytes.length >= 29 && bytes.subarray(0,8).equals(Buffer.from([137,80,78,71,13,10,26,10])), 'actual PNG magic required');
  return [bytes.readUInt32BE(16),bytes.readUInt32BE(20)];
};
async function capture(name) {
  await page.evaluate(() => {
    document.getElementById('closeout-synthetic-note')?.remove();
    window.scrollTo(0,0);
    const note = document.createElement('div'); note.id = 'closeout-synthetic-note';
    note.textContent = '合成测试图片与人工 GT · 隔离真实 API / RQ / CPU · 不代表模型精度';
    note.style.cssText = 'position:fixed;bottom:0;right:0;max-width:100%;background:#173450;color:white;padding:8px 12px;font:13px sans-serif;z-index:99999';
    document.body.append(note);
  });
  await page.screenshot({path:path.join(output,`${name}.png`),fullPage:true});
  await page.locator('#closeout-synthetic-note').evaluate(el=>el.remove());
}
async function readableImage(name, description) {
  const locator = page.getByRole('img',{name,exact:true});
  await locator.waitFor({state:'visible'});
  await locator.evaluate(async img=>{if(!img.complete) await img.decode();});
  const dimensions = await locator.evaluate(img=>[img.naturalWidth,img.naturalHeight]);
  check(dimensions[0] === 220 && dimensions[1] === 220,description);
}
async function readMetrics() {
  return page.locator('.pcb-metric-grid > div').evaluateAll(rows=>Object.fromEntries(rows.map(row=>[row.querySelector('dt').textContent,row.querySelector('dd').textContent])));
}
const metricPairs = [['defect_dice','Defect Dice'],['iou','Defect IoU'],['precision','Precision'],['recall','Recall']];
async function checkMetrics(task, description) {
  const displayed = await readMetrics();
  if(task.has_gt) {
    check(task.metrics.available === true && Object.keys(displayed).length === 4,`${description}: all four GT metrics displayed`);
    for(const [field,label] of metricPairs) {
      const value = task.metrics[field];
      check(displayed[label] === (value === null ? '—' : `${(value*100).toFixed(2)}%`),`${description}: ${label} matches API percentage`);
    }
  } else {
    check(task.metrics.available === false && Object.keys(displayed).length === 0,`${description}: no-GT API and UI omit numeric accuracy`);
    check((await page.locator('.pcb-no-metrics').innerText()).includes('无法计算真实性能指标'),`${description}: no-GT explanation visible`);
  }
  return displayed;
}
async function downloadLayer(row, label, kind) {
  await page.getByRole('button',{name:label,exact:true}).click();
  await readableImage(`PCB ${label}`,`${row.key}: ${kind} preview is readable at 220 coordinates`);
  const waiting = page.waitForEvent('download');
  await page.getByRole('button',{name:'下载当前图层',exact:true}).click();
  const download = await waiting;
  check(await download.failure() === null,`${row.key}: ${kind} browser download succeeds`);
  check(download.suggestedFilename() === `${row.taskId}_${kind}.png`,`${row.key}: ${kind} download name matches semantic label`);
  const bytes = await fs.readFile(await download.path());
  check(JSON.stringify(pngSize(bytes)) === '[220,220]',`${row.key}: ${kind} browser download has real 220 PNG bytes`);
  await fs.writeFile(path.join(output,row.key,`${kind}.png`),bytes);
  return bytes;
}
try {
  await fs.mkdir(output,{recursive:true});
  const reservation = net.createServer();
  await new Promise((resolve,reject)=>reservation.once('error',reject).listen(0,'127.0.0.1',resolve));
  const port = reservation.address().port;
  await new Promise(resolve=>reservation.close(resolve));
  assert.ok(![8000,5173].includes(port));
  server = await createServer({root:path.join(root,'apps/web'), configFile:path.join(root,'apps/web/vite.config.ts'),
    envFile:false,envDir:scratch,cacheDir:path.join(scratch,'cache'),logLevel:'error',
    server:{host:'127.0.0.1',port,strictPort:true,proxy:{'/api':{target:api.origin,changeOrigin:true,timeout:0,proxyTimeout:0}}}});
  await server.listen(); frontOrigin = `http://127.0.0.1:${server.httpServer.address().port}`;
  check(server.config.server.proxy['/api'].target === api.origin,'real Vite config proxies only to isolated API');
  browser = await chromium.launch({headless:true});
  context = await browser.newContext({viewport:{width:1440,height:1000},reducedMotion:'reduce'});
  await context.route('**/*',route=>{
    const url = new URL(route.request().url());
    if(url.origin === frontOrigin) return route.continue();
    blockedRequests.push(`${url.protocol}//${url.hostname}:${url.port}${url.pathname}`);
    return route.abort();
  });
  page = await context.newPage(); page.setDefaultTimeout(30000);
  page.on('pageerror',error=>browserErrors.push(redact(error.message)));
  page.on('response',response=>{
    const url = new URL(response.url());
    if(url.origin === frontOrigin && url.pathname.startsWith('/api/') && response.status() >= 400 && !(url.pathname === '/api/auth/me' && response.status() === 401))
      apiFailures.push({path:url.pathname,status:response.status()});
  });
  const go = async pathname=>{await page.goto(frontOrigin+pathname,{timeout:60000});await page.waitForLoadState('networkidle');};
  await go('/login?redirect=/inspect/pcb');
  await page.getByRole('textbox',{name:'用户名',exact:true}).fill(config.credentials.username);
  await page.getByLabel('密码',{exact:true}).fill(config.credentials.password);
  const loginWaiting = page.waitForResponse(r=>new URL(r.url()).pathname === '/api/auth/login' && r.request().method() === 'POST');
  await page.getByRole('button',{name:'登录',exact:true}).click();
  check((await loginWaiting).status() === 200,'synthetic owner logs in through real browser login form');
  await page.waitForURL('**/inspect/pcb');
  const ownerCookie = (await context.cookies()).find(cookie=>cookie.name === 'lab_session');
  check(Boolean(ownerCookie?.httpOnly),'real login issued HTTP-only session'); secrets.push(ownerCookie.value);
  for(const input of config.cases) {
    await go('/inspect/pcb');
    check(await page.getByRole('radio').count() === 3,`${input.key}: three admitted models available`);
    check(await page.locator('input[type=radio][value="unet"]').isChecked(),`${input.key}: default U-Net is selected`);
    await page.getByLabel('PCB 原图',{exact:true}).setInputFiles({name:input.filename,mimeType:input.mime,buffer:Buffer.from(input.imageBase64,'base64')});
    await readableImage('待分割 PCB 原图',`${input.key}: upload preview readable`);
    await page.locator('summary').filter({hasText:'高级选项'}).click();
    await page.getByRole('checkbox',{name:'生成 Grad-CAM',exact:true}).focus(); await page.keyboard.press('Space');
    check(await page.getByRole('checkbox',{name:'生成 Grad-CAM',exact:true}).isChecked(),`${input.key}: optional Grad-CAM enabled through browser`);
    if(input.hasGT) {
      await page.getByRole('checkbox',{name:'添加配对 GT',exact:true}).focus(); await page.keyboard.press('Space');
      await page.getByLabel('PCB 配对 GT',{exact:true}).setInputFiles({name:'synthetic-pcb-gt.png',mimeType:'image/png',buffer:Buffer.from(input.gtBase64,'base64')});
      await readableImage('配对 GT 预览',`${input.key}: paired GT preview readable`);
    } else check(!await page.getByRole('checkbox',{name:'添加配对 GT',exact:true}).isChecked(),'JPEG case intentionally has no GT');
    await capture(`${input.key}-upload-preview`);
    const creating = page.waitForResponse(r=>new URL(r.url()).pathname === '/api/scenes/pcb/segmentation/tasks' && r.request().method() === 'POST',{timeout:60000});
    await page.getByRole('button',{name:'开始 PCB 分割',exact:true}).click();
    const createdResponse = await creating;
    check(createdResponse.status() === 200,`${input.key}: browser submission reached real task API`);
    const taskId = (await createdResponse.json()).id;
    assert.match(taskId,/^[A-Za-z0-9_-]{1,128}$/);
    await page.waitForURL(`**/inspect/pcb/tasks/${taskId}`);
    await page.waitForFunction(()=>!!document.querySelector('.pcb-result .task-status.ok,.pcb-result .task-status.bad'),null,{timeout:180000});
    check(await page.locator('.pcb-result .task-status.ok').count() === 1,`${input.key}: real RQ Worker completed CPU task`);
    const response = await context.request.get(`${frontOrigin}/api/tasks/${taskId}`);
    const task = await response.json();
    check(task.status === 'success' && task.model.id === 'unet' && task.has_gt === input.hasGT,`${input.key}: real task model and GT identity match`);
    const hasCam = task.cam.status === 'ok';
    check(hasCam || (task.cam.status === 'unavailable' && task.cam.reason === '预测前景为空'),`${input.key}: CAM is computed or explicitly unavailable for empty foreground`);
    if(!hasCam) {
      check(!task.artifacts.some(a=>a.kind === 'cam') && await page.getByRole('button',{name:'Grad-CAM',exact:true}).isDisabled(),`${input.key}: empty-foreground CAM has no file or active control`);
      check((await page.locator('.pcb-cam-state').innerText()).includes('预测前景为空'),`${input.key}: empty-foreground CAM explanation is visible`);
    }
    await fs.mkdir(path.join(output,input.key),{recursive:true});
    const row = {key:input.key,filename:input.filename,taskId,model:'unet',hasGT:input.hasGT,api:task,uiMetrics:await checkMetrics(task,input.key),downloads:[],denied:[]};
    const cancel = await context.request.post(`${frontOrigin}/api/tasks/${taskId}/cancel`);
    check(cancel.status() === 404,`${input.key}: undeveloped cancellation API returns explicit 404`);
    row.cancellation = {status:'DEFERRED / NOT_SUPPORTED',method:'POST',httpStatus:cancel.status()};
    if(input.hasGT) row.uiCounts = await page.locator('.pcb-metrics > p').first().innerText();
    await readableImage('PCB 原始图像',`${input.key}: result original preview readable`);
    const layers = [['缺陷叠加','overlay'],['原始二值掩码（0/1）','pred_mask'],['可视化掩码（0/255）','mask_visual'],['缺陷边界','boundary'],['缺陷概率','probability']];
    if(hasCam) layers.push(['Grad-CAM','cam']);
    if(input.hasGT) layers.push(['配对 GT','gt'],['TP / FP / FN','error']);
    const uiBytes = {};
    for(const [label,kind] of layers) {
      uiBytes[kind] = await downloadLayer(row,label,kind);
      if(kind === 'mask_visual' || kind === 'error') await capture(`${input.key}-${kind}-result`);
    }
    const jsonWaiting = page.waitForEvent('download');
    await page.getByRole('button',{name:'下载结果 JSON',exact:true}).click();
    const jsonDownload = await jsonWaiting;
    check(await jsonDownload.failure() === null && jsonDownload.suggestedFilename() === `${taskId}_pcb.json`,`${input.key}: result JSON browser download succeeds`);
    const jsonData = JSON.parse(await fs.readFile(await jsonDownload.path(),'utf8'));
    await write(`${input.key}/pcb.json`,jsonData);
    await write(`${input.key}/api.json`,task);
    check(jsonData.task_id === taskId && jsonData.has_gt === input.hasGT,`${input.key}: downloaded JSON identity matches API`);
    // MySQL's JSON storage may reorder object keys; compare data, not text order.
    checkEqual(jsonData.metrics,task.metrics,`${input.key}: downloaded JSON metrics match API`);
    // Independently fetch every allowed file using the authenticated browser
    // request context. Capture real FileResponse headers and exact bytes; origin
    // is always visible but has no selected-layer download button in this UI.
    for(const artifact of task.artifacts) {
      assert.ok(artifact.url.startsWith(`/api/tasks/${taskId}/file/`));
      const file = await context.request.get(frontOrigin+artifact.url);
      const bytes = await file.body(), headers = file.headers();
      check(file.status() === 200,`${input.key}: authorized GET ${artifact.kind} succeeds`);
      if(artifact.kind !== 'pcb_result') {
        check(headers['content-type']?.split(';')[0] === 'image/png' && artifact.url.endsWith('/image.png') &&
          (!headers['content-disposition'] || /filename="?image\.png/.test(headers['content-disposition'])),`${input.key}: ${artifact.kind} HTTP MIME and URL filename are PNG`);
        check(JSON.stringify(pngSize(bytes)) === '[220,220]',`${input.key}: ${artifact.kind} GET body is real 220 PNG`);
        if(uiBytes[artifact.kind]) check(bytes.equals(uiBytes[artifact.kind]),`${input.key}: ${artifact.kind} UI download bytes equal FileResponse bytes`);
        await fs.writeFile(path.join(output,input.key,`${artifact.kind}.png`),bytes);
      } else checkEqual(JSON.parse(bytes),jsonData,`${input.key}: JSON UI and FileResponse payload identical`);
      row.downloads.push({kind:artifact.kind,url:artifact.url,status:file.status(),contentType:headers['content-type'],contentDisposition:headers['content-disposition'] ?? null,urlFilename:artifact.url.split('/').at(-1),bytes:bytes.length,sha256:crypto.createHash('sha256').update(bytes).digest('hex'),magicHex:artifact.kind === 'pcb_result'?null:bytes.subarray(0,8).toString('hex')});
    }
    for(const [role,session] of Object.entries(config.peers)) {
      const deniedContext = await browser.newContext();
      await deniedContext.addCookies([{name:'lab_session',value:session,url:frontOrigin,httpOnly:true,sameSite:'Lax'}]);
      try {
        for(const url of [`/api/tasks/${taskId}`,...task.artifacts.map(a=>a.url)]) {
          const denied = await deniedContext.request.get(frontOrigin+url);
          check(denied.status() === 404,`${input.key}: ${role} cannot GET ${url.split('/file/')[1] ?? 'task detail'}`);
          row.denied.push({role,url,status:denied.status()});
        }
      } finally {await deniedContext.close();}
    }
    createdTasks.push(row); await write(`${input.key}/api.json`,task);
  }
  check(new Set(createdTasks.map(row=>row.taskId)).size === 2,'two independent U-Net tasks created');
  for(const row of createdTasks) {
    await go('/records?type=pcb_segmentation');
    const link = page.locator(`a[href="/inspect/pcb/tasks/${row.taskId}"]`); await link.waitFor();
    check(await link.isVisible(),`${row.key}: task appears in real history`);
    await capture(`${row.key}-history`); await link.click();
    await page.waitForURL(`**/inspect/pcb/tasks/${row.taskId}`); await page.locator('.pcb-result-panel').waitFor();
    await checkMetrics(row.api,`${row.key} history re-entry`);
    await page.reload(); await page.waitForLoadState('networkidle');
    await page.locator('.pcb-result-panel').waitFor();
    assert.deepEqual(await checkMetrics(row.api,`${row.key} reload`),row.uiMetrics);
    const reloaded = await (await context.request.get(`${frontOrigin}/api/tasks/${row.taskId}`)).json();
    checkEqual(reloaded.metrics,row.api.metrics,`${row.key}: history reload preserves metrics`);
    const orderArtifacts = rows=>[...rows].sort((a,b)=>a.rel_path.localeCompare(b.rel_path));
    checkEqual(orderArtifacts(reloaded.artifacts),orderArtifacts(row.api.artifacts),`${row.key}: history reload preserves artifacts`);
    await page.getByRole('button',{name:'可视化掩码（0/255）',exact:true}).click();
    await readableImage('PCB 可视化掩码（0/255）',`${row.key}: visible mask survives reload`);
    await capture(`${row.key}-refreshed-result`);
  }
  await page.setViewportSize({width:390,height:1000});
  check(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth+1),'390px real result has no horizontal overflow');
  check(await page.getByRole('button',{name:/取消任务|中止任务/}).count() === 0,'mobile real result has no fake cancellation action');
  await capture('mobile-jpeg-result');
  for(const [surface,origin] of [['vite',frontOrigin],['api',api.origin]]) {
    const probe = await probePrivateAssets({origin,root,surface,output:path.join(output,`private-get-${surface}.json`)});
    securityChecks.push(probe);
    check(probe.status === 'PASS',`${surface}: private asset GET/HEAD matrix rejects disclosure`);
  }
  check(blockedRequests.every(url=>url === 'https://fonts.googleapis.com:/css2'),'only existing optional Google Fonts egress was attempted and blocked');
  check(browserErrors.length === 0,'live Chromium has no uncaught exceptions');
  check(apiFailures.length === 0,'live owner flow has no unexpected failed API requests');
  success = true;
} catch(error) {
  const message = redact(error instanceof Error ? error.stack ?? error.message : error);
  browserErrors.push(message); console.error(`PCB_CLOSEOUT_FAILED: ${message}`);
  if(page) {try {await capture('failure-state');} catch {}}
  process.exitCode = 1;
} finally {
  try {await write('results.json',{status:success?'PASS':'FAIL',checks:checks.length,assertions:checks,
    environment:'Real disposable MySQL + Redis/RQ + Windows SimpleWorker + U-Net + API + configured Vite + Chromium; no API mocks',
    inputProvenance:'Procedurally generated synthetic PCB and artificial GT; not model accuracy evidence',
    browser:browser?.version() ?? null,createdTasks,taskIds:createdTasks.map(row=>row.taskId),blockedRequests,apiFailures,browserErrors,securityChecks});}
  finally {
    await Promise.allSettled([browser?.close(),server?.close()]);config.credentials.password = ''; config.peers = {};
    const target = await fs.realpath(scratch), temporaryRoot = await fs.realpath(os.tmpdir());
    assert.ok(path.dirname(target) === temporaryRoot && path.basename(target).startsWith('steel-pcb-closeout-ui-'),'scratch cleanup must stay within exact owned temporary directory');
    await fs.rm(target,{recursive:true});
  }
}
if(success) console.log(JSON.stringify({status:'PASS',checks:checks.length,taskIds:createdTasks.map(row=>row.taskId),report:path.join(output,'results.json')}));

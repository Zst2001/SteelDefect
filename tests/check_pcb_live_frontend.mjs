// Real browser -> isolated FastAPI -> real Redis/RQ/CPU acceptance.
// Only the Playwright PACKAGE PATH is passed on argv (same convention as mock UI tests).
// Send one JSON document on stdin, then close stdin:
// {apiBase:"http://127.0.0.1:<isolated-port>",session:"<synthetic lab_session>",
//  taskIds:[],imageBase64:"<synthetic RGB PNG>",output:"<report-dir>"}
// Optional taskIds may contain three existing completed tasks for an extra read
// check. Independently, the UI creates one real task for each of the three models.
// The caller owns the isolated API/database/Redis/Worker lifecycle. This script
// starts only an ephemeral Vite server; no .env, startup seed, or mocked API.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath, pathToFileURL } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
let stdin = '';
for await (const part of process.stdin) {
  stdin += part.toString('utf8');
  if (Buffer.byteLength(stdin, 'utf8') > 4 * 1024 * 1024) throw new Error('Live PCB test input exceeds limit');
}
let config;
try { config = JSON.parse(stdin); } catch { throw new Error('Expected a JSON document on stdin'); }
stdin = '';
const api = new URL(config.apiBase);
assert.equal(api.protocol, 'http:', 'isolated API must use local HTTP');
assert.equal(api.hostname, '127.0.0.1', 'API proxy target must be numeric loopback');
assert.ok(Number(api.port) > 1024 && ![8000, 5173].includes(Number(api.port)), 'use a dedicated isolated API port');
assert.ok(!api.username && !api.password && !api.search && !api.hash && api.pathname === '/', 'API URL must not contain credentials/path/query');
assert.ok(typeof config.session === 'string' && config.session.length > 0 && config.session.length <= 512 && !/[\r\n]/.test(config.session), 'synthetic session required');
const taskIds = config.taskIds;
const validId = id => typeof id === 'string' && /^[A-Za-z0-9_-]{1,128}$/.test(id);
assert.ok(Array.isArray(taskIds) && [0,3].includes(taskIds.length) && new Set(taskIds).size === taskIds.length && taskIds.every(validId), 'taskIds must be empty or three unique completed task IDs');
assert.ok(typeof config.imageBase64 === 'string' && /^[A-Za-z0-9+/]+=*$/.test(config.imageBase64), 'synthetic PNG base64 required');
const inputImage = Buffer.from(config.imageBase64, 'base64');
config.imageBase64 = undefined;
const pngSize = bytes => {
  assert.ok(bytes.length >= 29 && bytes.subarray(0,8).equals(Buffer.from([137,80,78,71,13,10,26,10])), 'download/input is a PNG');
  return {width:bytes.readUInt32BE(16),height:bytes.readUInt32BE(20),bitDepth:bytes[24],colorType:bytes[25]};
};
assert.deepEqual(pngSize(inputImage), {width:220,height:220,bitDepth:8,colorType:2}, 'input must be the verified 220 RGB synthetic vector');
assert.ok(inputImage.length <= 2097152, 'synthetic image exceeds upload limit');
assert.ok(typeof config.output === 'string' && config.output.length > 0, 'output directory required');
const output = path.resolve(config.output);
await fs.mkdir(output, {recursive:true});
const redact = value => String(value).split(config.session).join('[REDACTED]');
const requireWeb = createRequire(path.join(root, 'apps/web/package.json'));
const {chromium} = createRequire(path.join(path.resolve(process.argv[2]), 'package.json'))('./');
const {createServer} = await import(pathToFileURL(requireWeb.resolve('vite')));
const vue = (await import(pathToFileURL(requireWeb.resolve('@vitejs/plugin-vue')))).default;
const scratch = await fs.mkdtemp(path.join(os.tmpdir(), 'steel-pcb-live-ui-'));
let server, browser, page, checkCount = 0, newTaskId = null, success = false;
const checks = [], observations = [], createdTasks = [], blockedRequests = [], browserErrors = [], apiFailures = [];
const check = (condition, message) => {
  assert.ok(condition, message);
  checks.push(message); checkCount++;
  console.log(`PASS ${message}`);
};
async function capture(name) {
  await page.evaluate(() => {
    document.getElementById('live-acceptance-note')?.remove();
    window.scrollTo(0,0);
    const note = document.createElement('div');
    note.id = 'live-acceptance-note';
    note.textContent = '隔离环境真实 API / RQ / CPU · 合成输入 · 非测试集精度';
    note.style.cssText = 'position:fixed;bottom:0;right:0;max-width:100%;box-sizing:border-box;background:#173450;color:#fff;padding:7px 12px;font:12px sans-serif;z-index:99999';
    document.body.append(note);
  });
  await page.screenshot({path:path.join(output,`${name}.png`),fullPage:true});
  await page.locator('#live-acceptance-note').evaluate(el => el.remove());
}
async function readableImage(alt, description) {
  const image = page.getByRole('img', {name:alt,exact:true});
  await image.waitFor({state:'visible',timeout:30000});
  await image.evaluate(async element => { if (!element.complete) await element.decode(); });
  const size = await image.evaluate(element => ({width:element.naturalWidth,height:element.naturalHeight}));
  check(size.width === 220 && size.height === 220, description);
}
async function downloadPNG(id, expectedKind) {
  const pending = page.waitForEvent('download', {timeout:30000});
  await page.getByRole('button',{name:'下载当前图层',exact:true}).click();
  const download = await pending;
  check((await download.failure()) === null, `${id} authenticated PNG download succeeds`);
  check(download.suggestedFilename() === `${id}_${expectedKind}.png`, `${id} download preserves selected layer identity`);
  const data = await fs.readFile(await download.path());
  const size = pngSize(data);
  check(size.width === 220 && size.height === 220, `${id} downloaded PNG retains 220 coordinates`);
}
async function downloadJSON(id) {
  const pending = page.waitForEvent('download', {timeout:30000});
  await page.getByRole('button',{name:'下载结果 JSON',exact:true}).click();
  const download = await pending;
  check((await download.failure()) === null, `${id} authenticated JSON download succeeds`);
  const data = JSON.parse(await fs.readFile(await download.path(),'utf8'));
  check(data.task_id === id && data.scene === 'pcb' && data.task_kind === 'segmentation', `${id} JSON provenance belongs to PCB task`);
  return data;
}
try {
  server = await createServer({root:path.join(root,'apps/web'),configFile:false,envFile:false,envDir:scratch,
    cacheDir:path.join(scratch,'cache'),plugins:[vue()],logLevel:'error',server:{host:'127.0.0.1',port:0,strictPort:true,
      proxy:{'/api':{target:api.origin,changeOrigin:true,timeout:0,proxyTimeout:0}}}});
  await server.listen();
  const address = server.httpServer.address();
  assert.ok(address && typeof address !== 'string', 'Vite did not allocate loopback port');
  const frontOrigin = `http://127.0.0.1:${address.port}`;
  browser = await chromium.launch({headless:true});
  const context = await browser.newContext({viewport:{width:1440,height:1000},reducedMotion:'reduce'});
  await context.addCookies([{name:'lab_session',value:config.session,url:frontOrigin,httpOnly:true,sameSite:'Lax'}]);
  await context.route('**/*', async route => {
    const url = new URL(route.request().url());
    if (url.origin === frontOrigin) return route.continue();
    // No request is fulfilled locally: every allowed API request goes through
    // Vite's loopback proxy to the real isolated FastAPI process.
    blockedRequests.push(`${url.protocol}//${url.hostname}:${url.port}${url.pathname}`);
    return route.abort();
  });
  page = await context.newPage(); page.setDefaultTimeout(30000);
  page.on('pageerror', error => browserErrors.push(redact(error.message)));
  page.on('response', response => {
    const url = new URL(response.url());
    if (url.origin === frontOrigin && url.pathname.startsWith('/api/') && response.status() >= 400)
      apiFailures.push({path:url.pathname,status:response.status()});
  });
  const go = async target => {await page.goto(frontOrigin+target,{timeout:60000});await page.waitForLoadState('networkidle');};
  const layers = [
    ['缺陷叠加','overlay'], ['原始二值掩码（0/1）','pred_mask'], ['缺陷边界','boundary'], ['缺陷概率','probability'], ['Grad-CAM','cam'],
  ];
  for (const [index,id] of taskIds.entries()) {
    const responsePromise = page.waitForResponse(r=>new URL(r.url()).pathname === `/api/tasks/${id}` && r.request().method() === 'GET');
    await go(`/inspect/pcb/tasks/${id}`);
    const response = await responsePromise, task = await response.json();
    check(response.ok() && task.status === 'success' && task.type === 'pcb_segmentation', `${id} existing real task is successful`);
    check(task.cam?.status === 'ok', `${id} real Grad-CAM is available`);
    await readableImage('PCB 原始图像', `${id} original image readable at 220 coordinates`);
    for (const [label,kind] of layers) {
      const button = page.getByRole('button',{name:label,exact:true});
      check(await button.isEnabled(), `${id} ${kind} layer selectable`);
      await button.click();
      await readableImage(`PCB ${label}`, `${id} real ${kind} layer readable at 220 coordinates`);
    }
    await downloadPNG(id,'cam');
    await downloadJSON(id);
    observations.push({taskId:id,model:task.model?.id,status:task.status,cam:task.cam?.status,hasGT:task.has_gt});
    await capture(`desktop-existing-${index+1}-${task.model?.id || 'pcb'}`);
  }
  if (taskIds.length) check(new Set(observations.map(row=>row.model)).size === 3, 'existing tasks cover three different real models');
  for (const modelId of ['unet','unet_resnet18','unetpp_resnet18']) {
    await go('/inspect/pcb');
    check(await page.getByRole('radio').count() === 3, `${modelId} live catalog shows three admitted models`);
    check(await page.getByLabel('PCB 原图',{exact:true}).isEnabled(), `${modelId} isolated service is enabled for acceptance`);
    await page.getByLabel('PCB 原图',{exact:true}).setInputFiles({name:'synthetic-reference-220.png',mimeType:'image/png',buffer:inputImage});
    await readableImage('待分割 PCB 原图',`${modelId} synthetic input preview retains 220 coordinates`);
    await page.locator(`input[type=radio][value="${modelId}"]`).check();
    await page.locator('summary').filter({hasText:'高级选项'}).click();
    await page.getByRole('checkbox',{name:'生成 Grad-CAM',exact:true}).focus();await page.keyboard.press('Space');
    check(!(await page.getByRole('checkbox',{name:'添加配对 GT',exact:true}).isChecked()), `${modelId} new live task deliberately omits GT`);
    if (modelId === 'unet') await capture('desktop-new-synthetic-input');
    const createResponse = page.waitForResponse(r=>new URL(r.url()).pathname === '/api/scenes/pcb/segmentation/tasks' && r.request().method() === 'POST', {timeout:60000});
    await page.getByRole('button',{name:'开始 PCB 分割',exact:true}).click();
    const createdResponse = await createResponse;
    check(createdResponse.ok(), `${modelId} browser submission reached real task API successfully`);
    const created = await createdResponse.json();
    assert.ok(validId(created.id), 'API returned an invalid task identifier');
    newTaskId = created.id;
    await page.waitForURL(`**/inspect/pcb/tasks/${newTaskId}`, {timeout:30000});
    await page.waitForFunction(() => !!document.querySelector('.pcb-result .task-status.ok, .pcb-result .task-status.bad'), null, {timeout:180000});
    check(await page.locator('.pcb-result .task-status.ok').count() === 1, `${modelId} real RQ Worker completed UI-created CPU task`);
    const finalTask = await page.evaluate(async id => {
      const response = await fetch(`/api/tasks/${encodeURIComponent(id)}`, {credentials:'same-origin'});
      if (!response.ok) throw new Error('Final isolated task API request failed');
      return response.json();
    }, newTaskId);
    check(finalTask.status === 'success' && finalTask.model?.id === modelId && finalTask.cam?.status === 'ok', `${modelId} task used selected real model and Grad-CAM`);
    check(finalTask.has_gt === false && finalTask.metrics?.available === false, `${modelId} real API omits no-GT accuracy`);
    check(await page.locator('.pcb-metrics').count() === 0 && (await page.locator('.pcb-no-metrics').innerText()).includes('无法计算真实性能指标'), `${modelId} live page has no numeric GT metrics`);
    await readableImage('PCB 原始图像',`${modelId} new real task original image readable`);
    for (const [label,kind] of layers) {
      const button = page.getByRole('button',{name:label,exact:true});
      check(await button.isEnabled(), `${modelId} ${kind} layer selectable`);
      await button.click();
      await readableImage(`PCB ${label}`, `${modelId} real ${kind} layer readable at 220 coordinates`);
    }
    await downloadPNG(newTaskId,'cam');
    await page.getByRole('button',{name:'原始二值掩码（0/1）',exact:true}).click();await readableImage('PCB 原始二值掩码（0/1）',`${modelId} UI-created task mask readable`);
    await downloadPNG(newTaskId,'pred_mask');
    const payload = await downloadJSON(newTaskId);
    check(payload.has_gt === false && payload.metrics?.available === false, `${modelId} authorized result JSON preserves no-GT policy`);
    createdTasks.push({taskId:newTaskId,model:modelId,status:finalTask.status,cam:finalTask.cam.status,hasGT:false});
    await capture(`desktop-created-${modelId}`);
  }
  check(new Set(createdTasks.map(row=>row.taskId)).size === 3, 'three UI submissions produced independent task records');
  await go('/records?type=pcb_segmentation');
  for (const item of createdTasks) {
    const link = page.locator(`a[href="/inspect/pcb/tasks/${item.taskId}"]`);
    await link.waitFor();check(await link.isVisible(), `${item.model} real task appears in existing history`);
  }
  const historyLink = page.locator(`a[href="/inspect/pcb/tasks/${newTaskId}"]`);
  await capture('desktop-real-history');
  await historyLink.click();await page.waitForURL(`**/inspect/pcb/tasks/${newTaskId}`);
  await page.setViewportSize({width:390,height:1000});await page.locator('.pcb-result-panel').waitFor();
  await readableImage('PCB 原始图像','mobile original image remains readable');
  check(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth+1), 'live result has no 390px horizontal overflow');
  await capture('mobile-created-real-result');
  await go('/inspect/pcb');await page.getByRole('radio').first().waitFor();
  check(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth+1), 'live workbench has no 390px horizontal overflow');
  await capture('mobile-live-workbench');
  // Existing index.html requests Google Fonts. Keep those requests blocked and
  // record them; do not mistake the unchanged shell's optional font for an API
  // or model dependency, and reject every other attempted external request.
  check(blockedRequests.every(url => url === 'https://fonts.googleapis.com:/css2'),
    'only existing optional Google Fonts requests were attempted and blocked; no unexpected egress');
  check(browserErrors.length === 0, 'live browser has no uncaught exceptions');
  check(apiFailures.length === 0, 'live acceptance has no failed HTTP API responses');
  success = true;
} catch (error) {
  const message = redact(error instanceof Error ? error.message : error);
  browserErrors.push(message);
  console.error(`PCB_LIVE_FRONTEND_FAILED: ${message}`);
  if (page) { try { await capture('failure-state'); } catch {} }
  process.exitCode = 1;
} finally {
  const result = {status:success?'PASS':'FAIL',checks:checkCount,assertions:checks,
    environment:'Real isolated FastAPI + RQ Worker + CPU models; no API mocks; synthetic inputs, not test-set accuracy',
    browser:browser?.version() ?? null,existingTasks:observations,createdTasks,taskIds:createdTasks.map(row=>row.taskId),newTaskId,
    blockedRequests,apiFailures,browserErrors:browserErrors.map(redact)};
  try { await fs.writeFile(path.join(output,'results.json'), JSON.stringify(result,null,2),'utf8'); }
  finally {
    await Promise.allSettled([browser?.close(), server?.close()]);
    config.session = '';
  }
}
if (success) console.log(JSON.stringify({status:'PASS',checks:checkCount,taskIds:createdTasks.map(row=>row.taskId),report:path.join(output,'results.json')}));

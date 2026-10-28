// Offline browser regression: all API calls mocked; Vite ignores config/.env.
// Usage: node tests/check_detail_pages.mjs <playwright directory> <artifact directory> [before snapshot root] [model]
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import { createRequire } from 'node:module';
import { fileURLToPath, pathToFileURL } from 'node:url';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const requireWeb = createRequire(path.join(root, 'apps/web/package.json'));
const { chromium } = createRequire(path.join(path.resolve(process.argv[2]), 'package.json'))('./');
const { createServer } = await import(pathToFileURL(requireWeb.resolve('vite')));
const vue = (await import(pathToFileURL(requireWeb.resolve('@vitejs/plugin-vue')))).default;
const scratch = await fs.mkdtemp(path.join(os.tmpdir(), 'steel-details-'));
const output = path.resolve(process.argv[3]);
await fs.mkdir(output, { recursive: true });
const beforeRoot = process.argv[4];
const beforeFiles = ['apps/web/src/views/datasets/DatasetDetailView.vue', 'apps/web/src/views/models/ModelCardView.vue'];
const beforePlugin = { name: 'read-only-before-snapshot', enforce: 'pre', async load(id) {
  if (!beforeRoot || id.includes('?')) return;
  const relative = path.relative(root, id).split(path.sep).join('/');
  if (beforeFiles.includes(relative)) return fs.readFile(path.join(beforeRoot, relative), 'utf8');
} };
const server = await createServer({ root: path.join(root, 'apps/web'), configFile: false, envFile: false,
  envDir: scratch, cacheDir: path.join(scratch, 'cache'), plugins: [beforePlugin, vue()],
  server: { host: '127.0.0.1', port: 5198, strictPort: true, proxy: {} }, logLevel: 'error' });
let browser, checks = 0;
const calls = [], unexpected = [], errors = [], failures = new Set(), holds = [];
let blockedExternalRequests = 0;
const check = (value, text) => { assert.ok(value, text); checks++; console.log(`PASS ${text}`); };
const hold = predicate => {
  let release, entered, timeout;
  const gate = { predicate, released: new Promise(r => { release = r; }), entered: new Promise((r, reject) => {
    entered = () => { clearTimeout(timeout); r(); };
    timeout = setTimeout(() => reject(new Error('Expected held API request was not received')), 15000);
    timeout.unref();
  }), release: () => { clearTimeout(timeout); release(); }, notify: entered };
  holds.push(gate); return gate;
};
const fixed = { id: 'v-fixed', kind: 'preset', sample_count: 26, has_gt: true, eval_ready: true, is_fixed_test: true };
const browse = { id: 'v-browse', kind: 'preset', sample_count: 1, has_gt: false, eval_ready: false, is_fixed_test: false, browse_only: true };
const dataset = id => ({ id, name: `验收模拟 · 数据 ${id}`, preprocess: 'neu_200',
  disclaimer: '验收模拟：正式评测只用 NEU-20；学生不可下载固定测试集 GT。',
  legend: [{ id: 1, name: '夹渣', color: '#e23d2e' }, { id: 2, name: '斑块', color: '#2f9e44' }, { id: 3, name: '划痕', color: '#2f6fed' }],
  versions: id === 'dataset-a' ? [fixed, browse] : [browse] });
const perf = status => ({ status, can_measure: !['queued', 'measuring'].includes(status), param_count: null,
  weight_bytes: null, latency_ms_per_image: null, fps_per_image: null, device: 'cpu', input_kind: 'dummy',
  input_h: 200, input_w: 200, batch: 1, warmup_runs: 3, timed_runs: 10, disclaimer: '仅本机 CPU 前向耗时，未测量不显示数值。' });
const model = (id, extra = {}) => ({ id, name: `验收模拟 · 模型 ${id}`, source: 'builtin', status: 'runnable',
  runnable_here: true, requires_cuda: false, task_type: 'segmentation', input_size: [200, 200],
  in_channels: 3, num_classes: 4, preprocess_id: 'neu_200', preprocess: { name: 'neu_200', width: 200, height: 200 },
  class_map: { 0: '背景', 1: '夹渣', 2: '斑块', 3: '划痕' }, weight_sha256: 'a'.repeat(64),
  metrics_source: '正式评测记录', perf: perf('unmeasured'), ...extra });
const models = new Map(['model-a', 'model-b'].map(id => [id, model(id)]));
models.set('student-a', model('student-a', { source: 'student', status: 'cannot_start', runnable_here: false,
  fail_stage: 'forward', fail_message: '验收模拟：输出需要 logits。', perf: { ...perf('unmeasured'), can_measure: false } }));
const adapt = { fail_stage: 'forward', kind_labels: ['输出接口'], can_apply: true, points: ['验收模拟：保持权重严格加载，检查输出形状。'],
  diff: '验收模拟，不包含真实源码。', llm_status: 'skipped', consent_hint: '请确认后再追加并复检。' };
const sampleSvg = '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200"><rect width="200" height="200" fill="#b7c0c9"/><path d="M120 15 L105 65 L118 115 L96 180" stroke="#566372" stroke-width="5" fill="none"/><text x="12" y="195" font-size="11">SYNTHETIC UI SAMPLE</text></svg>';
try {
  await server.listen(); browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce' });
  await context.route('**/*', async route => {
    const request = route.request(), url = new URL(request.url()), key = url.pathname, method = request.method();
    if (url.hostname !== '127.0.0.1' || url.port !== '5198') { blockedExternalRequests++; return route.abort(); }
    if (!key.startsWith('/api/')) return route.continue();
    calls.push({ key, method, query: url.search });
    const gate = holds.find(x => !x.used && x.predicate(key, url, method));
    if (gate) { gate.used = true; gate.notify(); await gate.released; }
    if (failures.has(key)) return route.fulfill({ status: 503, json: { code: 'TEST_UNAVAILABLE', message: '验收模拟：读取暂时失败' } });
    const json = data => route.fulfill({ json: data });
    if (key === '/api/auth/me') return json({ id: 1, username: '验收模拟用户', role: 'student' });
    if (key === '/api/datasets') return json({ items: [] });
    if (key === '/api/models') return json({ builtins: [...models.values()].filter(x => x.source === 'builtin'), mine: [], shared: [] });
    if (key.startsWith('/api/test-image/')) return route.fulfill({ contentType: 'image/svg+xml', body: sampleSvg });
    const samples = key.match(/^\/api\/datasets\/([^/]+)\/versions\/([^/]+)\/samples$/);
    if (samples) {
      const offset = Number(url.searchParams.get('offset')), total = samples[2] === fixed.id ? 26 : 1;
      return json({ offset, limit: 24, total, items: Array.from({ length: Math.min(24, Math.max(total - offset, 0)) }, (_, i) => ({
        sample_key: `${samples[2]}_${String(offset + i + 1).padStart(2, '0')}`, width: 200, height: 200,
        has_mask: samples[2] === fixed.id, preview_url: '/api/test-image/sample.svg' })) });
    }
    const ds = key.match(/^\/api\/datasets\/([^/]+)$/); if (ds) return json(dataset(ds[1]));
    const card = key.match(/^\/api\/models\/([^/]+)$/); if (card) return json(models.get(card[1]) || model(card[1]));
    const adaptation = key.match(/^\/api\/models\/([^/]+)\/adapt$/);
    if (adaptation && method === 'GET') return json(adapt);
    const measurement = key.match(/^\/api\/models\/([^/]+)\/perf$/);
    if (measurement && method === 'POST') return json(models.get(measurement[1]));
    unexpected.push(`${method} ${key}`); return route.fulfill({ status: 500, json: { message: 'Unexpected endpoint blocked' } });
  });
  const page = await context.newPage(); page.setDefaultTimeout(8000);
  page.on('pageerror', error => errors.push(error.message));
  const go = async route => { await page.goto(`http://127.0.0.1:5198${route}`); await page.waitForLoadState('networkidle'); };
  const navigate = async route => { await page.evaluate(async path => { const { default: router } = await import('/src/router/index.ts'); await router.push(path); }, route); };
  const idle = () => page.waitForLoadState('networkidle');
  const waitFigures = count => page.waitForFunction(n => document.querySelectorAll('figure').length === n, count);
  const capture = async name => {
    await page.evaluate(() => { window.scrollTo(0, 0); const tag = document.createElement('div'); tag.id = 'test-label'; tag.textContent = '界面验收 · 全部业务数据为模拟'; tag.style.cssText = 'position:fixed;right:0;bottom:0;background:#173450;color:white;padding:6px 12px;font-size:12px;z-index:99999'; document.body.append(tag); });
    await page.screenshot({ path: path.join(output, `${name}.png`), fullPage: true });
    await page.locator('#test-label').evaluate(el => el.remove());
  };
  // Route reuse must load the next dataset rather than retaining the first mounted one.
  if (process.argv[5] !== 'model') {
  await go('/datasets/dataset-a');
  check(await page.locator('figure').count() === 24, 'first dataset page shows 24 original previews');
  check(await page.getByRole('link', { name: /下载.*GT/ }).count() === 0, 'dataset page has no fixed GT download link');
  await capture('01-dataset-detail');
  await navigate('/datasets/dataset-b'); await page.getByRole('heading', { name: /数据 dataset-b/ }).waitFor();
  await page.locator('figure').filter({ hasText: 'v-browse_01' }).waitFor();
  check(await page.getByRole('heading', { level: 1 }).innerText().then(t => t.includes('dataset-b')), 'reused dataset route refreshes detail');
  check(await page.locator('figure').count() === 1, 'reused dataset route refreshes samples');

  failures.add('/api/datasets/dataset-a'); await go('/datasets/dataset-a');
  check(await page.getByRole('alert').count() > 0, 'dataset initial failure has persistent alert');
  failures.clear(); await page.getByRole('button', { name: '重新加载', exact: true }).click(); await waitFigures(24);
  check(await page.locator('figure').count() === 24, 'dataset initial failure recovers without reloading browser');
  const samplePath = '/api/datasets/dataset-a/versions/v-fixed/samples';
  failures.add(samplePath); await page.getByRole('button', { name: '下一页', exact: true }).click(); await page.getByRole('alert').waitFor();
  check(await page.getByRole('alert').count() > 0, 'pagination failure has persistent alert');
  await capture('02-dataset-page-error'); failures.clear();
  await page.getByRole('button', { name: /重新加载|重试/ }).click(); await waitFigures(2);
  check(await page.locator('figure').count() === 2, 'pagination retry keeps intended offset');
  await page.getByRole('button', { name: '上一页', exact: true }).click(); await waitFigures(24);
  const oldPage = hold((key, url) => key === samplePath && url.searchParams.get('offset') === '24');
  await page.getByRole('button', { name: '下一页', exact: true }).click(); await oldPage.entered;
  await page.getByRole('radio', { name: /浏览/ }).focus(); await page.keyboard.press('Space');
  await page.locator('figure').filter({ hasText: 'v-browse_01' }).waitFor();
  oldPage.release(); await idle();
  check(await page.locator('figure').allTextContents().then(x => x.length === 1 && x[0].includes('v-browse')), 'late page response cannot overwrite selected version');
  const oldDetail = hold(key => key === '/api/datasets/dataset-a');
  await navigate('/datasets/dataset-a?reload=1');
  // Route param is unchanged here; visit another id then back to start an actual detail request.
  await navigate('/datasets/dataset-b'); await idle(); await navigate('/datasets/dataset-a'); await oldDetail.entered;
  await navigate('/datasets/dataset-b'); await page.getByRole('heading', { name: /数据 dataset-b/ }).waitFor();
  oldDetail.release(); await idle();
  check(await page.getByRole('heading', { level: 1 }).innerText().then(x => x.includes('dataset-b')), 'late dataset detail cannot overwrite newer route');
  }

  failures.add('/api/models/model-a'); await go('/models/model-a');
  check(await page.locator('.main').getByRole('alert').count() > 0, 'model initial failure has persistent alert instead of blank page');
  await capture('03-model-load-error'); failures.clear();
  await page.getByRole('button', { name: '重新加载', exact: true }).click(); await page.getByRole('heading', { name: /模型 model-a/ }).waitFor();
  check(await page.getByRole('heading', { level: 1 }).innerText().then(x => x.includes('model-a')), 'model retry restores detail');
  check(await page.getByText('未测量', { exact: false }).count() > 0, 'unmeasured model does not invent speed');
  await capture('04-model-detail');
  const delayedModel = hold(key => key === '/api/models/model-b');
  await navigate('/models/model-b'); await delayedModel.entered;
  check(await page.getByRole('button', { name: '加入缺陷分割', exact: true }).count() === 0 || await page.getByRole('button', { name: '加入缺陷分割', exact: true }).isDisabled(), 'old model cannot be submitted while new card loads');
  await navigate('/models/model-a'); await page.getByRole('heading', { name: /模型 model-a/ }).waitFor();
  delayedModel.release(); await idle();
  check(await page.getByRole('heading', { level: 1 }).innerText().then(x => x.includes('model-a')), 'late model response cannot overwrite newer route');
  const measurement = hold((key, _url, method) => key === '/api/models/model-a/perf' && method === 'POST');
  await page.getByRole('button', { name: '测量参数量与耗时', exact: true }).click(); await measurement.entered;
  check(await page.getByRole('button', { name: '测量参数量与耗时', exact: true }).isDisabled(), 'in-flight measurement disables duplicate submission');
  await navigate('/models/model-b'); await page.getByRole('heading', { name: /模型 model-b/ }).waitFor();
  measurement.release(); await idle();
  check(await page.getByRole('heading', { level: 1 }).innerText().then(x => x.includes('model-b')), 'late measurement response cannot replace another model');

  await go('/models/student-a'); await page.getByRole('button', { name: '按方案追加并复检', exact: true }).waitFor();
  await capture('05-model-diagnosis');
  await page.getByRole('button', { name: '按方案追加并复检', exact: true }).click(); await page.locator('.el-message-box').waitFor();
  await navigate('/models/model-b'); await page.getByRole('heading', { name: /模型 model-b/ }).waitFor();
  const confirm = page.getByRole('button', { name: '按方案复检', exact: true });
  if (await confirm.isVisible()) await confirm.click(); await idle();
  check(calls.filter(x => x.method === 'POST' && x.key.endsWith('/adapt')).length === 0, 'leaving diagnosis cancels pending consent for original model');

  models.set('model-a', model('model-a', { source: 'student', status: 'checking', runnable_here: false }));
  await go('/models/model-a');
  models.set('model-a', model('model-a'));
  await page.getByRole('button', { name: '加入缺陷分割', exact: true }).waitFor();
  await page.waitForFunction(() => { const button = [...document.querySelectorAll('button')].find(x => x.textContent.includes('加入缺陷分割')); return button && !button.disabled; });
  check(true, 'opening checking model automatically observes completed admission');

  // Leave with a read in flight and the same :id in another view (old id-only guard misses this).
  models.set('model-a', model('model-a', { perf: perf('queued') }));
  await go('/models/model-a');
  const polling = hold(key => key === '/api/models/model-a');
  await polling.entered;
  await navigate('/datasets/model-a'); await page.getByRole('heading', { name: /数据 model-a/ }).waitFor();
  polling.release(); await idle(); const countAfterLeave = calls.filter(x => x.key === '/api/models/model-a').length;
  await page.waitForTimeout(5400);
  check(calls.filter(x => x.key === '/api/models/model-a').length === countAfterLeave, 'unmounted model page stops polling even when route id matches');
  await go('/models/model-a');
  failures.add('/api/models/model-a');
  await page.locator('.main').getByRole('alert').waitFor();
  check(await page.getByRole('button', { name: '测量中', exact: true }).isDisabled(), 'poll failure blocks new measurement while status is uncertain');
  const countAfterFailure = calls.filter(x => x.key === '/api/models/model-a').length;
  await page.waitForTimeout(3400);
  check(calls.filter(x => x.key === '/api/models/model-a').length === countAfterFailure, 'poll failure pauses automatic requests');
  await capture('06-model-poll-error');
  const postsBeforeRetry = calls.filter(x => x.method === 'POST').length;
  failures.clear();
  models.set('model-a', model('model-a'));
  await page.getByRole('button', { name: '重新加载', exact: true }).click();
  await page.getByRole('button', { name: '测量参数量与耗时', exact: true }).waitFor();
  check(await page.getByRole('button', { name: '测量参数量与耗时', exact: true }).isEnabled(), 'poll retry refreshes current status and restores actions');
  check(calls.filter(x => x.method === 'POST').length === postsBeforeRetry, 'retry after poll failure only reads and never resubmits measurement');
  for (const width of [1440, 768, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    for (const target of ['/datasets/dataset-a', '/models/model-a', '/models/student-a']) {
      await go(target);
      check(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `${target} no horizontal overflow at ${width}px`);
      await capture(`${width}-${target.split('/').filter(Boolean).join('-')}`);
    }
  }
  check(unexpected.length === 0, `no unmocked/external API calls: ${unexpected.join(',')}`);
  check(errors.length === 0, `no browser exceptions: ${errors.join(',')}`);
  check(calls.filter(x => x.method === 'POST').every(x => x.key === '/api/models/model-a/perf'), 'only explicitly mocked measurement POST was issued');
  await fs.rm(path.join(output, 'failure-context.json'), { force: true });
  await fs.writeFile(path.join(output, 'detail-test-results.json'), JSON.stringify({ checks, browser: browser.version(), mockedApiCalls: calls.length, blockedExternalRequests, unexpected, errors, isolation: 'No .env, backend, DB, Redis, Docker, LLM or inference; all business data synthetic.' }, null, 2));
  console.log(`PASS ${checks} detail assertions; ${calls.length} mocked requests.`);
} catch (error) {
  await fs.writeFile(path.join(output, 'failure-context.json'), JSON.stringify({ error: error.message, calls, unexpected, errors }, null, 2));
  throw error;
} finally {
  holds.forEach(gate => gate.release());
  if (browser) await browser.close(); await server.close();
}

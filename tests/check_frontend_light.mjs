// Isolated UI acceptance: no .env, API proxy, database, Redis, Docker or model calls.
// Usage: node tests/check_frontend_light.mjs <absolute playwright package directory> [artifact directory]
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath, pathToFileURL } from 'node:url';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const requireWeb = createRequire(path.join(root, 'apps/web/package.json'));
const { chromium } = process.argv[2] ? createRequire(path.join(path.resolve(process.argv[2]), 'package.json'))('./') : requireWeb('playwright');
const { createServer } = await import(pathToFileURL(requireWeb.resolve('vite')));
const vue = (await import(pathToFileURL(requireWeb.resolve('@vitejs/plugin-vue')))).default;
const scratch = await fs.mkdtemp(path.join(os.tmpdir(), 'steel-ui-check-'));
const output = path.resolve(process.argv[3] || path.join(scratch, 'screenshots'));
await fs.mkdir(output, { recursive: true });
const server = await createServer({ root: path.join(root, 'apps/web'), configFile: false, envFile: false,
  envDir: scratch, cacheDir: path.join(scratch, 'vite-cache'), plugins: [vue()],
  server: { host: '127.0.0.1', port: 5197, strictPort: true, proxy: {} }, logLevel: 'error' });
let browser;
let checks = 0;
const check = (condition, message) => { assert.ok(condition, message); checks++; console.log(`PASS ${message}`); };
const builtins = ['UNet', 'DeepLabV3+', 'UNet++', 'PSPNet'].map((name, i) => ({ id: `builtin-${i}`, name, slug: name.toLowerCase(), source: 'builtin', status: 'runnable', runnable_here: true, requires_cuda: false, fps_per_image: null }));
// Values below are synthetic serialization fixtures, never actual benchmark claims.
const pageIntroduction = '智能感知与精密工业检测实验室（Intelligent Perception and Precision Industrial Inspection Laboratory，简称 IPPI Lab）由江西师范大学与江西博方教育科技集团有限公司联合筹建，依托江西师范大学人工智能学院，由邹翔博士领衔建设，是面向高端智能制造精密质检领域的产学研协同创新平台。共建单位江西博方教育科技集团为高新技术企业、省级专精特新中小企业，组建专职研发团队深度参与科研攻关，提供工程化开发、场景验证与成果转化支撑。实验室团队汇聚高校科研骨干、企业研发人员、硕士研究生及优秀本科生，聚焦工业缺陷检测、工业图像精密分割方向，开展智能感知基础算法研究，攻克高端制造精密质检关键技术瓶颈。相关研究先后获国家自然科学基金（62202211）、江西省科技创新基地计划项目（20242BCC32021）资助，已搭建高性能算力平台与工业仿真实验环境。实验室坚持校企协同、本研衔接育人，在学科竞赛、学术产出、拔尖人才培养方面已取得阶段性成效。实验室现未来将紧扣智能制造国家战略，充分融合高校学科创新优势与企业工程落地能力，致力打造省内领先、国内具有一定影响力的工业视觉科研创新、成果转化与高水平人才培养基地。';
const demoBuiltins = [...builtins, ...['BiSeNet', 'DANet', 'SegFormer'].map((name, i) => ({ id: `demo-extra-${i}`, name, slug: name.toLowerCase() }))].map((model, i) => ({ ...model, param_count: i === 0 ? 1250000 : null, fps_per_image: i === 0 ? 2.5 : null }));
const legend = [{ id: 1, name: '夹渣', color: '#e23d2e' }, { id: 2, name: '斑块', color: '#2f9e44' }, { id: 3, name: '划痕', color: '#2f6fed' }];
const rows = [
  { id: 'synthetic-compare-no-gt', type: 'compare', type_label: '快速对比', status: 'success', has_gt: false, error_summary: null, bundle_ready: false, bundle_unavailable_reason: '验收模拟：图层包不存在' },
  { id: 'synthetic-running', type: 'compare', type_label: '快速对比', status: 'running', has_gt: false, bundle_ready: false },
  { id: 'synthetic-failed', type: 'eval', type_label: '正式评测', status: 'failed', has_gt: true, error_summary: '验收模拟：严格权重加载失败，请查看模型检查结果。', bundle_ready: false },
];
const task = { ...rows[0], n: 2, samples: [{ id: 'sample-a', sample_key: 'synthetic_01' }, { id: 'sample-b', sample_key: 'synthetic_02' }], preview_sample_keys: ['synthetic_01', 'synthetic_02'], legend,
  models: builtins.slice(0, 2).map(x => ({ model_version_id: x.id, name: x.name, status: 'success', role: 'baseline' })),
  artifacts: [{ kind: 'origin', sample_key: 'synthetic_01', model_version_id: null, url: '/api/test-image/origin.png' },
    { kind: 'montage', sample_key: 'synthetic_01', url: '/api/test-image/synthetic_01__mask.png' },
    { kind: 'montage', sample_key: 'synthetic_01', url: '/api/test-image/synthetic_01__cam_c2.png' },
    { kind: 'montage', sample_key: 'synthetic_02', url: '/api/test-image/synthetic_02__mask.png' }] };
const assistantTask = { ...rows[0], n: 2 };
const syntheticSession = { id: 'synthetic-session', title: '验收模拟：无 GT 结果分析', specialty: 'segment', llm_ready: false, working: { task_id: rows[0].id }, turns: [
  { id: 'user-1', role: 'user', content: '验收模拟：这批没有配对掩码，可以比较精度吗？' },
  { id: 'assistant-1', role: 'assistant', llm_status: 'skipped', evidence_pack: {
    task: { ...assistantTask, preprocess: { name: 'neu_200', width: 200, height: 200 }, open_path: '/compare/synthetic-compare-no-gt' }, metrics: { available: false },
    judgements: [{ grade: 'measurement', text: '验收模拟：本批未提供完整配对 GT，仅生成可视化。' }, { grade: 'rule', text: '无 GT 时不报告 mIoU / mDice，也不能据此比较精度。' }, { grade: 'speculation', text: '可先检查预测边界，再在完整配对后进行实验。' }] } },
] };
const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="840" height="300"><rect width="840" height="300" fill="#273442"/><g fill="#8793a0"><rect x="12" y="40" width="260" height="245"/><rect x="290" y="40" width="260" height="245"/><rect x="568" y="40" width="260" height="245"/></g><g stroke="#e23d2e" stroke-width="8" fill="none"><path d="M180 65 L165 120 L182 190 L160 260"/><path d="M458 65 L443 120 L460 190 L438 260"/><path d="M736 65 L721 120 L738 190 L716 260"/></g><g font-family="sans-serif" font-size="16" fill="white"><text x="24" y="26">Synthetic original</text><text x="302" y="26">UNet / synthetic mask</text><text x="580" y="26">DeepLabV3+ / synthetic mask</text></g></svg>`;
const sampleSvg = `<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200"><defs><linearGradient id="g"><stop stop-color="#858f99"/><stop offset=".5" stop-color="#adb5bc"/><stop offset="1" stop-color="#7a8793"/></linearGradient></defs><rect width="200" height="200" fill="url(#g)"/><g stroke="#737e88" opacity=".5"><path d="M20 0v200M37 0v200M52 0v200M87 0v200M102 0v200M149 0v200M175 0v200M188 0v200"/></g><path d="m119 12-9 41 6 39-12 45 4 49" stroke="#4b5662" stroke-width="5" fill="none"/><rect y="174" width="200" height="26" fill="#20364d"/><text x="12" y="191" fill="white" font-family="sans-serif" font-size="11">SYNTHETIC UI SAMPLE</text></svg>`;
const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScLbtAAAAABJRU5ErkJggg==', 'base64');
const upload = name => ({ name, mimeType: 'image/png', buffer: png });
const catalogFixture = { stats: { research_models: 2, papers: 1, updated_at: '2026-10-27' },
  models: [{ id: 'catalog-model-1', name: '验收模拟 · 分割文献条目', task_type: 'segmentation', year: 2026, backbone: '示例结构', keywords: '界面验证', detail: '本条仅用于浏览器展示验收，不是已发表模型或可运行权重。' }],
  datasets: [{ id: 'catalog-dataset-1', name: '验收模拟 · 数据集条目', task_type: 'segmentation', source_object: '界面夹具', numbers_text: '规模未提供', access_note: '仅用于目录布局检查，不提供下载。' }],
  works: [{ id: 'catalog-work-1', name: '验收模拟 · 研究成果条目', kind: 'paper', year: 2026, venue: '界面验收夹具', authors: '模拟作者', summary: '仅验证成果卡片、详情和导师管理入口，不代表真实学术成果。' }],
  funds: [{ id: 'catalog-fund-1', name: '验收模拟 · 科研项目条目', source: 'other', role: 'pi', status: 'ongoing', start_year: 2026, detail: '界面验收夹具，未填写项目号或金额。' }] };
let dashboardFailure = false, dashboardEmpty = false, emptyRecordPage = false, catalogFailure = false, signedIn = true, role = 'student';
const failingPaths = new Set();
let raceRecords = false, releaseOldRecord;
// A populated catalog verifies wrapping across rows, rather than only a single card.
catalogFixture.models = Array.from({ length: 9 }, (_, i) => ({ ...catalogFixture.models[0], id: `catalog-model-${i}`, name: `验收模拟 · 分割文献 ${i + 1}` }));
catalogFixture.datasets = Array.from({ length: 6 }, (_, i) => ({ ...catalogFixture.datasets[0], id: `catalog-dataset-${i}`, name: `验收模拟 · 数据资源 ${i + 1}`, image_count: i ? null : 1200, class_count: i ? null : 3 }));
const apiCalls = [], unexpected = [], errors = [];
try {
  await server.listen();
  browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1672, height: 941 }, reducedMotion: 'reduce' });
  await context.route('**/*', async route => {
    const request = route.request(), url = new URL(request.url()), key = url.pathname;
    if (url.hostname !== '127.0.0.1' || url.port !== '5197') return route.abort();
    if (!key.startsWith('/api/')) return route.continue();
    apiCalls.push({ key, method: request.method(), body: request.postDataJSON?.bind(request) });
    const json = data => route.fulfill({ json: data });
    if (failingPaths.has(key)) return route.fulfill({ status: 503, json: { code: 'TEST_READ_UNAVAILABLE', message: '验收模拟：读取失败，请重试' } });
    if (key === '/api/records' && raceRecords && url.searchParams.get('type')) {
      const old = url.searchParams.get('type') === 'compare';
      if (old) await new Promise(resolve => { releaseOldRecord = resolve; });
      return json({ items: [{ ...rows[0], id: old ? 'older-result' : 'newer-result', note: old ? '过期响应' : '最新筛选结果', open_path: '/compare/synthetic-compare-no-gt' }], total: 1 });
    }
    if (key.startsWith('/api/test-image/')) return route.fulfill({ contentType: 'image/svg+xml', body: key.endsWith('/origin.png') ? sampleSvg : svg });
    if (key === '/api/catalog') return catalogFailure ? route.fulfill({ status: 503, json: { code: 'TEST_CATALOG_UNAVAILABLE', message: '验收模拟：目录暂不可用' } }) : json(catalogFixture);
    if (key === '/api/auth/me') return signedIn ? json({ id: 1, username: '验收模拟用户', role }) : route.fulfill({ status: 401, json: { detail: 'UI test guest' } });
    if (key === '/api/me/dashboard') return dashboardFailure ? route.fulfill({ status: 503, json: { stage: 'resource', code: 'TEST_UNAVAILABLE', message: '验收模拟：工作台暂不可用' } }) : json({ notices: [], recent_tasks: dashboardEmpty ? [] : rows, active_tasks: dashboardEmpty ? [] : [rows[1]], failed_tasks: dashboardEmpty ? [] : [rows[2]], recent_models: dashboardEmpty ? [] : [{ id: 'student-example', name: '学生模型 · 验收示例', status: 'checking', fail_stage: null }] });
    if (key === '/api/models') return json({ builtins, mine: [], shared: [] });
    if (key === '/api/records') return json({ items: emptyRecordPage && url.searchParams.get('page') === '2' ? [] : [{ ...rows[0], note: '验收模拟记录', created_at: '2026-10-26T12:00:00', open_path: '/compare/synthetic-compare-no-gt', can_note: true, can_archive: true, can_rerun: false, can_submit: false, can_withdraw: false, can_analyze: false }], total: emptyRecordPage ? 25 : 1 });
    if (key === '/api/demo/models') return json({ items: demoBuiltins });
    if (key === '/api/demo/samples') return json({ items: Array.from({ length: 20 }, (_, i) => ({ sample_key: `synthetic_${i + 1}`, width: 200, height: 200, preview_url: '/api/test-image/origin.png' })), legend });
    if (key === '/api/demo/tasks' && request.method() === 'POST') return json({ id: 'synthetic-demo' });
    if (key === '/api/demo/tasks/synthetic-demo') return json({ ...task, type: 'demo', disclaimer: '公开演示 / 预备样例 / 不代表测试集性能' });
    if (key === '/api/assistant/sessions') return json({ items: [{ id: syntheticSession.id, title: syntheticSession.title, specialty: syntheticSession.specialty }], llm_ready: false });
    if (key === '/api/assistant/tasks') return json({ items: [assistantTask], llm_ready: false });
    if (key === '/api/assistant/sessions/synthetic-session') return json(syntheticSession);
    if (key === '/api/tasks/synthetic-compare-no-gt') return json(task);
    if (key === '/api/tasks/synthetic-compare-no-gt/metrics') return json({ available: false });
    if (key === '/api/datasets') return json({ items: [] });
    unexpected.push(key); return route.fulfill({ status: 500, json: { detail: 'Unmocked endpoint blocked' } });
  });
  const page = await context.newPage();
  page.on('pageerror', error => errors.push(error.message));
  const go = async route => { await page.goto(`http://127.0.0.1:5197${route}`); await page.waitForLoadState('networkidle'); };
  const capture = async (name, fullPage = true) => {
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    await page.evaluate(() => { const label = document.createElement('div'); label.id = 'acceptance-label'; label.textContent = '浏览器验收 · 全部业务数据为模拟 · 非实测结果'; label.style.cssText = 'position:fixed;bottom:0;right:0;padding:5px 12px;background:#14283e;color:white;font:11px sans-serif;z-index:99999'; document.body.append(label); });
    await page.screenshot({ path: path.join(output, `${name}.png`), fullPage });
    await page.locator('#acceptance-label').evaluate(node => node.remove());
  };
  const noOverflow = async route => check(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `${route}: no page-level horizontal overflow`);
  const contrastCheck = async selector => {
    const results = await page.locator(selector).evaluateAll(nodes => {
      const rgb = color => (color.match(/[\d.]+/g) || []).map(Number);
      const luminance = color => color.slice(0, 3).map(v => { v /= 255; return v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4; }).reduce((n, v, i) => n + v * [.2126, .7152, .0722][i], 0);
      return nodes.filter(node => node.getClientRects().length).map(node => {
        let parent = node, bg;
        while (parent) { const candidate = rgb(getComputedStyle(parent).backgroundColor); if (candidate.length === 3 || candidate[3] === 1) { bg = candidate; break; } parent = parent.parentElement; }
        const fgL = luminance(rgb(getComputedStyle(node).color)), bgL = luminance(bg || [255, 255, 255]);
        return { text: node.textContent.trim(), ratio: (Math.max(fgL, bgL) + .05) / (Math.min(fgL, bgL) + .05) };
      });
    });
    check(results.length > 0 && results.every(item => item.ratio >= 4.5), `catalog normal text contrast >=4.5: ${selector} ${JSON.stringify(results.filter(item => item.ratio < 4.5))}`);
  };
  await go('/workbench');
  check(await page.locator('html').getAttribute('class') === 'workbench-light', 'light theme applied');
  check(await page.locator('.summary-card strong').allTextContents().then(x => x.map(v => v.replace(/\D/g, '')).join(',') === '1,3,1'), 'dashboard counts reflect bounded response arrays');
  check(await page.locator('.shortcut-grid .shortcut').count() === 4, 'dashboard has four primary workflow cards');
  check(await page.locator('.dashboard-rail .wb-panel').count() === 3, 'dashboard separates attention, activity and imported models');
  check(await page.locator('.workspace-bar').evaluate(node => getComputedStyle(node).backgroundColor) === 'rgb(255, 255, 255)', 'workspace has a distinct white top bar');
  check(await page.locator('.main').innerText().then(x => !x.includes('GPU') && !x.includes('存储')), 'no invented resource telemetry');
  await capture('01-workbench'); await noOverflow('desktop dashboard');
  dashboardFailure = true; await go('/workbench');
  check(await page.getByText('验收模拟：工作台暂不可用', { exact: false }).count() > 0, 'dashboard error is visible');
  check(await page.locator('.summary-grid').count() === 0, 'failed load does not display zero statistics');
  dashboardFailure = false; dashboardEmpty = true; await page.getByText('重新加载', { exact: true }).click();
  await page.getByText('还没有任务，从新建分割对照开始。').waitFor(); check(true, 'dashboard retry and empty state'); await capture('01b-workbench-empty'); dashboardEmpty = false;
  await go('/inspect/steel/segmentation');
  check(await page.locator('.wb-model-choices strong').evaluateAll(nodes => nodes.length > 0 && nodes.every(n => parseFloat(getComputedStyle(n).fontSize) >= 15)), 'comparison model names use the readable primary scale');
  await capture('02a-steel-submission-empty');
  const inputs = page.locator('input[type=file]');
  await inputs.nth(0).setInputFiles([upload('steel_01.png'), upload('steel_02.png')]);
  check(await page.getByRole('button', { name: '开始对照', exact: true }).isEnabled(), 'no GT comparison remains submittable');
  await inputs.nth(1).setInputFiles(upload('steel_01.png'));
  check(await page.getByText('已配对 1 / 2。', { exact: false }).count() === 1, 'partial GT pairing explained');
  check(await page.getByRole('button', { name: '开始对照', exact: true }).isEnabled(), 'partial GT comparison remains submittable');
  await capture('02-steel-submission');
  await inputs.nth(1).setInputFiles(upload('steel_02.png'));
  check(await page.getByText('已全部配对 2 张', { exact: false }).count() === 1, 'full GT pairing explained');
  await inputs.nth(1).setInputFiles(upload('unpaired.png'));
  check(await page.getByRole('button', { name: '开始对照', exact: true }).isDisabled(), 'extra masks block submission');
  check(await page.getByRole('checkbox', { name: /PSPNet/ }).isDisabled(), 'comparison maximum three baselines');
  await go('/compare/synthetic-compare-no-gt');
  check(await page.locator('.result-viewer').evaluate(node => getComputedStyle(node).backgroundColor) === 'rgb(255, 255, 255)', 'result uses a white evidence viewer card');
  check(await page.locator('.metrics').count() === 0, 'no GT result has no numeric metric panel');
  check(await page.getByRole('button', { name: '下载图层包（供 Draw.io）', exact: true }).isDisabled(), 'bundle_ready=false disables download');
  check(await page.getByRole('button', { name: '本张 GT', exact: true }).count() === 0, 'unauthorized GT is absent');
  await page.getByText('热力图', { exact: true }).click();
  check(await page.getByText('当前类别暂无热力图', { exact: false }).count() === 1, 'missing selected CAM class has empty state');
  await page.getByText('斑块', { exact: true }).last().click();
  check(await page.locator('.stage img').getAttribute('src').then(x => x.includes('__cam_c2')), 'other available CAM class remains selectable');
  await page.getByText('彩色掩码拼图', { exact: true }).click(); await capture('03-compare-result');
  check(await page.getByRole('button', { name: '上一张', exact: true }).isDisabled(), 'result starts at first authorized sample');
  await page.getByRole('button', { name: '下一张', exact: true }).click();
  check(await page.locator('.stage img').getAttribute('src').then(x => x.includes('synthetic_02__mask')), 'new result pager switches authorized sample');
  check(await page.getByRole('button', { name: '下一张', exact: true }).isDisabled(), 'result pager stops at last sample');
  await page.getByRole('button', { name: '上一张', exact: true }).click();
  check(await page.locator('.stage img').getAttribute('src').then(x => x.includes('synthetic_01__mask')), 'result pager returns to first sample');
  await go('/models/import'); await page.getByRole('combobox', { name: '输入通道' }).focus(); await page.keyboard.press('Enter');
  check(await page.getByRole('option').allTextContents().then(x => x.join(',') === '1 · 灰度,3 · RGB'), 'model input channels restricted to 1 or 3');
  check(await page.locator('.el-select-dropdown:visible').evaluate(node => getComputedStyle(node.closest('.el-popper')).backgroundColor) === 'rgb(255, 255, 255)', 'teleported select uses light surface');
  await page.getByRole('option', { name: '3 · RGB' }).click(); await capture('04-model-import');
  await page.getByLabel('模型源码 .py', { exact: true }).setInputFiles({ name: 'synthetic_model.py', mimeType: 'text/plain', buffer: Buffer.from('# UI test fixture only; not executed') });
  await page.getByLabel('模型权重 .pth', { exact: true }).setInputFiles({ name: 'synthetic_weights.pth', mimeType: 'application/octet-stream', buffer: Buffer.from('UI fixture; not model weights') });
  await page.getByPlaceholder('例如 残差UNet-实验3').fill('验收模拟模型');
  check(await page.locator('.file-drop.selected').count() === 2, 'new file cards reflect selected source and weights');
  check(await page.getByRole('button', { name: '开始检查', exact: true }).isEnabled(), 'selected files preserve import form readiness without submitting');
  check(await page.locator('.check-timeline .ok').count() === 0, 'file selection does not invent completed admission stages');
  await capture('04b-model-files-selected');
  await go('/records'); await capture('06-records');
  check(await page.getByText('学生提交', { exact: true }).count() === 0, 'student has no advisor inbox');
  await page.getByRole('button', { name: '更多记录操作' }).click();
  check(await page.getByRole('menuitem', { name: '再跑', exact: true }).count() === 0, 'can_rerun=false hides rerun action');
  check(await page.getByRole('menuitem', { name: '提交导师', exact: true }).count() === 0, 'can_submit=false hides submission');
  await page.getByRole('menuitem', { name: '备注', exact: true }).click();
  await page.locator('.el-message-box').waitFor();
  check(await page.locator('.el-message-box').evaluate(node => getComputedStyle(node).backgroundColor) === 'rgb(255, 255, 255)', 'teleported note dialog uses light theme');
  await page.getByRole('button', { name: '取消', exact: true }).click();
  role = 'advisor'; await go('/records'); check(await page.getByText('学生提交', { exact: true }).count() === 1, 'advisor retains inbox selector'); role = 'student';
  emptyRecordPage = true; await go('/records'); await page.getByRole('button', { name: '下一页', exact: true }).click();
  await page.getByText('当前页暂无记录，共 25 条', { exact: true }).waitFor();
  check(await page.getByRole('button', { name: '上一页', exact: true }).isEnabled(), 'empty record page retains previous-page navigation');
  await page.getByRole('button', { name: '上一页', exact: true }).click();
  await page.getByText('验收模拟记录', { exact: true }).waitFor(); check(true, 'record pager recovers from empty page'); emptyRecordPage = false;
  await go('/assistant'); await capture('05-assistant');
  check(await page.locator('.pills .pill').allTextContents().then(x => x.join(',') === '学术,分割,模型'), 'assistant keeps exactly three manual specialties');
  await page.locator('.suggest button').first().focus(); await page.keyboard.press('Enter');
  check(await page.locator('textarea').inputValue().then(x => x.length > 0), 'assistant suggestions keyboard operable');
  await page.getByRole('button', { name: '对话列表', exact: true }).click();
  await page.locator('.session-list li').filter({ hasText: syntheticSession.title }).click();
  await page.getByRole('button', { name: '收起', exact: true }).click();
  await page.locator('.evidence-card').waitFor();
  check(await page.locator('.context-facts').innerText().then(x => x.includes('不可用') && x.includes('2')), 'assistant context rail reflects authorized task facts');
  check(await page.locator('.evidence-card .metrics').count() === 0, 'assistant no-GT evidence has no numeric metric panel');
  await capture('05b-assistant-evidence');
  await page.locator('.pills .pill').filter({ hasText: '模型' }).click();
  check(await page.locator('.feed').count() === 0 && await page.locator('.context-empty').innerText().then(x => x.includes('尚未选择模型')), 'manual specialty change clears previous task context');
  await go('/demo'); for (let i = 0; i < 6; i++) await page.locator('.coupon').nth(i).click();
  check(await page.locator('.coupon.on').count() === 5, 'demo sample cap of five retained');
  for (let i = 0; i < 3; i++) await page.locator('.wb-model-choices .el-checkbox').nth(i).click();
  check(await page.getByRole('checkbox', { name: /PSPNet/ }).isDisabled(), 'demo baseline cap of three retained');
  check(await page.locator('input[type=file]').count() === 0 && await page.locator('.metrics').count() === 0, 'demo exposes no uploads or metric panel');
  check(await page.locator('.coupon img').evaluateAll(nodes => nodes.every(n => n.getBoundingClientRect().width <= 113 && n.getBoundingClientRect().height <= 113 && getComputedStyle(n).objectFit === 'contain')), 'demo thumbnails are bounded and preserve full image');
  check(await page.locator('.demo-models .wb-model-choices strong').evaluateAll(nodes => nodes.length > 0 && nodes.every(n => parseFloat(getComputedStyle(n).fontSize) >= 16)), 'demo model names have readable primary typography');
  check(await page.locator('.demo-models .wb-model-choices').evaluate(n => getComputedStyle(n).gridTemplateColumns.split(' ').length === 2), 'desktop demo model cards form two columns');
  check(await page.locator('.demo-models .el-checkbox').first().innerText().then(text => text.includes('1.25 M') && text.includes('2.50 图/秒')), 'demo displays persisted parameter and speed fixture with units');
  check(await page.locator('.demo-models .el-checkbox').nth(1).innerText().then(text => (text.match(/未测量/g) || []).length === 2), 'demo missing measurements remain explicit rather than invented');
  check(await page.locator('.tray').evaluate(n => n.scrollHeight > n.clientHeight && n.clientHeight <= 400), 'twenty demo samples use a bounded scrollable catalog');
  await capture('07-public-demo'); await page.getByRole('button', { name: '开始演示', exact: true }).click();
  await page.waitForURL('**/demo/synthetic-demo'); await page.waitForLoadState('networkidle');
  check(await page.locator('.metrics').count() === 0, 'demo result never exposes metric panel');
  // Steel classification now has a dedicated upload/result acceptance suite.
  for (const route of ['/inspect/steel/detection', '/inspect/pcb', '/inspect/solar']) {
    await go(route); check(await page.getByRole('button', { name: '提交任务（未开放）', exact: true }).isDisabled(), `${route}: submission remains disabled`);
  }
  signedIn = false; await go('/'); check(await page.locator('html').getAttribute('class') === 'workbench-light', 'public homepage uses the unified light theme');
  check(await page.locator('body').textContent().then(x => x.includes('实验室现未来将')), 'original laboratory introduction retained in homepage');
  check(await page.locator('.brand .title').innerText() === 'IPPI LAB' && await page.locator('.brand .sub').innerText() === '智能感知与精密工业检测实验室', 'sidebar uses requested IPPI LAB identity');
  check(await page.locator('.hero-desc').isVisible() && await page.locator('.hero-desc').textContent().then(text => text.trim() === pageIntroduction), 'complete requested laboratory introduction is visible in hero');
  check(await page.locator('.hero-desc').evaluate(n => parseFloat(getComputedStyle(n).fontSize) >= 17 && n.scrollHeight <= n.clientHeight + 1), 'hero introduction is larger and not clipped');
  await contrastCheck('#defect-models .name, #defect-models .meta, #defect-models .method-tags span, #defect-models .resource-label, #defect-models .kind, #defect-models .ext');
  await contrastCheck('#defect-datasets .name, #defect-datasets .row, #defect-datasets .row-label, #defect-datasets .resource-label, #defect-datasets .kind, #defect-datasets .ext, #defect-datasets .missing');
  check(await page.locator('.main').evaluate(node => getComputedStyle(node).backgroundColor) === 'rgb(243, 246, 252)', 'homepage matches workbench canvas');
  check(await page.locator('.stat-value').allTextContents().then(x => x.join(',') === '2,1'), 'homepage statistics come from catalog response');
  check(await page.getByRole('button', { name: '上传成果', exact: true }).count() === 0 && await page.getByRole('button', { name: '编辑统计', exact: true }).count() === 0, 'guest cannot see advisor catalog editing');
  await capture('00-home'); await capture('00-home-first-screen', false); await noOverflow('desktop public homepage');
  await page.locator('#defect-models').screenshot({ path: path.join(output, '00b-home-model-cards.png') });
  await page.locator('#defect-datasets').screenshot({ path: path.join(output, '00c-home-dataset-cards.png') });
  await page.locator('.section-nav').getByRole('link', { name: '关于实验室', exact: true }).click();
  check(await page.locator('#about-lab').getAttribute('open') !== null && await page.locator('.lab-full-introduction').isVisible(), 'homepage about navigation reveals full introduction');
  await page.locator('#defect-models').getByRole('button', { name: '分类', exact: true }).click();
  check(await page.locator('#defect-models .card').count() === 0, 'homepage task filter respects catalog data');
  await page.locator('#defect-models').getByRole('button', { name: '分割', exact: true }).click();
  check(await page.locator('#defect-models .card').count() === 9, 'homepage segmentation filter restores matching entries');
  await page.locator('#research-works').getByRole('button', { name: '查看详情', exact: true }).click();
  await page.locator('.el-dialog:visible').waitFor();
  check(await page.locator('.el-dialog:visible').evaluate(n => getComputedStyle(n).backgroundColor) === 'rgb(255, 255, 255)', 'homepage catalog dialog shares the light theme');
  await page.keyboard.press('Escape');
  await page.locator('.hero-actions').getByRole('link', { name: '进入工作台', exact: true }).click(); await page.waitForURL('**/login?**'); await page.waitForLoadState('networkidle');
  check(new URL(page.url()).searchParams.get('redirect') === '/workbench', 'homepage guest workbench CTA retains login redirect');
  await capture('11-login'); await noOverflow('desktop login');
  check(await page.getByRole('textbox', { name: '用户名', exact: true }).isVisible() && await page.getByLabel('密码', { exact: true }).count() === 1, 'login fields retain accessible labels');
  signedIn = true; role = 'advisor'; await go('/');
  check(await page.getByRole('button', { name: '上传成果', exact: true }).isVisible() && await page.getByRole('button', { name: '编辑统计', exact: true }).isVisible(), 'advisor retains catalog management controls'); role = 'student';
  catalogFailure = true; await go('/');
  check(await page.getByText('验收模拟：目录暂不可用', { exact: false }).count() > 0, 'homepage catalog load failure is visible');
  check(await page.locator('.stat-value').allTextContents().then(values => !values.includes('0')), 'failed catalog does not masquerade as zero statistics'); catalogFailure = false;
  await page.getByRole('menuitem', { name: '工作台', exact: true }).click(); await page.waitForURL('**/workbench'); await page.waitForLoadState('networkidle');
  check(await page.locator('html').getAttribute('class') === 'workbench-light', 'SPA navigation keeps unified light theme');
  for (const [route, name] of [['/models', '08-models'], ['/models/perf', '09-model-performance'], ['/datasets', '10-datasets']]) { await go(route); await capture(name); }
  for (const [route, endpoint, retry] of [['/models', '/api/models', '重新加载'], ['/models/perf', '/api/models', '重新加载'], ['/datasets', '/api/datasets', '重新加载'], ['/demo', '/api/demo/models', '重新加载目录'], ['/records', '/api/records', '重试']]) {
    failingPaths.add(endpoint); await go(route);
    check(await page.getByRole('alert').filter({ hasText: '验收模拟：读取失败' }).count() === 1, `${route}: failed loading has an actionable error state`);
    if (route === '/records') check(await page.locator('.record-count').innerText().then(text => text.includes('—')), 'record failure does not claim zero results');
    if (route === '/demo') check(await page.getByRole('button', { name: '开始演示', exact: true }).isDisabled(), 'demo catalog failure blocks submission');
    await capture(`error-${route.replaceAll('/', '-').slice(1)}`);
    failingPaths.delete(endpoint); await page.getByRole('button', { name: retry, exact: true }).click(); await page.waitForLoadState('networkidle');
    check(await page.getByRole('alert').filter({ hasText: '验收模拟：读取失败' }).count() === 0, `${route}: retry recovers without a page reload`);
  }
  raceRecords = true; await go('/records');
  await page.getByRole('combobox', { name: '任务类型', exact: true }).focus(); await page.keyboard.press('Enter');
  await page.getByRole('option', { name: '快速对比', exact: true }).click();
  await page.locator('.records-loading').waitFor();
  await page.getByRole('combobox', { name: '任务类型', exact: true }).focus(); await page.keyboard.press('Enter');
  await page.getByRole('option', { name: '正式评测', exact: true }).click();
  await page.getByText('最新筛选结果', { exact: true }).waitFor();
  check(typeof releaseOldRecord === 'function', 'older record response is deliberately held for race verification');
  releaseOldRecord(); await page.waitForLoadState('networkidle');
  check(await page.getByText('最新筛选结果', { exact: true }).isVisible() && await page.getByText('过期响应', { exact: true }).count() === 0, 'late record response cannot overwrite current filter results');
  raceRecords = false;
  await page.getByRole('button', { name: '重置筛选', exact: true }).click(); await page.waitForLoadState('networkidle');
  check(await page.getByRole('button', { name: '重置筛选', exact: true }).count() === 0 && await page.getByText('最新筛选结果', { exact: true }).count() === 0, 'record filters reset to current scope without stale rows');
  for (const width of [1440, 1280, 768, 390]) {
    await page.setViewportSize({ width, height: 900 });
    for (const route of ['/', '/workbench', '/inspect/steel/segmentation', '/compare/synthetic-compare-no-gt', '/models/import', '/records', '/assistant', '/demo', '/eval/new', '/models', '/models/perf', '/models/scatter', '/datasets']) {
      await go(route); await noOverflow(`${width}px ${route}`);
      if (width === 390 && ['/', '/workbench', '/inspect/steel/segmentation', '/assistant', '/demo'].includes(route)) await capture(`mobile-${route === '/' ? 'home' : route.split('/').at(-1)}`);
    }
    signedIn = false; await go('/login'); await noOverflow(`${width}px login`); if (width === 390) await capture('mobile-login'); signedIn = true;
  }
  await go('/workbench'); await page.getByRole('button', { name: '菜单 / 对照台' }).click();
  check(await page.locator('#app-navigation').isVisible(), 'mobile navigation opens');
  await page.getByRole('menuitem', { name: '缺陷检测', exact: true }).click();
  const solarMenu = page.getByRole('menuitem', { name: /太阳能电池板检测/ });
  await solarMenu.waitFor({ state: 'visible' });
  check(await solarMenu.evaluate(node => node.scrollWidth <= node.clientWidth + 1 && node.querySelector('.nav-badge').getBoundingClientRect().right <= node.getBoundingClientRect().right), 'expanded mobile scene label and status badge fit navigation');
  await page.screenshot({ path: path.join(output, 'mobile-navigation.png') });
  await page.getByRole('menuitem', { name: '结果记录', exact: true }).click(); await page.waitForURL('**/records'); await page.waitForLoadState('networkidle');
  check(await page.locator('#app-navigation').isHidden(), 'mobile navigation closes after route change');
  check(unexpected.length === 0, `all API traffic mocked (${unexpected.join(',')})`);
  check(errors.length === 0, `no browser page errors (${errors.join(',')})`);
  check(apiCalls.filter(x => x.method !== 'GET').every(x => x.key === '/api/demo/tasks'), 'only intentional mocked demo submission; no real mutation');
  const summary = { checks, browser: browser.version(), viewportWidths: [1672, 1440, 1280, 768, 390], apiRequests: apiCalls.length, unexpected, pageErrors: errors, backend: 'fully mocked; no live services', output };
  await fs.writeFile(path.join(output, 'results.json'), JSON.stringify(summary, null, 2));
  console.log(JSON.stringify(summary, null, 2));
} finally { await browser?.close(); await server.close(); }

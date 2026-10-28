// Isolated classification UI acceptance. All API traffic is mocked; no .env or inference.
// node tests/check_classification_frontend.mjs <absolute Playwright package directory> [output directory]
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath, pathToFileURL } from 'node:url';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const requireWeb = createRequire(path.join(root, 'apps/web/package.json'));
const { chromium } = createRequire(path.join(path.resolve(process.argv[2]), 'package.json'))('./');
const { createServer } = await import(pathToFileURL(requireWeb.resolve('vite')));
const vue = (await import(pathToFileURL(requireWeb.resolve('@vitejs/plugin-vue')))).default;
const scratch = await fs.mkdtemp(path.join(os.tmpdir(), 'steel-classification-ui-'));
const output = path.resolve(process.argv[3] || 'docs/report/classification-2026-10-28/frontend');
await fs.mkdir(output, { recursive: true });
const server = await createServer({ root: path.join(root, 'apps/web'), configFile: false, envFile: false, envDir: scratch,
  cacheDir: path.join(scratch, 'cache'), plugins: [vue()], server: { host: '127.0.0.1', port: 5199, strictPort: true, proxy: {} }, logLevel: 'error' });
const classes = ['龟裂','夹杂','斑块','麻点','轧入氧化皮','划痕'].map((display_zh, id) => ({ id, key: `synthetic-${id}`, display_zh }));
const slugs = ['mobilenet_v3_small','resnet18','efficientnet_b0','resnet50','densenet121','convnext_tiny'];
const names = ['MobileNetV3-Small','ResNet18','EfficientNet-B0','ResNet50','DenseNet121','ConvNeXt-Tiny'];
const models = slugs.map((slug, i) => ({ slug, name: names[i], available: i !== 5, status: i === 5 ? 'unavailable' : 'available',
  reason: i === 5 ? '验收模拟：校验未通过' : null, param_count: i ? null : 1524006, classes }));
const catalog = { models, default_model: slugs[0], max_images: 50, max_models: 3, max_image_bytes: 10485760 };
const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScLbtAAAAABJRU5ErkJggg==', 'base64');
const upload = name => ({ name, mimeType: 'image/png', buffer: png });
const svg = '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200"><rect width="200" height="200" fill="#a6b2bc"/><path d="M120 10 L108 76 L119 140 L100 185" stroke="#526578" fill="none" stroke-width="5"/><text x="9" y="195" font-size="10">SYNTHETIC UI SAMPLE</text></svg>';
const scores = [0.75,0.15,0.06,0.02,0.01,0.01];
const makeTask = (id, hasGT = false, status = 'success') => ({ id, type: 'classification', type_label: '钢铁缺陷分类', status,
  has_gt: hasGT, n: 2, error_summary: null, classes,
  models: [0,1].map(i => ({ model_version_id: `version-${i}`, slug: slugs[i], name: names[i], status: status === 'success' ? 'success' : 'queued' })),
  samples: [0,1].map(i => ({ sample_key: `sample-${i}`, filename: `验收模拟_steel_${i}.png`, preview_url: '/api/classification-test/origin.svg', ...(hasGT ? { class_id: i } : {}) })),
  predictions: status !== 'success' ? [] : [0,1].flatMap(i => [0,1].map(j => ({ sample_key: `sample-${i}`, model_version_id: `version-${j}`, model_slug: slugs[j], class_id: 0, key: classes[0].key, display_zh: classes[0].display_zh, score: scores[0], scores, topk: classes.slice(0,3).map((c, k) => ({ class_id: c.id, key: c.key, display_zh: c.display_zh, score: scores[k] })) }))),
  metrics: hasGT && status === 'success' ? { available: true, n: 2, models: [{ model_version_id: 'version-0', accuracy: 0.5, macro_f1: 0.111111, confusion_matrix: classes.map((_, i) => classes.map((_, j) => j === 0 && i < 2 ? 1 : 0)) }] } : { available: false },
  result_download_url: status === 'success' ? `/api/tasks/${id}/file/classification.json` : null });
let browser, checks = 0, catalogFailure = false, submitFailure = false, detailFailure = false, noAvailable = false, lastGT = false, createdPolls = 0;
const calls = [], unexpected = [], errors = [];
const check = (condition, message) => { assert.ok(condition, message); checks++; console.log(`PASS ${message}`); };
try {
  await server.listen(); browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce' });
  await context.route('**/*', async route => {
    const request = route.request(), url = new URL(request.url()), key = url.pathname, method = request.method();
    if (url.hostname !== '127.0.0.1' || url.port !== '5199') return route.abort();
    if (!key.startsWith('/api/')) return route.continue();
    calls.push({ key, method, body: request.postData() });
    const json = data => route.fulfill({ json: data });
    const fail = () => route.fulfill({ status: 503, json: { code: 'TEST_UNAVAILABLE', message: '验收模拟：暂时不可用' } });
    if (key === '/api/auth/me') return json({ id: 'user-1', username: '验收模拟用户', role: 'student' });
    if (key === '/api/classification/models') return catalogFailure ? fail() : json(noAvailable ? { ...catalog, models: models.map(m => ({ ...m, available: false, reason: '验收模拟：缺少本地校验' })) } : catalog);
    if (key === '/api/classification/uploads' && method === 'POST') { lastGT = request.postData().includes('labels_json'); return json({ batch_id: 'synthetic-batch', has_gt: lastGT, sample_count: 2, samples: [] }); }
    if (key === '/api/classification/tasks' && method === 'POST') { if (submitFailure) return fail(); createdPolls = 0; return json(makeTask('created-task',lastGT,'queued')); }
    if (key === '/api/tasks/created-task') return json(makeTask('created-task',lastGT,createdPolls++ ? 'success' : 'queued'));
    if (key === '/api/tasks/no-gt') return detailFailure ? fail() : json(makeTask('no-gt'));
    if (key === '/api/tasks/with-gt') return json(makeTask('with-gt',true));
    if (key === '/api/tasks/waiting') return json(makeTask('waiting',false,'queued'));
    if (key === '/api/tasks/wrong-domain') return json({ id: 'wrong-domain', type: 'compare' });
    if (key.endsWith('/file/classification.json')) return json(makeTask('no-gt'));
    if (key === '/api/classification-test/origin.svg') return route.fulfill({ contentType: 'image/svg+xml', body: svg });
    unexpected.push(`${method} ${key}`); return route.fulfill({ status: 500, json: { message: 'Unmocked endpoint blocked' } });
  });
  const page = await context.newPage(); page.setDefaultTimeout(10000); page.on('pageerror', e => errors.push(e.message));
  const go = async path => { await page.goto(`http://127.0.0.1:5199${path}`); await page.waitForLoadState('networkidle'); };
  const navigate = async path => page.evaluate(async dest => { const {default: router} = await import('/src/router/index.ts'); await router.push(dest); }, path);
  const capture = async name => {
    await page.evaluate(() => { window.scrollTo(0,0); const el = document.createElement('div'); el.id = 'test-note'; el.textContent = '界面验收 · 全部业务数据为模拟 · 非模型测试成绩'; el.style.cssText = 'position:fixed;bottom:0;right:0;background:#173450;color:#fff;padding:6px 12px;font:12px sans-serif;z-index:99999'; document.body.append(el); });
    await page.screenshot({ path: path.join(output,`${name}.png`), fullPage: true }); await page.locator('#test-note').evaluate(el => el.remove());
  };
  await go('/inspect/steel/classification');
  check(await page.getByRole('heading', {name:'钢铁表面缺陷分类',exact:true}).count() === 1, 'classification uses existing steel scene header');
  check(await page.locator('.switch a').count() === 3, 'three steel task tabs remain');
  check(await page.locator('.switch a').filter({hasText:'目标检测'}).innerText().then(t => t.includes('未开放')), 'detection remains unavailable');
  check(await page.getByRole('link',{name:/NEU-20 正式评测/}).count() === 0, 'classification does not link to segmentation evaluation');
  check(await page.getByRole('checkbox',{name:/MobileNetV3-Small/}).isChecked(), 'validated MobileNet is selected by default');
  check(await page.getByRole('checkbox',{name:/ConvNeXt-Tiny/}).isDisabled(), 'unavailable asset cannot be selected');
  check(await page.getByRole('button',{name:'开始分类',exact:true}).isDisabled(), 'empty upload cannot submit');
  await capture('01-classification-empty');
  await page.getByLabel('分类原图',{exact:true}).setInputFiles(Array.from({length:51},(_,i)=>upload(`too_many_${i}.png`)));
  check(await page.getByRole('alert').innerText().then(t=>t.includes('最多 50 张')),'51 image selection is rejected before upload');
  check(await page.locator('.image-list li').count()===0,'over-limit selection leaves image list unchanged');
  await page.getByLabel('分类原图',{exact:true}).setInputFiles(upload('unsupported.gif'));
  check(await page.getByRole('alert').innerText().then(t=>t.includes('有效的 PNG')),'unsupported file type has explicit error');
  await page.getByLabel('分类原图',{exact:true}).setInputFiles([upload('steel_1.png'),upload('steel_2.png')]);
  check(await page.getByRole('button',{name:'开始分类',exact:true}).isEnabled(), 'unlabeled images can submit');
  await page.getByRole('checkbox',{name:'填写真实图级标签',exact:true}).focus(); await page.keyboard.press('Space');
  check(await page.getByRole('button',{name:'开始分类',exact:true}).isDisabled(), 'label mode requires complete labels');
  await page.getByLabel('steel_1.png 真实类别',{exact:true}).selectOption('0');
  check(await page.getByRole('button',{name:'开始分类',exact:true}).isDisabled(), 'partial labels cannot submit');
  await page.getByLabel('steel_2.png 真实类别',{exact:true}).selectOption('1');
  check(await page.getByRole('button',{name:'开始分类',exact:true}).isEnabled(), 'complete labels including class zero enable submission');
  for (const name of ['ResNet18','EfficientNet-B0']) { await page.getByRole('checkbox',{name:new RegExp(name)}).focus(); await page.keyboard.press('Space'); }
  check(await page.getByRole('checkbox',{name:/ResNet50/}).isDisabled(), 'maximum three classification models');
  await capture('02-classification-labelled');
  submitFailure = true; await page.getByRole('button',{name:'开始分类',exact:true}).click(); await page.getByRole('alert').filter({hasText:'暂时不可用'}).waitFor();
  check(calls.filter(x=>x.key==='/api/classification/uploads').length===1,'upload completes once before queue failure');
  check(calls.find(x=>x.key==='/api/classification/uploads').body.includes('[0,1]'),'labels serialized in file order');
  const firstCreate = calls.find(x=>x.key==='/api/classification/tasks');
  check(JSON.parse(firstCreate.body).model_slugs.length===3,'selected models reach task request');
  submitFailure = false; await page.getByRole('button',{name:'开始分类',exact:true}).click();
  await page.waitForURL('**/classification/created-task');
  check(calls.filter(x=>x.key==='/api/classification/uploads').length===1,'task retry reuses uploaded batch');
  await page.getByRole('heading',{name:'本批分类指标',exact:true}).waitFor();
  check(createdPolls>=2,'queued classification automatically polls to completed result');
  check(await page.locator('.sample-result').count()===2,'result displays each original image');
  check(await page.locator('.top-scores').count()===4,'each sample includes both model predictions');
  await page.getByText('查看混淆矩阵',{exact:true}).click();
  check(await page.locator('.confusion-matrix tbody tr').count()===6,'complete GT enables six-class confusion matrix');
  await capture('03-classification-metrics');
  await go('/inspect/steel/classification'); await page.getByLabel('分类原图',{exact:true}).setInputFiles([upload('new_1.png'),upload('new_2.png')]);
  await page.getByRole('button',{name:'开始分类',exact:true}).click(); await page.waitForURL('**/classification/created-task');
  await page.locator('.top-scores').first().waitFor();
  check(!calls.filter(x=>x.key==='/api/classification/uploads').at(-1).body.includes('labels_json'),'no GT upload omits labels entirely');
  check(await page.locator('.metrics-panel').count()===0,'unlabeled submission completes without numeric metric panel');
  await go('/classification/no-gt');
  check(await page.locator('.breadcrumb strong').innerText()==='缺陷检测','classification result breadcrumb belongs to defect inspection');
  check(await page.locator('.el-menu-item.is-active').innerText()==='钢铁检测','classification result keeps existing steel navigation selected');
  check(await page.locator('.el-sub-menu.is-opened > .el-sub-menu__title').innerText().then(t=>t.includes('缺陷检测')),'classification result expands existing defect navigation');
  check(await page.locator('.metrics-panel').count()===0,'no GT result has no numeric accuracy or F1 panel');
  check(await page.locator('.confusion-matrix').count()===0,'no GT result has no confusion matrix');
  check(await page.locator('.metrics-unavailable').innerText().then(t=>t.includes('未提供真实标签')),'unavailable metrics reason explicit');
  check(await page.locator('.cls-notice').innerText().then(t=>t.includes('不是经过校准的正确概率')),'scores are not represented as calibrated correctness probability');
  check(await page.getByText('Mask',{exact:true}).count()===0 && await page.getByText('热力图',{exact:true}).count()===0,'classification has no segmentation visualization controls');
  const download = page.waitForEvent('download'); await page.getByRole('button',{name:'下载分类结果 JSON',exact:true}).click();
  check((await download).suggestedFilename()==='no-gt_classification.json','authorized JSON response can download');
  await capture('04-classification-no-gt');
  detailFailure = true; await go('/classification/no-gt'); await page.getByRole('alert').waitFor();
  check(await page.getByRole('button',{name:'重新加载',exact:true}).isVisible(),'detail failure has explicit retry');
  detailFailure = false; await page.getByRole('button',{name:'重新加载',exact:true}).click(); await page.locator('.sample-result').first().waitFor();
  check(await page.locator('.sample-result').count()===2,'detail retry restores predictions');
  await go('/classification/wrong-domain');
  check(await page.getByRole('alert').innerText().then(t=>t.includes('不是钢铁缺陷分类')),'segmentation task cannot render as classification');
  await go('/classification/waiting'); await navigate('/inspect/steel/classification'); await page.locator('.classification-new').waitFor();
  const beforeLeave = calls.filter(x=>x.key==='/api/tasks/waiting').length; await page.waitForTimeout(3000);
  check(calls.filter(x=>x.key==='/api/tasks/waiting').length===beforeLeave,'leaving result page stops polling');
  catalogFailure = true; await go('/inspect/steel/classification');
  check(await page.getByRole('alert').innerText().then(t=>t.includes('分类模型目录暂不可用')),'catalog failure is distinct from no models');
  catalogFailure = false; await page.getByRole('button',{name:'重新加载目录',exact:true}).click(); await page.locator('.classification-models strong').filter({hasText:'MobileNetV3-Small'}).waitFor();
  check(await page.getByRole('checkbox',{name:/MobileNetV3-Small/}).isChecked(),'catalog retry restores default validated model');
  noAvailable = true; await go('/inspect/steel/classification');
  check(await page.getByRole('button',{name:'开始分类',exact:true}).isDisabled(),'all unavailable weights keep submission closed'); noAvailable = false;
  for(const width of [1440,768,390]) {
    await page.setViewportSize({width,height:1000});
    for(const target of ['/inspect/steel/classification','/classification/no-gt','/classification/with-gt']) {
      await go(target);
      check(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`${target} has no page overflow at ${width}px`);
      if(target.endsWith('/classification')) await page.getByLabel('分类原图',{exact:true}).setInputFiles(upload('验收模拟.png'));
      await capture(`${width}-${target.split('/').filter(Boolean).join('-')}`);
    }
  }
  check(unexpected.length===0,`all classification API endpoints mocked: ${unexpected.join(',')}`);
  check(errors.length===0,`no browser exceptions: ${errors.join(',')}`);
  await fs.writeFile(path.join(output,'results.json'),JSON.stringify({checks,browser:browser.version(),apiRequests:calls.length,unexpected,errors,environment:'All business data mocked; no production API, DB, Redis, Docker, LLM or inference'},null,2));
  console.log(`PASS ${checks} classification browser assertions; ${calls.length} mocked API requests.`);
} finally { if(browser) await browser.close(); await server.close(); }

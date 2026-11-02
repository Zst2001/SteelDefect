// Real isolated HTTP/RQ/CPU; only synthetic ROI and ephemeral cookies on stdin.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import net from 'node:net';
import {createRequire} from 'node:module';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {probePrivateAssets} from './pcb_private_get_probe.mjs';
import {classificationPrivatePaths} from './pcb_classification_private_paths.mjs';
const root=fileURLToPath(new URL('../',import.meta.url));
let input='';for await(const part of process.stdin){input+=part;assert(input.length<4e6);}
const cfg=JSON.parse(input);input='';
const api=new URL(cfg.apiBase),out=path.resolve(cfg.output);
assert(api.hostname==='127.0.0.1'&&!['8000','5173'].includes(api.port));
const req=createRequire(path.join(root,'apps/web/package.json'));
const {createServer}=await import(pathToFileURL(req.resolve('vite')));
const {chromium}=createRequire(path.join(path.resolve(process.argv[2]),'package.json'))('./');
const temp=await fs.mkdtemp(path.join(os.tmpdir(),'steel-roi-browser-'));
let server,browser,context,page,passed=false;
const checks=[],runs=[],errors=[],blocked=[];
const check=(value,label)=>{assert(value,label);checks.push(label);};
const redact=s=>Object.values(cfg.tokens).reduce((t,v)=>t.split(v).join('[redacted]'),String(s));
try {
  const reservation=net.createServer();await new Promise(resolve=>reservation.listen(0,'127.0.0.1',resolve));
  const frontPort=reservation.address().port;await new Promise(resolve=>reservation.close(resolve));
  assert(![8000,5173].includes(frontPort));
  server=await createServer({root:path.join(root,'apps/web'),configFile:path.join(root,'apps/web/vite.config.ts'),
    envFile:false,envDir:temp,cacheDir:path.join(temp,'vite'),logLevel:'warn',server:{host:'127.0.0.1',port:frontPort,strictPort:true,
      proxy:{'/api':{target:api.origin,changeOrigin:true,timeout:0,proxyTimeout:0}}}});
  await server.listen();const origin=`http://127.0.0.1:${server.httpServer.address().port}`;
  browser=await chromium.launch({headless:true});
  context=await browser.newContext({viewport:{width:1440,height:1000},reducedMotion:'reduce'});
  await context.addCookies([{name:'lab_session',value:cfg.tokens.owner,url:origin,httpOnly:true,sameSite:'Lax'}]);
  await context.route('**/*',r=>{const u=new URL(r.request().url());if(u.origin===origin)return r.continue();blocked.push(u.origin+u.pathname);return r.abort();});
  page=await context.newPage();page.setDefaultTimeout(30000);
  page.on('pageerror',e=>errors.push(redact(e.message)));
  const go=async p=>{await page.goto(origin+p,{timeout:60000});await page.waitForLoadState('networkidle');};
  const shot=async name=>{
    await page.evaluate(()=>{const e=document.createElement('div');e.id='evidence-note';e.textContent='隔离真实 API / RQ / CPU · 合成 ROI · 不代表测试精度';e.style='position:fixed;bottom:0;right:0;background:#173450;color:white;padding:8px;font:12px sans-serif;z-index:99999';document.body.append(e);});
    await page.screenshot({path:path.join(out,name+'.png'),fullPage:true});await page.locator('#evidence-note').evaluate(e=>e.remove());
  };
  for(const [i,key] of ['efficientnet_b0','mobilenet_v3_small','mobilenet_v3_small'].entries()){
    await go('/inspect/pcb/classification');
    check(await page.locator('#roi-model').inputValue()==='efficientnet_b0','backend default EfficientNet '+i);
    check(await page.locator('#roi-model option').count()===2,'two admitted models '+i);
    check(await page.locator('.roi-classes>span').count()===6,'six fixed classes '+i);
    await page.getByLabel('PCB 分类 ROI',{exact:true}).setInputFiles({name:i===1?'roi.jpg':'roi.png',mimeType:i===1?'image/jpeg':'image/png',buffer:Buffer.from(i===1?cfg.jpeg:cfg.png,'base64')});
    await page.getByRole('img',{name:'待分类 ROI 预览',exact:true}).waitFor();
    await page.locator('#roi-model').selectOption(key);
    if(i===0)await shot('desktop-upload');
    const created=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/scenes/pcb/classification/tasks'&&r.request().method()==='POST');
    await page.getByRole('button',{name:'开始 PCB 分类',exact:true}).click();
    const response=await created;check(response.ok(),'real submission '+i);const initial=await response.json();
    await page.waitForURL('**/inspect/pcb/classification/tasks/'+initial.id);
    await page.getByRole('button',{name:'下载结果 JSON',exact:true}).waitFor({state:'visible',timeout:150000});
    const detail=await(await context.request.get(origin+'/api/tasks/'+initial.id)).json();
    check(detail.status==='success'&&detail.type==='pcb_classify','CPU task success '+i);
    check(detail.model.id===key&&detail.result.model_id===key,'model identity '+i);
    check(detail.metrics.available===false&&!detail.has_gt,'no metrics '+i);
    check(detail.result.input_adapted===(i===1),'input adaptation '+i);
    check(detail.result.probabilities.every(p=>Number.isFinite(p)&&p>=0&&p<=1),'finite bounded probabilities '+i);
    check(detail.result.probabilities.length===6&&Math.abs(detail.result.probabilities.reduce((a,b)=>a+b,0)-1)<1e-5,'probability simplex '+i);
    check(Number.isInteger(detail.result.class_id)&&detail.result.class_id===detail.result.probabilities.indexOf(Math.max(...detail.result.probabilities)),'prediction is argmax '+i);
    const labels=[['open','断路'],['short','短路'],['mousebite','鼠咬'],['spur','毛刺'],['copper','余铜'],['pin-hole','针孔']];
    check(detail.classes.length===6&&detail.classes.every((c,n)=>c.class_id===n&&c.label_en===labels[n][0]&&c.label_zh===labels[n][1]),'fixed class order and labels '+i);
    check(detail.result.label_en===labels[detail.result.class_id][0]&&detail.result.label_zh===labels[detail.result.class_id][1],'prediction label mapping '+i);
    check(detail.result.confidence===detail.result.probabilities[detail.result.class_id],'confidence index '+i);
    check(await page.locator('meter').count()===6,'six visible probability bars '+i);
    for(let n=0;n<6;n++)check(Math.abs(Number(await page.locator('meter').nth(n).getAttribute('value'))-detail.result.probabilities[n])<1e-8,'UI matches actual probability '+i+'/'+n);
    const im=page.getByRole('img',{name:'模型输入 ROI 灰度预览',exact:true});await im.evaluate(async el=>{await el.decode();});
    check(await im.evaluate(el=>el.naturalWidth===224&&el.naturalHeight===224),'authorized 224 preview '+i);
    const download=page.waitForEvent('download');await page.getByRole('button',{name:'下载结果 JSON',exact:true}).click();
    const d=await download;check(await d.failure()===null,'JSON download '+i);
    const json=JSON.parse(await fs.readFile(await d.path(),'utf8'));check(json.task_id===initial.id,'download belongs to task '+i);
    assert.deepEqual(json,detail.result);check(true,'download exactly matches API result '+i);
    await shot('desktop-result-'+i);
    await page.setViewportSize({width:390,height:844});
    check(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'mobile no horizontal overflow '+i);
    if(i===0)await shot('mobile-result');
    await page.setViewportSize({width:1440,height:1000});
    runs.push({taskId:initial.id,model:key,status:detail.status,adapted:detail.result.input_adapted,cacheHit:detail.result.cache_hit});
  }
  check(runs[2].cacheHit===true,'same Worker subsequent model uses cache');
  await go('/records?type=pcb_classify');
  for(const run of runs)check(await page.locator(`a[href="/inspect/pcb/classification/tasks/${run.taskId}"]`).count()>0,'history links '+run.taskId);
  await page.setViewportSize({width:390,height:844});await go('/inspect/pcb/classification');
  check(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'mobile upload no overflow');
  check(await page.getByRole('button',{name:'开始 PCB 分类',exact:true}).isVisible(),'mobile submit visible');
  await shot('mobile-upload');
  await page.setViewportSize({width:1440,height:1000});await go('/inspect/pcb');
  check(await page.getByRole('heading',{name:'PCB 表面缺陷分割工作台',exact:true}).count()===1,'segmentation sibling preserved');
  const paths=[...classificationPrivatePaths,classificationPrivatePaths[0].toUpperCase()];
  const dev=await probePrivateAssets({origin,root,surface:'classification-vite',output:path.join(out,'private-vite.json'),paths});
  const apiProof=await probePrivateAssets({origin:api.origin,root,surface:'classification-api',output:path.join(out,'private-api.json'),paths});
  check(errors.length===0,'no browser runtime errors');passed=true;
  console.log(`PASS real browser: ${checks.length} assertions, ${runs.length} CPU tasks, ${dev.requests+apiProof.requests} bounded private HTTP denials`);
} finally {
  await fs.writeFile(path.join(out,'browser-results.json'),JSON.stringify({status:passed?'PASS':'FAIL',checks:checks.length,assertions:checks,runs,errors,blockedExternal:blocked},null,2));
  if(browser)await browser.close();if(server)await server.close();
  const resolved=await fs.realpath(temp);assert(path.dirname(resolved)==await fs.realpath(os.tmpdir())&&path.basename(resolved).startsWith('steel-roi-browser-'));
  await fs.rm(resolved,{recursive:true});
}

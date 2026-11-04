// Actual isolated API/RQ/CPU browser acceptance. Ephemeral credentials only arrive via stdin.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {createRequire} from 'node:module';
import {fileURLToPath,pathToFileURL} from 'node:url';
const root=fileURLToPath(new URL('../',import.meta.url));
let input='';for await(const part of process.stdin){input+=part;assert(input.length<64e6);}
const cfg=JSON.parse(input);input='';const api=new URL(cfg.apiBase),out=path.resolve(cfg.output);
assert(api.hostname==='127.0.0.1'&&!['8000','5173'].includes(api.port));
const req=createRequire(path.join(root,'apps/web/package.json'));
const {createServer}=await import(pathToFileURL(req.resolve('vite'))),{chromium}=createRequire(path.join(path.resolve(process.argv[2]),'package.json'))('./');
const temp=await fs.mkdtemp(path.join(os.tmpdir(),'steel-pcb-batch-browser-'));
const checks=[],errors=[],blocked=[],task_ids=[];const check=(ok,label)=>{assert(ok,label);checks.push(label);};
const redact=s=>Object.values(cfg.tokens).reduce((t,v)=>t.split(v).join('[redacted]'),String(s));
let server,browser,page,passed=false,batch_id=null;
try {
 server=await createServer({root:path.join(root,'apps/web'),configFile:path.join(root,'apps/web/vite.config.ts'),envFile:false,envDir:temp,cacheDir:path.join(temp,'vite'),logLevel:'error',server:{host:'127.0.0.1',port:0,proxy:{'/api':{target:api.origin,changeOrigin:true,timeout:0,proxyTimeout:0}}}});await server.listen();const origin='http://127.0.0.1:'+server.httpServer.address().port;
 browser=await chromium.launch({headless:true});const context=await browser.newContext({viewport:{width:1440,height:1100},reducedMotion:'reduce'});
 await context.addCookies([{name:'lab_session',value:cfg.tokens.owner,url:origin,httpOnly:true,sameSite:'Lax'}]);
 await context.route('**/*',r=>{const u=new URL(r.request().url());if(u.origin===origin)return r.continue();blocked.push(u.origin+u.pathname);return r.abort();});
 page=await context.newPage();page.setDefaultTimeout(30000);page.on('pageerror',e=>errors.push(redact(e.message)));
 const go=async p=>{await page.goto(origin+p,{timeout:60000});await page.waitForLoadState('networkidle');};
 const shot=async name=>{
  // Full-page capture does not itself trigger offscreen native lazy images.
  const lazy=page.locator('img[loading="lazy"]');
  for(const img of await lazy.all()){await img.scrollIntoViewIfNeeded();await img.evaluate(async el=>{await el.decode();if(!el.complete||!el.naturalWidth)throw new Error('Lazy preview did not decode');});}
  await page.locator('img').evaluateAll(images=>Promise.all(images.map(img=>img.decode())));
  if(await page.locator('img').count())check(await page.locator('img').evaluateAll(images=>images.every(el=>el.complete&&el.naturalWidth>0)),name+': every current-source preview decodes');
  await page.evaluate(()=>{window.scrollTo(0,0);const e=document.createElement('p');e.id='acceptance-evidence';e.textContent='真实隔离 API / RQ / CPU · 合成图像，不代表实验精度';e.style='background:#203b5c;color:white;padding:8px;font:12px sans-serif;margin:10px';document.body.prepend(e);});
  await page.waitForTimeout(150);await page.screenshot({path:path.join(out,name+'.png'),fullPage:true});await page.locator('#acceptance-evidence').evaluate(e=>e.remove());
 };
 await go('/inspect/pcb');check(await page.locator('.pcb-model input:checked').count()===1,'default one selected model');check(await page.locator('.pcb-model input[value="unet"]').isChecked(),'default U-Net preserved');
 const chooser=page.waitForEvent('filechooser');await page.getByRole('button',{name:'点击此区域选择 PCB 原图',exact:true}).click({position:{x:12,y:12}});const dialog=await chooser;check(dialog.isMultiple(),'full upload region invokes multiple native filechooser');
 await dialog.setFiles(cfg.images.map(row=>({name:row.name,mimeType:'image/png',buffer:Buffer.from(row.base64,'base64')})));
 await page.locator('.pcb-image-row').nth(1).waitFor();check(await page.locator('.pcb-image-row').count()===2,'two actual input images selected');
 check(await page.getByRole('button',{name:'选择原图',exact:true}).count()===0,'old small picker button absent');
 await page.getByRole('button',{name:'全选全部模型',exact:true}).click();check(await page.locator('.pcb-model input:checked').count()===3,'three admitted models selected');
 check((await page.locator('.pcb-task-equation').innerText()).includes('6'),'six independent tasks in summary');
 check(await page.getByRole('heading',{name:'配对 GT 标签（可选）',exact:true}).isVisible(),'GT card visible');check(await page.getByRole('heading',{name:'生成 Grad-CAM 解释图（可选）',exact:true}).isVisible(),'CAM card visible');
 await page.getByLabel('PCB 配对 GT',{exact:true}).setInputFiles({name:cfg.gt.name,mimeType:'image/png',buffer:Buffer.from(cfg.gt.base64,'base64')});
 const gtSelect=page.getByLabel(cfg.images[0].name+' 的 GT',{exact:true});await gtSelect.locator('option').nth(1).waitFor({state:'attached'});if(!(await gtSelect.inputValue()))await gtSelect.selectOption({index:1});
 check(!!(await gtSelect.inputValue()),'GT explicitly paired to native image only');
 await page.getByText('生成 Grad-CAM',{exact:true}).click();check(await page.getByRole('button',{name:'开始批量分割',exact:true}).isDisabled(),'mixed-size CAM requires acknowledgement');await page.getByText('我确认这些图片仅生成分割图层，不生成 CAM',{exact:true}).click();
 await shot('batch-desktop-form');
 const created=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/scenes/pcb/segmentation/tasks/batch'&&r.request().method()==='POST');await page.getByRole('button',{name:'开始批量分割',exact:true}).click();const response=await created;check(response.ok(),'real batch API accepted submission');const submitted=await response.json();batch_id=submitted.batch_id;
 await page.waitForURL('**/inspect/pcb/batches/'+batch_id);await page.getByRole('heading',{name:'全部完成',exact:true}).waitFor({timeout:480000});
 let batch=await(await context.request.get(origin+'/api/scenes/pcb/segmentation/batches/'+batch_id)).json();
 check(batch.counts.total===6&&batch.counts.success===6&&batch.counts.failed===0,'six real CPU children completed');check(batch.samples.length===2,'persistent batch preserves both inputs');
 check(await page.locator('.pcb-reference-card').count()===2&&await page.locator('.pcb-child-card').count()===3,'first source comparison is immediately visible with original and GT columns');
 for(const sample of batch.samples){
  check(sample.tasks.length===3,'three model tasks for '+sample.filename);
  const expected=cfg.images.find(i=>i.name===sample.filename);check(!!expected&&sample.width===expected.width&&sample.height===expected.height,'persisted original dimensions '+sample.filename);
  for(const task of sample.tasks){task_ids.push(task.id);check(task.status==='success'&&task.type==='pcb_segmentation','correct child type/status '+task.id);check(task.metrics.available===sample.has_gt,'GT metric discipline '+task.id);
   if(!sample.input_plan.cam_supported)check(task.cam.status==='not_supported_for_size','unsupported CAM is explicit '+task.id);
   else check(['ok','unavailable','failed'].includes(task.cam.status),'native CAM has explicit outcome '+task.id);
   const downloaded=await context.request.get(origin+'/api/tasks/'+task.id+'/file/pcb.json');check(downloaded.ok(),'authorized JSON download '+task.id);const result=await downloaded.json();check(result.task_id===task.id,'JSON identity '+task.id);check(result.width===sample.width&&result.height===sample.height,'JSON reports original dimensions '+task.id);
  }
 }
 for(const sample of batch.samples){
  await page.getByLabel('选择对比图片',{exact:true}).selectOption(sample.sample_id);await page.getByRole('tab',{name:'叠加拼图',exact:true}).click();
  check(await page.locator('.pcb-child-card').count()===3,'three model columns for current source '+sample.filename);
  const previews=page.locator('.pcb-child-card .pcb-comparison-frame img');check(await previews.count()===3,'three model overlays directly rendered '+sample.filename);
  for(const img of await previews.all()){await img.scrollIntoViewIfNeeded();await img.evaluate(async e=>e.decode());check(await img.evaluate((e,size)=>e.naturalWidth===size.width&&e.naturalHeight===size.height,{width:sample.width,height:sample.height}),'overlay preserves original dimensions '+sample.filename);}
  check(await page.locator('.pcb-metrics-table').count()===(sample.has_gt?1:0),'current source metrics visible only with GT '+sample.filename);
 }
 await shot('batch-desktop-results');
 const download=page.waitForEvent('download');await page.getByRole('button',{name:'下载此图层（原尺寸）',exact:true}).first().click();check((await download).suggestedFilename().endsWith('_overlay.png'),'browser layer download');
 await page.reload();await page.getByRole('heading',{name:'全部完成',exact:true}).waitFor();check(await page.getByLabel('选择对比图片',{exact:true}).locator('option').count()===2,'refresh restores persisted source selector');
 await page.setViewportSize({width:390,height:844});await page.getByLabel('选择对比图片',{exact:true}).selectOption(batch.samples[1].sample_id);check(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'mobile montage fits viewport');await shot('batch-mobile-results');
 const large=batch.samples.find(s=>s.width!==220||s.height!==220);await go('/inspect/pcb/tasks/'+large.tasks[0].id);check(await page.getByText(large.width+' × '+large.height,{exact:false}).count()>0,'single-task detail preserves large dimensions');check(await page.getByRole('link',{name:'返回批次对比',exact:true}).count()===1,'history detail links back to persistent batch');
 await go('/records?type=pcb_segmentation');for(const id of task_ids)check(await page.locator('a[href="/inspect/pcb/tasks/'+id+'"]').count()>0,'history contains child '+id);
 await go('/inspect/pcb');check(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'mobile form fits viewport');await shot('batch-mobile-form');
 check(new Set(task_ids).size===6,'all six children have independent IDs');check(errors.length===0,'no browser runtime errors');check(blocked.every(url=>['fonts.googleapis.com','fonts.gstatic.com'].includes(new URL(url).hostname)),'all external requests blocked; only existing global font requests attempted');passed=true;console.log('PASS real PCB batch browser: '+checks.length+' assertions, six CPU tasks');
} finally {
 await fs.writeFile(path.join(out,'browser-results.json'),JSON.stringify({status:passed?'PASS':'FAIL',checks:checks.length,assertions:checks,batch_id,task_ids,errors,blockedExternal:blocked,blockedFontRequests:blocked.filter(url=>['fonts.googleapis.com','fonts.gstatic.com'].includes(new URL(url).hostname))},null,2));
 if(!passed&&page)await page.screenshot({path:path.join(out,'browser-failure.png'),fullPage:true}).catch(()=>{});
 if(browser)await browser.close();if(server)await server.close();const resolved=await fs.realpath(temp);assert(path.dirname(resolved)===await fs.realpath(os.tmpdir())&&path.basename(resolved).startsWith('steel-pcb-batch-browser-'));await fs.rm(resolved,{recursive:true});
}

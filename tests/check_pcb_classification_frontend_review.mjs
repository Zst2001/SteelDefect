// Synthetic, isolated regression checks. Does not call the API, DB, worker or model.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {createRequire} from 'node:module';
import {fileURLToPath,pathToFileURL} from 'node:url';

const root=fileURLToPath(new URL('../',import.meta.url)), out=path.resolve(process.argv[3]);
await fs.mkdir(out,{recursive:true});assert(!(await fs.readdir(out)).includes('results.json'),'Use a new evidence directory');
const req=createRequire(path.join(root,'apps/web/package.json'));
const {createServer}=await import(pathToFileURL(req.resolve('vite')));
const {chromium}=createRequire(path.join(path.resolve(process.argv[2]),'package.json'))('./');
const temp=await fs.mkdtemp(path.join(os.tmpdir(),'steel-roi-review-'));
const checks=[],errors=[],unexpected=[],submissions=[];
const check=(value,label)=>{assert(value,label);checks.push(label);};
const classes=['open','short','mousebite','spur','copper','pin-hole'].map((label_en,class_id)=>({label_en,class_id,label_zh:['断路','短路','鼠咬','毛刺','余铜','针孔'][class_id]}));
const catalog={enabled:true,available:true,default_model:'efficientnet_b0',max_image_bytes:2097152,classes,models:[
  {model_id:'efficientnet_b0',name:'EfficientNet-B0',params:4015234,available:true,default:true},
  {model_id:'mobilenet_v3_small',name:'MobileNetV3-Small',params:1524006,available:true,default:false}]};
function task(id) {
  return {id,status:'success',type:'pcb_classify',scene:'pcb',task_kind:'classification',protocol_id:'pcb_cls_deeppcb_roi_v0',model:{id:'efficientnet_b0',name:'EfficientNet-B0'},classes,input:{width:224,height:224,input_adapted:false},
    result:{...classes[3],task_id:id,model_id:'efficientnet_b0',protocol_id:'pcb_cls_deeppcb_roi_v0',confidence:.75,probabilities:[.05,.05,.05,.75,.05,.05],input_adapted:false,sample_sha256:'a'.repeat(64)},
    artifacts:[],result_download_url:`/api/tasks/${id}/file/pcb_classification.json`};
}
let server,browser,passed=false,uploads=0,downloadValid=false,repairResult=false,releaseSlow,slowEntered;
const slowReceived=new Promise(resolve=>{slowEntered=resolve;});
try {
  server=await createServer({root:path.join(root,'apps/web'),configFile:path.join(root,'apps/web/vite.config.ts'),envFile:false,envDir:temp,cacheDir:path.join(temp,'vite'),logLevel:'error',server:{host:'127.0.0.1',port:0,proxy:{}}});
  await server.listen();const origin=`http://127.0.0.1:${server.httpServer.address().port}`;
  browser=await chromium.launch({headless:true});const context=await browser.newContext({viewport:{width:1440,height:1000}});
  await context.route('**/*',async route=>{
    const request=route.request(),url=new URL(request.url()),key=url.pathname;
    if(url.origin!==origin)return route.abort();if(!key.startsWith('/api/'))return route.continue();
    const json=data=>route.fulfill({json:data});
    if(key==='/api/auth/me')return json({id:'mock',username:'模拟用户',role:'student'});
    if(key==='/api/scenes/pcb/classification/models')return json(catalog);
    if(key==='/api/scenes/pcb/classification/uploads')return json({batch_id:`batch-${++uploads}`,sample_count:1});
    if(key==='/api/scenes/pcb/classification/tasks'){
      submissions.push({...request.postDataJSON(),key:request.headers()['idempotency-key']});
      return route.fulfill({status:503,json:{code:'SYNTHETIC_UNCERTAIN',message:'验收模拟：提交响应不确定'}});
    }
    if(key.endsWith('/file/pcb_classification.json'))return json(downloadValid?task('valid').result:{...task('valid').result,task_id:'other-task'});
    if(key.startsWith('/api/tasks/')){
      const id=key.slice('/api/tasks/'.length), t=task(id);
      if(id==='slow'){slowEntered();await new Promise(resolve=>{releaseSlow=resolve;});}
      if(id==='wrong-task')t.result.task_id='other-task';
      if(id==='wrong-model')t.result.model_id='mobilenet_v3_small';
      if(id==='wrong-protocol')t.result.protocol_id='other-protocol';
      if(id==='wrong-chinese')t.result.label_zh='短路';
      if(id==='wrong-argmax'){Object.assign(t.result,classes[0]);t.result.confidence=.05;}
      if(id==='malformed-labels')t.classes={length:6};
      if(id==='wrong-envelope')t.id='other-task';
      if(id==='unknown-status')t.status='unexpected';
      if(id==='repair'&&!repairResult)t.result.task_id='other-task';
      if(id==='small-probability'){t.result.probabilities=[.000001,0,0,.999999,0,0];t.result.confidence=.999999;}
      return json(t);
    }
    unexpected.push(key);return route.fulfill({status:404,json:{message:'unexpected mock route'}});
  });
  const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));page.setDefaultTimeout(15000);
  const go=async target=>{await page.goto(origin+target,{timeout:60000});await page.waitForLoadState('networkidle');};
  await go('/inspect/pcb/classification');
  const png=Buffer.from(await page.evaluate(()=>{const c=document.createElement('canvas');c.width=224;c.height=224;c.getContext('2d').fillRect(0,0,224,224);return c.toDataURL('image/png').split(',')[1];}),'base64');
  const choose=()=>page.getByLabel('PCB 分类 ROI',{exact:true}).setInputFiles({name:'roi.png',mimeType:'image/png',buffer:png});
  await choose();await page.getByRole('img',{name:'待分类 ROI 预览'}).waitFor();
  const submit=async()=>{await page.getByRole('button',{name:'开始 PCB 分类',exact:true}).click();await page.getByRole('alert').waitFor();};
  await submit();await page.locator('#roi-model').selectOption('mobilenet_v3_small');await submit();
  await page.locator('#roi-model').selectOption('efficientnet_b0');await submit();
  check(uploads===1,'A-B-A retries reuse one uploaded batch');
  check(submissions.length===3&&!!submissions[0].key&&submissions[0].key===submissions[2].key,'returning to model A reuses its uncertain request key');
  check(submissions[1].key!==submissions[0].key,'different models use distinct request keys');
  await page.getByRole('button',{name:'移除 ROI',exact:true}).click();
  check(await page.getByRole('img',{name:'待分类 ROI 预览'}).count()===0,'remove clears the ROI preview');
  check(await page.getByRole('button',{name:'开始 PCB 分类',exact:true}).isDisabled(),'remove disables submission');
  check(await page.getByRole('alert').count()===0,'remove clears stale submission error');
  await choose();await page.getByRole('img',{name:'待分类 ROI 预览'}).waitFor();await submit();
  check(uploads===2&&submissions.at(-1).batch_id==='batch-2'&&submissions.at(-1).key!==submissions[0].key,'new ROI starts a fresh batch and key');
  for(const id of ['wrong-task','wrong-model','wrong-protocol','wrong-chinese','wrong-argmax','malformed-labels','wrong-envelope','unknown-status']){
    await go('/inspect/pcb/classification/tasks/'+id);await page.getByRole('alert').waitFor();
    check(await page.locator('meter').count()===0,id+' cannot display a plausible but invalid result');
    check(await page.getByRole('button',{name:'下载结果 JSON',exact:true}).count()===0,id+' cannot download a result');
  }
  await go('/inspect/pcb/classification/tasks/repair');repairResult=true;
  await page.getByRole('button',{name:'重新加载结果',exact:true}).click();await page.locator('meter').first().waitFor();
  check(await page.locator('meter').count()===6,'invalid result has a working reload action');
  await go('/inspect/pcb/classification/tasks/valid');
  check(await page.getByRole('navigation',{name:'PCB 任务类型'}).getByRole('link',{name:'缺陷分类',exact:true}).getAttribute('aria-current')==='page','classification tab announces its active result section');
  let downloaded=0;page.on('download',()=>downloaded++);
  await page.getByRole('button',{name:'下载结果 JSON',exact:true}).click();await page.getByRole('alert').waitFor();
  check(downloaded===0&&await page.getByRole('alert').textContent().then(x=>x.includes('未保存文件')),'mismatched JSON is rejected before saving');
  downloadValid=true;const download=page.waitForEvent('download');await page.getByRole('button',{name:'下载结果 JSON',exact:true}).click();
  check((await download).suggestedFilename()==='valid_pcb_classification.json','validated JSON remains downloadable');
  await go('/inspect/pcb/classification/tasks/small-probability');
  check(await page.locator('.roi-probability strong').first().textContent()==='<0.01%','nonzero tiny probability is not displayed as zero');
  check(await page.locator('.roi-confidence strong').textContent()==='>99.99%','near-one confidence is not displayed as certain');
  check(await page.locator('meter').first().getAttribute('aria-valuetext')==='<0.01%','probability meter has readable precision');
  await page.screenshot({path:path.join(out,'result-synthetic.png'),fullPage:true});
  await page.evaluate(()=>document.querySelector('#app').__vue_app__.config.globalProperties.$router.push('/inspect/pcb/classification/tasks/slow'));
  await slowReceived;
  await page.evaluate(()=>document.querySelector('#app').__vue_app__.config.globalProperties.$router.push('/inspect/pcb/classification/tasks/valid'));
  await page.locator('.roi-confidence strong').filter({hasText:'75.00%'}).waitFor();
  const slowResponse=page.waitForResponse(r=>r.url().endsWith('/api/tasks/slow'));releaseSlow();await slowResponse;await page.waitForLoadState('networkidle');
  check((await page.locator('.pcb-head .pcb-code').textContent()).includes('valid')&&await page.locator('.roi-confidence strong').textContent()==='75.00%','late response from prior route cannot replace current task');
  check(errors.length===0,'no JavaScript runtime errors');check(unexpected.length===0,'all API calls remain synthetic');
  passed=true;console.log(`PASS ${checks.length} synthetic PCB frontend review assertions`);
} finally {
  if(releaseSlow)releaseSlow();
  await fs.writeFile(path.join(out,'results.json'),JSON.stringify({status:passed?'PASS':'FAIL',checks:checks.length,assertions:checks,errors,unexpected,scope:'mock API only; no DB, worker, inference or real infrastructure'},null,2));
  if(browser)await browser.close();if(server)await server.close();
  const resolved=await fs.realpath(temp);assert(path.dirname(resolved)===await fs.realpath(os.tmpdir())&&path.basename(resolved).startsWith('steel-roi-review-'));await fs.rm(resolved,{recursive:true});
}

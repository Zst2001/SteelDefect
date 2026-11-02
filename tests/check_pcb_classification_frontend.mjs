// Error/retry/responsive UI tests with explicitly synthetic API fixtures.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import net from 'node:net';
import {createRequire} from 'node:module';
import {fileURLToPath,pathToFileURL} from 'node:url';
const root=fileURLToPath(new URL('../',import.meta.url)),out=path.resolve(process.argv[3]);
await fs.mkdir(out,{recursive:true});assert(!(await fs.readdir(out)).includes('results.json'));
const req=createRequire(path.join(root,'apps/web/package.json'));
const {createServer}=await import(pathToFileURL(req.resolve('vite')));
const {chromium}=createRequire(path.join(path.resolve(process.argv[2]),'package.json'))('./');
const temp=await fs.mkdtemp(path.join(os.tmpdir(),'steel-roi-mock-'));
let server,browser,mode='ready',uploadError=false,submitError=false,downloadError=false,polls=0,passed=false;
const checks=[],calls=[],errors=[],unexpected=[];
const check=(value,label)=>{assert(value,label);checks.push(label);};
const classes=['open','short','mousebite','spur','copper','pin-hole'].map((label_en,class_id)=>({label_en,class_id,label_zh:['断路','短路','鼠咬','毛刺','余铜','针孔'][class_id]}));
const catalog={enabled:true,available:true,default_model:'efficientnet_b0',max_image_bytes:2097152,classes,models:[
  {model_id:'efficientnet_b0',name:'EfficientNet-B0',params:4015234,available:true,default:true},
  {model_id:'mobilenet_v3_small',name:'MobileNetV3-Small',params:1524006,available:true,default:false}]};
const task=(id,status='success')=>({id,status,type:'pcb_classify',scene:'pcb',task_kind:'classification',protocol_id:'pcb_cls_deeppcb_roi_v0',model:{id:'efficientnet_b0',name:'EfficientNet-B0'},classes,input:{width:224,height:224,input_adapted:false},
  result:status==='success'?{task_id:id,model_id:'efficientnet_b0',protocol_id:'pcb_cls_deeppcb_roi_v0',...classes[3],confidence:.75,probabilities:[.05,.05,.05,.75,.05,.05],input_adapted:true,adaptation_notice:'验收模拟：已进行灰度和尺寸转换',sample_sha256:'a'.repeat(64)}:null,
  artifacts:[],result_download_url:status==='success'?`/api/tasks/${id}/file/pcb_classification.json`:null,error_summary:status==='failed'?'PCB_CLS_JOB_TIMEOUT: 验收模拟超时':null});
try {
  const reservation=net.createServer();await new Promise(r=>reservation.listen(0,'127.0.0.1',r));const port=reservation.address().port;await new Promise(r=>reservation.close(r));
  server=await createServer({root:path.join(root,'apps/web'),configFile:path.join(root,'apps/web/vite.config.ts'),envFile:false,envDir:temp,cacheDir:path.join(temp,'vite'),logLevel:'error',server:{host:'127.0.0.1',port,strictPort:true,proxy:{}}});await server.listen();
  const origin=`http://127.0.0.1:${port}`;browser=await chromium.launch({headless:true});const context=await browser.newContext({viewport:{width:1440,height:1000}});
  await context.route('**/*',async route=>{
    const request=route.request(),url=new URL(request.url()),key=url.pathname;
    if(url.origin!==origin)return route.abort();if(!key.startsWith('/api/'))return route.continue();
    calls.push({key,method:request.method(),idempotency:request.headers()['idempotency-key']});
    const json=data=>route.fulfill({json:data}),fail=(status=503)=>route.fulfill({status,json:{code:'SYNTHETIC_ERROR',message:'验收模拟：服务不可用'}});
    if(key==='/api/auth/me')return json({id:'mock',username:'模拟用户',role:'student'});
    if(key==='/api/scenes/pcb/classification/models')return mode==='error'?fail():json(mode==='disabled'?{...catalog,enabled:false}:mode==='missing'?{...catalog,models:catalog.models.map(m=>({...m,available:false}))}:catalog);
    if(key==='/api/scenes/pcb/classification/uploads')return uploadError?fail(400):json({batch_id:'batch',sample_count:1});
    if(key==='/api/scenes/pcb/classification/tasks'){polls=0;return submitError?fail():json({id:'created',status:'queued'});}
    if(key==='/api/tasks/created')return json(task('created',polls++<1?'queued':'success'));
    if(key.endsWith('/file/pcb_classification.json'))return downloadError?fail(403):json(task('created').result);
    if(key==='/api/tasks/failed')return json(task('failed','failed'));
    if(key==='/api/tasks/queued')return json({...task('queued','queued'),error_summary:'QUEUE_UNKNOWN: 入队待核验'});
    if(key==='/api/tasks/running')return json(task('running','running'));
    if(key==='/api/tasks/forbidden')return fail(404);
    if(key==='/api/tasks/wrong')return json({...task('wrong'),type:'classification',scene:'steel'});
    if(key==='/api/tasks/invalid'){const t=task('invalid');t.result.probabilities=[1,1,1,1,1,1];return json(t);}
    unexpected.push(key);return fail(404);
  });
  const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));page.setDefaultTimeout(15000);
  const go=async target=>{await page.goto(origin+target,{timeout:60000});await page.waitForLoadState('networkidle');};
  await go('/inspect/pcb/classification');
  const png=Buffer.from(await page.evaluate(()=>{const c=document.createElement('canvas');c.width=224;c.height=224;c.getContext('2d').fillRect(0,0,224,224);return c.toDataURL('image/png').split(',')[1];}),'base64');
  for(const state of ['disabled','missing','error']){
    mode=state;await go('/inspect/pcb/classification');check(await page.getByRole('button',{name:'开始 PCB 分类',exact:true}).isDisabled(),state+' blocks submit');
    check(await page.locator('.pcb-state').isVisible(),state+' explanation visible');
  }
  mode='ready';await go('/inspect/pcb/classification');check(await page.locator('#roi-model').inputValue()==='efficientnet_b0','default is EfficientNet');
  check(await page.getByRole('button',{name:'开始 PCB 分类',exact:true}).isDisabled(),'empty input disabled');
  for(const [name,buffer] of [['empty.png',Buffer.alloc(0)],['big.png',Buffer.alloc(2097153)],['fake.jpg',png],['bad.png',Buffer.from('bad')]]){
    await page.getByLabel('PCB 分类 ROI',{exact:true}).setInputFiles({name,mimeType:'image/png',buffer});await page.getByRole('alert').waitFor();
    check(await page.getByRole('button',{name:'开始 PCB 分类',exact:true}).isDisabled(),name+' rejected');
  }
  await page.getByLabel('PCB 分类 ROI',{exact:true}).setInputFiles({name:'roi.png',mimeType:'image/png',buffer:png});await page.getByRole('img',{name:'待分类 ROI 预览'}).waitFor();
  uploadError=true;await page.getByRole('button',{name:'开始 PCB 分类',exact:true}).click();await page.getByRole('alert').waitFor();
  check(!calls.some(c=>c.key.endsWith('/classification/tasks')),'bad upload never creates task');
  uploadError=false;submitError=true;await page.getByRole('button',{name:'开始 PCB 分类',exact:true}).click();await page.getByRole('alert').waitFor();
  const before=calls.filter(c=>c.key.endsWith('/classification/uploads')).length,key=calls.filter(c=>c.key.endsWith('/classification/tasks')).at(-1).idempotency;
  submitError=false;await page.getByRole('button',{name:'开始 PCB 分类',exact:true}).click();await page.waitForURL('**/tasks/created');await page.locator('meter').first().waitFor();
  check(calls.filter(c=>c.key.endsWith('/classification/uploads')).length===before,'retry reuses uploaded batch');
  check(!!key&&calls.filter(c=>c.key.endsWith('/classification/tasks')).at(-1).idempotency===key,'retry preserves idempotency');
  check(polls>=2,'real polling transitions queued fixture to success');check(await page.locator('meter').count()===6,'six result bars');
  check(await page.locator('.roi-adapted').isVisible(),'adaptation warning');
  downloadError=true;await page.getByRole('button',{name:'下载结果 JSON',exact:true}).click();await page.getByRole('alert').waitFor();check(await page.getByRole('alert').isVisible(),'revoked JSON download error readable');
  downloadError=false;const pending=page.waitForEvent('download');await page.getByRole('button',{name:'下载结果 JSON',exact:true}).click();check((await pending).suggestedFilename()==='created_pcb_classification.json','JSON successful download');
  for(const id of ['failed','forbidden','wrong','invalid']){await go('/inspect/pcb/classification/tasks/'+id);check(await page.getByRole('alert').count()>0,id+' fails visibly');check(await page.locator('meter').count()===0,id+' never fabricates result');}
  for(const id of ['queued','running']){await go('/inspect/pcb/classification/tasks/'+id);check(await page.getByRole('status').count()>0,id+' status visible');}
  for(const width of [1440,768,390]){await page.setViewportSize({width,height:900});await go('/inspect/pcb/classification');check(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'workbench fits '+width);check(await page.getByRole('button',{name:'开始 PCB 分类',exact:true}).isVisible(),'submit visible '+width);}
  check(errors.length===0,'no JS errors');check(unexpected.length===0,'no unhandled API routes');passed=true;
  console.log(`PASS ${checks.length} synthetic PCB classification UI assertions`);
} finally {
  await fs.writeFile(path.join(out,'results.json'),JSON.stringify({status:passed?'PASS':'FAIL',checks:checks.length,assertions:checks,errors,unexpected,scope:'mock API; not CPU or real infrastructure'},null,2));
  if(browser)await browser.close();if(server)await server.close();const resolved=await fs.realpath(temp);assert(path.dirname(resolved)===await fs.realpath(os.tmpdir())&&path.basename(resolved).startsWith('steel-roi-mock-'));await fs.rm(resolved,{recursive:true});
}

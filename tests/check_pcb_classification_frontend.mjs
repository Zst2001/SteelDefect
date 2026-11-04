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
const failingModels=new Set();let multi=false;
const checks=[],calls=[],errors=[],unexpected=[];
const check=(value,label)=>{assert(value,label);checks.push(label);};
const classes=['open','short','mousebite','spur','copper','pin-hole'].map((label_en,class_id)=>({label_en,class_id,label_zh:['断路','短路','鼠咬','毛刺','余铜','针孔'][class_id]}));
const catalog={enabled:true,available:true,default_model:'efficientnet_b0',max_image_bytes:10485760,max_pixels:16777216,supported_formats:['PNG','JPEG','WEBP','BMP','TIFF','GIF'],classes,models:[
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
    calls.push({key,method:request.method(),idempotency:request.headers()['idempotency-key'],...(key.endsWith('/classification/tasks')&&request.method()==='POST'?{body:request.postDataJSON()}:{} )});
    const json=data=>route.fulfill({json:data}),fail=(status=503)=>route.fulfill({status,json:{code:'SYNTHETIC_ERROR',message:'验收模拟：服务不可用'}});
    if(key==='/api/auth/me')return json({id:'mock',username:'模拟用户',role:'student'});
    if(key==='/api/scenes/pcb/classification/models')return mode==='error'?fail():json(mode==='disabled'?{...catalog,enabled:false}:mode==='missing'?{...catalog,models:catalog.models.map(m=>({...m,available:false}))}:catalog);
    if(key==='/api/scenes/pcb/classification/uploads')return uploadError?fail(400):json({batch_id:'batch',sample_count:1});
    if(key==='/api/scenes/pcb/classification/tasks'){polls=0;const model=request.postDataJSON().model_id;return submitError||failingModels.has(model)?fail():json({id:multi?'created-'+model:'created',status:'queued'});}
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
  const imageBytes=async mime=>Buffer.from(await page.evaluate(mime=>{const c=document.createElement('canvas');c.width=224;c.height=224;c.getContext('2d').fillRect(0,0,224,224);return c.toDataURL(mime).split(',')[1];},mime),'base64');
  const png=await imageBytes('image/png'),jpeg=await imageBytes('image/jpeg'),webp=await imageBytes('image/webp');
  const bmp=Buffer.from('Qk1OAAAAAAAAADYAAAAoAAAAAwAAAAIAAAABABgAAAAAABgAAADEDgAAxA4AAAAAAAAAAAAAoFoooFoooFooAAAAoFoooFoooFooAAAA','base64');
  const largeBmp=Buffer.alloc(54+1024*1024*3,90);bmp.copy(largeBmp,0,0,54);largeBmp.writeUInt32LE(largeBmp.length,2);largeBmp.writeInt32LE(1024,18);largeBmp.writeInt32LE(1024,22);largeBmp.writeUInt32LE(1024*1024*3,34);
  const overPixels=Buffer.from(await page.evaluate(()=>{const c=document.createElement('canvas');c.width=4097;c.height=4096;return c.toDataURL('image/png').split(',')[1];}),'base64');
  const tiff=Buffer.from('SUkqAAgAAAAJAAABBAABAAAAAwAAAAEBBAABAAAAAgAAAAIBAwABAAAACAAAAAMBAwABAAAAAQAAAAYBAwABAAAAAQAAABEBBAABAAAAegAAABYBBAABAAAAAgAAABcBBAABAAAABgAAABwBAwABAAAAAQAAAAAAAABQUFBQUFA=','base64');
  const gif=Buffer.from('R0lGODdhAwACAIEAAFBQUAAAAAAAAAAAACwAAAAAAwACAAAIBgABCBwYEAA7','base64');
  const submitButton=()=>page.getByRole('button',{name:'开始 PCB 分类',exact:true});
  const choose=async(name='roi.png',buffer=png,mimeType='image/png')=>{await page.getByLabel('PCB 分类 ROI',{exact:true}).setInputFiles({name,mimeType,buffer});await page.getByText('正在检查图片…',{exact:true}).waitFor({state:'hidden'});};
  const pickDrop=async files=>{await page.locator('.roi-dropzone').evaluate((el,rows)=>{const dt=new DataTransfer();for(const row of rows)dt.items.add(new File([Uint8Array.from(row.bytes)],row.name,{type:row.mime}));el.dispatchEvent(new DragEvent('drop',{bubbles:true,cancelable:true,dataTransfer:dt}));},files.map(f=>({name:f.name,bytes:[...f.buffer],mime:f.mimeType||'image/png'})));};
  const shot=async name=>{await page.evaluate(()=>window.scrollTo(0,0));await page.waitForFunction(()=>window.scrollY===0);await page.evaluate(()=>{const e=document.createElement('div');e.id='mock-note';e.textContent='隔离界面验收 · 图像和结果为合成数据';e.style='position:fixed;bottom:0;right:0;background:#173450;color:white;padding:6px 10px;font:12px sans-serif;z-index:99999';document.body.append(e);});await page.screenshot({path:path.join(out,name+'.png'),fullPage:true});await page.locator('#mock-note').evaluate(e=>e.remove());};
  for(const state of ['disabled','missing','error']){
    mode=state;await go('/inspect/pcb/classification');check(await page.getByRole('button',{name:'开始 PCB 分类',exact:true}).isDisabled(),state+' blocks submit');
    check(await page.locator('.pcb-state').isVisible(),state+' explanation visible');
    check(await page.locator('.roi-dropzone').isDisabled(),state+' blocks upload picker');
  }
  mode='ready';await go('/inspect/pcb/classification');check(await page.locator('.roi-model-card input[value="efficientnet_b0"]').isChecked(),'default is EfficientNet');
  check(await page.locator('.roi-model-card').count()===2&&await page.locator('select').count()===0,'both models are visible cards without dropdown');
  check(await page.getByRole('button',{name:'选择 ROI',exact:true}).count()===0,'redundant choose ROI button removed');
  check(!await page.locator('.roi-model-card input[value="mobilenet_v3_small"]').isChecked(),'lightweight model initially unchecked');
  await page.getByRole('button',{name:'全选全部模型',exact:true}).click();check(await page.locator('.roi-model-card input:checked').count()===2,'select all models');
  await page.getByRole('button',{name:'取消全选',exact:true}).click();check(await page.locator('.roi-model-card input:checked').count()===0&&await submitButton().isDisabled(),'cancel all leaves no model and blocks submit');
  await page.locator('.roi-model-card input[value="efficientnet_b0"]').check();
  for(const position of [{x:10,y:10},null]){const picker=page.waitForEvent('filechooser');await page.locator('.roi-dropzone').click(position?{position}:{});check(!(await picker).isMultiple(),'whole upload area opens single file chooser '+JSON.stringify(position));}
  for(const key of ['Enter','Space']){await page.locator('.roi-dropzone').focus();const picker=page.waitForEvent('filechooser');await page.keyboard.press(key);await picker;check(true,'upload picker supports keyboard '+key);}
  await shot('desktop-empty');
  check(await page.getByRole('button',{name:'开始 PCB 分类',exact:true}).isDisabled(),'empty input disabled');
  for(const [name,buffer] of [['empty.png',Buffer.alloc(0)],['big.png',Buffer.alloc(10485761)],['over-pixels.png',overPixels],['bad.png',Buffer.from('bad')],['broken.png',png.subarray(0,16)],['vector.svg',Buffer.from('<svg></svg>')]]){
    await page.getByLabel('PCB 分类 ROI',{exact:true}).setInputFiles({name,mimeType:'image/png',buffer});await page.getByRole('alert').waitFor();
    check(await page.getByRole('button',{name:'开始 PCB 分类',exact:true}).isDisabled(),name+' rejected');
  }
  for(const [name,buffer,mime] of [['renamed.jpg',png,'image/jpeg'],['no-extension',png,'application/octet-stream'],['roi.jpg',jpeg,'image/jpeg'],['roi.webp',webp,'image/webp'],['roi.bmp',bmp,'image/bmp'],['large-valid.bmp',largeBmp,'image/bmp'],['roi.gif',gif,'image/gif']]){
    await choose(name,buffer,mime);await page.getByRole('img',{name:'待分类 ROI 预览'}).waitFor();check(await submitButton().isEnabled(),'content-based image accepted '+name);
  }
  await choose('roi.tiff',tiff,'image/tiff');await page.getByRole('img',{name:'待分类 ROI 预览'}).waitFor({state:'hidden'});await page.waitForFunction(()=>!document.querySelector('button.roi-submit')?.disabled);
  check(await submitButton().isEnabled(),'TIFF allowed pending authoritative server validation');check(await page.locator('body').textContent().then(t=>t.includes('TIFF')),'TIFF fallback explains preview compatibility');
  await pickDrop([{name:'drop.png',buffer:png}]);await page.getByRole('img',{name:'待分类 ROI 预览'}).waitFor();check(await page.locator('.roi-filename').textContent().then(t=>t.includes('drop.png')),'drop selects image');
  await pickDrop([{name:'a.png',buffer:png},{name:'b.png',buffer:png}]);await page.getByRole('alert').first().waitFor();check(await page.getByRole('alert').first().textContent().then(t=>/一张|单张/.test(t)),'multiple dropped images explicitly rejected');
  await choose();await page.getByRole('img',{name:'待分类 ROI 预览'}).waitFor();await choose();check(await submitButton().isEnabled(),'same file can be selected again');
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
  multi=true;await go('/inspect/pcb/classification');await choose();await page.getByRole('img',{name:'待分类 ROI 预览'}).waitFor();await page.getByRole('button',{name:'全选全部模型',exact:true}).click();
  failingModels.add('mobilenet_v3_small');const firstMulti=calls.length;await submitButton().click();await page.getByRole('alert').first().waitFor();
  let sent=calls.slice(firstMulti).filter(c=>c.key.endsWith('/classification/tasks'));
  check(sent.length===2&&sent[0].body.model_id==='efficientnet_b0'&&sent[1].body.model_id==='mobilenet_v3_small','both selected models actually submit independent tasks');
  check(sent[0].body.batch_id===sent[1].body.batch_id&&sent[0].idempotency!==sent[1].idempotency,'multi-model tasks share uploaded image but use distinct request keys');
  check(page.url().endsWith('/inspect/pcb/classification'),'multi-model submission stays with all task links');
  check(await page.locator('a[href="/inspect/pcb/classification/tasks/created-efficientnet_b0"]').count()===1,'partial success retains first model result link');
  const partialKey=sent[1].idempotency,uploadCount=calls.filter(c=>c.key.endsWith('/classification/uploads')).length,beforeRetry=calls.length;
  failingModels.clear();await submitButton().click();await page.locator('a[href="/inspect/pcb/classification/tasks/created-mobilenet_v3_small"]').waitFor();
  sent=calls.slice(beforeRetry).filter(c=>c.key.endsWith('/classification/tasks'));
  check(sent.length===1&&sent[0].body.model_id==='mobilenet_v3_small'&&sent[0].idempotency===partialKey,'partial retry resubmits only unresolved model with same key');
  check(calls.filter(c=>c.key.endsWith('/classification/uploads')).length===uploadCount,'partial retry does not upload image again');
  check(await submitButton().isDisabled(),'all confirmed submissions cannot be duplicated');
  check(await page.locator('.roi-submission-results a').count()===2,'both completed submissions provide result links');
  await shot('desktop-two-models');
  await page.getByRole('button',{name:'取消全选',exact:true}).click();await page.getByRole('button',{name:'全选全部模型',exact:true}).click();check(await submitButton().isDisabled(),'deselect-reselect keeps completed request identities');
  for(const width of [1440,768,390]){await page.setViewportSize({width,height:900});await go('/inspect/pcb/classification');check(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'workbench fits '+width);check(await page.getByRole('button',{name:'开始 PCB 分类',exact:true}).isVisible(),'submit visible '+width);}
  await choose();await page.getByRole('img',{name:'待分类 ROI 预览'}).waitFor();await page.getByRole('button',{name:'全选全部模型',exact:true}).click();await shot('mobile-upload');
  check(errors.length===0,'no JS errors');check(unexpected.length===0,'no unhandled API routes');passed=true;
  console.log(`PASS ${checks.length} synthetic PCB classification UI assertions`);
} finally {
  await fs.writeFile(path.join(out,'results.json'),JSON.stringify({status:passed?'PASS':'FAIL',checks:checks.length,assertions:checks,errors,unexpected,scope:'mock API; not CPU or real infrastructure'},null,2));
  if(browser)await browser.close();if(server)await server.close();const resolved=await fs.realpath(temp);assert(path.dirname(resolved)===await fs.realpath(os.tmpdir())&&path.basename(resolved).startsWith('steel-roi-mock-'));await fs.rm(resolved,{recursive:true});
}

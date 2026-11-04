// Legacy single-task detail/history compatibility acceptance. Batch upload/selection now lives in check_pcb_batch_frontend.mjs.
// Synthetic images and mocked API only; no model or production service.
// node tests/check_pcb_frontend.mjs <absolute Playwright package directory> [output directory]
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import zlib from 'node:zlib';
import { createRequire } from 'node:module';
import { fileURLToPath, pathToFileURL } from 'node:url';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const requireWeb = createRequire(path.join(root, 'apps/web/package.json'));
const { chromium } = createRequire(path.join(path.resolve(process.argv[2]), 'package.json'))('./');
const { createServer } = await import(pathToFileURL(requireWeb.resolve('vite')));
const vue = (await import(pathToFileURL(requireWeb.resolve('@vitejs/plugin-vue')))).default;
const scratch = await fs.mkdtemp(path.join(os.tmpdir(), 'steel-pcb-ui-'));
const output = path.resolve(process.argv[3] || 'docs/report/pcb-stage4-closeout-20261030/frontend');
await fs.mkdir(output, { recursive: true });
const server = await createServer({ root:path.join(root,'apps/web'), configFile:false, envFile:false, envDir:scratch,
  cacheDir:path.join(scratch,'cache'), plugins:[vue()], server:{host:'127.0.0.1',port:0,proxy:{}},logLevel:'error' });
function png(width=220,height=220,gray=false,foreground=1) {
  const crc = data => { let c=0xffffffff; for(const b of data) { c^=b; for(let i=0;i<8;i++) c=(c>>>1)^((c&1)?0xedb88320:0); } return (c^0xffffffff)>>>0; };
  const chunk = (type,data) => { const body=Buffer.concat([Buffer.from(type),data]), length=Buffer.alloc(4),check=Buffer.alloc(4); length.writeUInt32BE(data.length);check.writeUInt32BE(crc(body));return Buffer.concat([length,body,check]); };
  const header=Buffer.alloc(13);header.writeUInt32BE(width);header.writeUInt32BE(height,4);header[8]=8;header[9]=gray?0:2;
  const channels=gray?1:3, pixels=Buffer.alloc(height*(1+width*channels));
  for(let y=0;y<height;y++) for(let x=0;x<width;x++) { const i=y*(1+width*channels)+1+x*channels; const track=x%45<5||y%50<4;
    if(gray) pixels[i]=(x>95&&x<120&&y>70&&y<145)?foreground:0;
    else { pixels[i]=track?168:25; pixels[i+1]=track?167:76; pixels[i+2]=track?94:63; }
  }
  return Buffer.concat([Buffer.from([137,80,78,71,13,10,26,10]),chunk('IHDR',header),chunk('IDAT',zlib.deflateSync(pixels)),chunk('IEND',Buffer.alloc(0))]);
}
const upload=(name='synthetic-pcb.png',width=220,height=220,gray=false)=>({name,mimeType:'image/png',buffer:png(width,height,gray)});
const models=['unet','unet_resnet18','unetpp_resnet18'].map((slug,i)=>({slug,name:['U-Net','ResNet18-U-Net','ResNet18-U-Net++'][i],available:true,param_count:[7849634,14413570,16111106][i]}));
const catalog={enabled:true,available:true,models,default_model:'unet',max_image_bytes:2097152,input:{width:220,height:220,mode:'RGB',formats:['PNG','JPEG']}};
function makeTask(id,{gt=false,status='success',cam='not_requested',model='unet',emptyMetric=false,legacy=false}={}) {
  const kinds=status==='success'?['origin','pred_mask',...(!legacy?['mask_visual']:[]),'overlay','boundary','probability',...(cam==='ok'?['cam']:[]),...(gt?['gt','error']:[])]:[];
  return {id,type:'pcb_segmentation',scene:'pcb',task_kind:'segmentation',status,has_gt:gt,include_cam:cam!=='not_requested',
    model:{id:model,name:models.find(m=>m.slug===model).name,weight_sha256:'a'.repeat(64),protocol_hash:'b'.repeat(64)},samples:[{sample_key:'image',filename:'synthetic-pcb.png',sha256:'c'.repeat(64)}],
    artifacts:kinds.map(kind=>({kind,url:`/api/tasks/${id}/file/${kind}/${model}/image.png`,rel_path:`${kind}/${model}/image.png`,sample_key:'image'})),
    metrics:gt&&status==='success'?{available:true,defect_dice:emptyMetric?null:.8,iou:.6667,precision:.75,recall:.85,tp:12,fp:4,fn:2,tn:48382}:{available:false},
    cam:{status:cam,layer:cam==='not_requested'?null:'dec1',reason:cam==='unavailable'?'预测前景为空':cam==='failed'?'验收模拟：解释计算失败':null},
    error_summary:status==='failed'?'验收模拟：输入完整性校验失败':null,result_download_url:status==='success'?`/api/tasks/${id}/file/pcb.json`:null};
}
let browser, releaseCatalog, checks=0, mode='ready', uploadFailure=false, submitFailure=false, detailFailure=false, denyDownload=false, lastGT=false, polls=0, lastModel='unet',lastCam=false;
const calls=[], unexpected=[], errors=[];
const check=(condition,message)=>{ assert.ok(condition,message);checks++;console.log(`PASS ${message}`); };
try {
  await server.listen();const origin='http://127.0.0.1:'+server.httpServer.address().port;browser=await chromium.launch({headless:true});
  const context=await browser.newContext({viewport:{width:1440,height:1000},reducedMotion:'reduce'});
  await context.route('**/*',async route=>{
    const request=route.request(),url=new URL(request.url()),key=url.pathname,method=request.method();
    if(url.origin!==origin)return route.abort();
    if(!key.startsWith('/api/'))return route.continue();
    calls.push({key,method,body:request.postData(),idempotency:request.headers()['idempotency-key']});
    const json=data=>route.fulfill({json:data});
    const fail=(status=503,message='验收模拟：服务暂不可用')=>route.fulfill({status,json:{code:'TEST_ERROR',message}});
    if(key==='/api/auth/me')return json({id:'mock-user',username:'验收模拟用户',role:'student'});
    if(key==='/api/scenes/pcb/segmentation/models') {if(mode==='loading')await new Promise(resolve=>{releaseCatalog=resolve;});return mode==='error'?fail():json(mode==='disabled'?{...catalog,enabled:false}:mode==='missing'?{...catalog,models:models.map((m,i)=>({...m,available:i!==2}))}:catalog);}
    if(key==='/api/scenes/pcb/segmentation/uploads') { if(uploadFailure)return fail(422,'验收模拟：GT 包含非法像素值');lastGT=request.postData().includes('name="gt"');return json({batch_id:`batch-${calls.filter(c=>c.key===key).length}`,has_gt:lastGT,sample_count:1}); }
    if(key==='/api/scenes/pcb/segmentation/tasks') { if(submitFailure)return fail();const data=request.postDataJSON();lastModel=data.model_id;lastCam=data.include_cam;polls=0;return json({id:'created',status:'queued'}); }
    if(key.startsWith('/api/tasks/')&&key.includes('/file/')) { if(denyDownload)return fail(403,'验收模拟：任务下载权限已变更');if(key.endsWith('/pcb.json'))return json({scene:'pcb',synthetic:true});const kind=key.split('/file/')[1].split('/')[0];return route.fulfill({contentType:'image/png',body:png(220,220,['pred_mask','mask_visual','gt'].includes(kind),key.includes('/empty-mask/')?0:kind==='mask_visual'?255:1)}); }
    if(key==='/api/tasks/created')return json(makeTask('created',{gt:lastGT,status:polls++<1?'queued':'success',model:lastModel,cam:lastCam?'ok':'not_requested'}));
    if(key==='/api/tasks/no-gt')return detailFailure?fail():json(makeTask('no-gt'));
    if(key==='/api/tasks/with-gt')return json(makeTask('with-gt',{gt:true,cam:'ok',emptyMetric:true}));
    if(key==='/api/tasks/legacy')return json(makeTask('legacy',{legacy:true}));
    if(key==='/api/tasks/empty-mask')return json(makeTask('empty-mask'));
    if(key==='/api/tasks/queued')return json(makeTask('queued',{status:'queued'}));
    if(key==='/api/tasks/timeout')return json({...makeTask('timeout',{status:'failed'}),error_summary:'验收模拟：任务执行超时，请新建任务'});
    if(key==='/api/tasks/forbidden')return fail(403,'验收模拟：无权查看该任务');
    if(key==='/api/tasks/no-cam')return json(makeTask('no-cam',{cam:'unavailable'}));
    if(key==='/api/tasks/cam-failed')return json(makeTask('cam-failed',{cam:'failed'}));
    if(key==='/api/tasks/failed')return json(makeTask('failed',{status:'failed'}));
    if(key==='/api/tasks/waiting')return json(makeTask('waiting',{status:'running'}));
    if(key==='/api/tasks/wrong-scene')return json({...makeTask('wrong-scene'),scene:'steel'});
    if(key==='/api/records')return json({items:[{...makeTask('no-gt'),type_label:'PCB 表面分割',open_path:'/inspect/pcb/tasks/no-gt',bundle_ready:false,note:'',created_at:'2026-10-29T10:00:00',can_submit:false,can_rerun:false,can_note:true,can_archive:true}],total:1});
    unexpected.push(`${method} ${key}`);return fail(500,'Unmocked request blocked');
  });
  const page=await context.newPage();page.setDefaultTimeout(10000);page.on('pageerror',err=>errors.push(err.message));
  const go=async target=>{await page.goto(`${origin}${target}`,{timeout:45000});await page.waitForLoadState('networkidle');};
  const navigate=async target=>page.evaluate(async dest=>{const{default:router}=await import('/src/router/index.ts');await router.push(dest);},target);
  const capture=async name=>{await page.evaluate(()=>{window.scrollTo(0,0);const el=document.createElement('div');el.id='test-note';el.textContent='界面验收 · 合成图像与模拟 API · 非模型测试成绩';el.style.cssText='position:fixed;bottom:0;right:0;background:#173450;color:#fff;padding:6px 12px;font:12px sans-serif;z-index:99999';document.body.append(el);});await page.screenshot({path:path.join(output,`${name}.png`),fullPage:true});await page.locator('#test-note').evaluate(el=>el.remove());};
  const noCancel=async label=>{check(await page.getByRole('button',{name:/取消任务|中止任务|终止任务|停止任务|cancel task/i}).count()===0,`no unsupported cancel button: ${label}`);check(await page.getByRole('link',{name:/取消任务|中止任务|终止任务|停止任务|cancel task/i}).count()===0,`no unsupported cancel link: ${label}`);check(await page.locator('.task-status').filter({hasText:/已取消|取消中|canceled|canceling|cancelled|cancelling/i}).count()===0,`no fabricated cancel status: ${label}`);};
  const maskDownload=async(id,kind)=>{const event=page.waitForEvent('download');await page.getByRole('button',{name:'下载当前图层',exact:true}).click();const download=await event;check(download.suggestedFilename()===`${id}_${kind}.png`,`${id} ${kind} filename matches mask semantics`);const bytes=await fs.readFile(await download.path());check(bytes.subarray(0,8).equals(Buffer.from([137,80,78,71,13,10,26,10])),`${id} ${kind} download is PNG`);await fs.writeFile(path.join(output,download.suggestedFilename()),bytes);return page.evaluate(async data=>{const image=new Image();image.src=`data:image/png;base64,${data}`;await image.decode();const canvas=document.createElement('canvas');canvas.width=image.naturalWidth;canvas.height=image.naturalHeight;const ctx=canvas.getContext('2d');ctx.drawImage(image,0,0);const rgba=ctx.getImageData(0,0,canvas.width,canvas.height).data;return {width:canvas.width,height:canvas.height,pixels:Array.from({length:rgba.length/4},(_,i)=>rgba[i*4])};},bytes.toString('base64'));};
  lastGT=true;lastCam=true;lastModel='unetpp_resnet18';polls=0;
  await go('/inspect/pcb/tasks/created');await page.locator('.pcb-metrics').waitFor();
  check(polls>=2,'legacy queued task polls to successful result');
  check(await page.locator('.el-menu-item.is-active').innerText()==='PCB板检测','result keeps PCB navigation active');
  await page.getByRole('button',{name:'缺陷概率',exact:true}).click();check(await page.locator('.pcb-probability-scale').isVisible(),'probability has distinct scale');
  await page.getByRole('button',{name:'Grad-CAM',exact:true}).click();check((await page.locator('.layer-description').innerText()).includes('不表示缺陷概率'),'CAM distinguished from probability');
  await page.getByRole('button',{name:'放大查看',exact:true}).click();check(await page.getByRole('dialog').isVisible(),'layer can be enlarged');await page.keyboard.press('Escape');
  const layerDownload=page.waitForEvent('download');await page.getByRole('button',{name:'下载当前图层',exact:true}).click();check((await layerDownload).suggestedFilename()==='created_cam.png','authorized layer download');
  await capture('02-result-with-gt');
  await go('/inspect/pcb/tasks/no-gt');
  check(await page.locator('.pcb-metrics').count()===0,'no GT has no numeric metrics');
  check((await page.locator('.pcb-no-metrics').innerText()).includes('无法计算真实性能指标'),'no GT reason explicit');
  check(await page.getByRole('button',{name:'配对 GT',exact:true}).count()===0,'no GT has no GT/error layer');
  check(await page.getByRole('button',{name:'Grad-CAM',exact:true}).isDisabled(),'unrequested CAM cannot select');
  const jsonDownload=page.waitForEvent('download');await page.getByRole('button',{name:'下载结果 JSON',exact:true}).click();check((await jsonDownload).suggestedFilename()==='no-gt_pcb.json','authorized JSON download');
  await page.getByRole('button',{name:'原始二值掩码（0/1）',exact:true}).click();check(await page.locator('.pcb-result-frame .pcb-mask').count()===1,'0/1 mask preview is enhanced without changing download');
  check(await page.getByRole('img',{name:'PCB 原始二值掩码（0/1）',exact:true}).count()===1,'raw mask image has exact 0/1 identity');
  const raw=await maskDownload('no-gt','pred_mask');check(raw.width===220&&raw.height===220,'raw mask preserves 220 x 220 geometry');check([...new Set(raw.pixels)].sort().join(',')==='0,1','raw mask download contains only 0/1 with nonempty foreground');
  await page.getByRole('button',{name:'可视化掩码（0/255）',exact:true}).click();const visualImage=page.getByRole('img',{name:'PCB 可视化掩码（0/255）',exact:true});await visualImage.waitFor();check(await visualImage.evaluate(el=>getComputedStyle(el).filter==='none'),'visual mask displays directly without CSS brightness');check((await page.locator('.layer-description').innerText()).includes('不用于指标计算'),'visual mask explicitly excluded from metric calculation');
  const visual=await maskDownload('no-gt','mask_visual');check(visual.width===220&&visual.height===220,'visual mask preserves 220 x 220 geometry');check([...new Set(visual.pixels)].sort((a,b)=>a-b).join(',')==='0,255','visual mask download contains only 0/255 with visible foreground');check(raw.pixels.every((value,i)=>(value>0)===(visual.pixels[i]>0)),'raw and visual mask foreground positions match pixel for pixel');
  await page.getByRole('button',{name:'放大查看',exact:true}).click();check(await page.getByRole('img',{name:'可视化掩码（0/255） 放大查看',exact:true}).evaluate(el=>getComputedStyle(el).filter==='none'),'enlarged visual mask also avoids brightness transform');await page.keyboard.press('Escape');await capture('03-directly-visible-mask');
  denyDownload=true;await page.getByRole('button',{name:'下载当前图层',exact:true}).click();await page.getByRole('alert').filter({hasText:'下载权限已变更'}).waitFor();check(await page.getByRole('alert').filter({hasText:'下载权限已变更'}).isVisible(),'revoked download permission is visible rather than silent success');denyDownload=false;
  await go('/inspect/pcb/tasks/legacy');check(await page.getByRole('button',{name:'可视化掩码（0/255）',exact:true}).isDisabled(),'legacy task cannot offer nonexistent 0/255 mask');check((await page.locator('.pcb-mask-legacy').innerText()).includes('下载仍保留原始 0/1'),'legacy fallback explains original download values');await page.getByRole('button',{name:'原始二值掩码（0/1）',exact:true}).click();check(await page.getByRole('img',{name:'PCB 原始二值掩码（0/1）',exact:true}).evaluate(el=>getComputedStyle(el).filter==='brightness(255)'),'legacy raw mask CSS preview remains visible');const legacy=await maskDownload('legacy','pred_mask');check([...new Set(legacy.pixels)].sort().join(',')==='0,1','legacy download remains original 0/1 rather than pretending to be visual');await capture('04-legacy-mask');
  await go('/inspect/pcb/tasks/empty-mask');await page.getByRole('button',{name:'原始二值掩码（0/1）',exact:true}).click();const emptyRaw=await maskDownload('empty-mask','pred_mask');await page.getByRole('button',{name:'可视化掩码（0/255）',exact:true}).click();const emptyVisual=await maskDownload('empty-mask','mask_visual');check(emptyRaw.pixels.every(x=>x===0)&&emptyVisual.pixels.every(x=>x===0),'empty foreground produces two all-background masks');
  await go('/inspect/pcb/tasks/with-gt');check((await page.locator('.pcb-metric-grid dd').first().innerText())==='—','undefined metric is not coerced to zero');
  await go('/inspect/pcb/tasks/no-cam');check((await page.locator('.pcb-cam-state').innerText()).includes('预测前景为空'),'empty foreground has explicit CAM unavailable state');
  await go('/inspect/pcb/tasks/cam-failed');check((await page.locator('.pcb-cam-state').innerText()).includes('基础分割结果仍然有效'),'CAM failure preserves completed segmentation');
  await go('/inspect/pcb/tasks/failed');check((await page.getByRole('alert').innerText()).includes('输入完整性校验失败'),'task failure has actionable reason');
  await go('/inspect/pcb/tasks/timeout');check((await page.getByRole('alert').innerText()).includes('任务执行超时'),'timeout remains truthful failed task with explicit reason');
  await go('/inspect/pcb/tasks/forbidden');check((await page.getByRole('alert').innerText()).includes('无权查看该任务'),'revoked view permission has explicit feedback');
  await go('/inspect/pcb/tasks/wrong-scene');check((await page.getByRole('alert').innerText()).includes('不是 PCB 分割任务'),'cross scene task is refused');
  detailFailure=true;await go('/inspect/pcb/tasks/no-gt');check(await page.getByRole('button',{name:'重新加载',exact:true}).isVisible(),'detail error provides retry');detailFailure=false;await page.getByRole('button',{name:'重新加载',exact:true}).click();await page.locator('.pcb-result-panel').waitFor();
  await go('/inspect/pcb/tasks/waiting');await navigate('/inspect/pcb');await page.locator('.pcb-new').waitFor();const count=calls.filter(c=>c.key==='/api/tasks/waiting').length;await page.waitForTimeout(2800);check(calls.filter(c=>c.key==='/api/tasks/waiting').length===count,'leaving detail stops polling');
  await go('/records?type=pcb_segmentation');check(calls.filter(c=>c.key==='/api/records').length>0,'PCB history uses existing records');check(await page.getByText('PCB 表面分割',{exact:true}).count()>0,'PCB history has explicit task label');await page.getByRole('link',{name:'查看',exact:true}).click();await page.waitForURL('**/inspect/pcb/tasks/no-gt');
  for(const width of [1440,768,390]) {await page.setViewportSize({width,height:1000});for(const target of ['/inspect/pcb/tasks/no-gt','/inspect/pcb/tasks/with-gt','/inspect/pcb/tasks/legacy','/inspect/pcb/tasks/queued','/inspect/pcb/tasks/waiting','/records?type=pcb_segmentation']) {await go(target);check(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`no overflow ${width}px ${target}`);if(target.startsWith('/inspect/pcb'))check((await page.locator('.pcb-cancel-notice').innerText()).includes('任务取消本期延期，当前不支持主动中止已提交任务'),`cancellation deferral visible ${width}px ${target}`);if(target.startsWith('/records')){await page.getByRole('button',{name:'更多记录操作',exact:true}).click();await page.getByRole('menuitem',{name:'备注',exact:true}).waitFor();check(await page.getByRole('menuitem',{name:/取消任务|中止任务|终止任务|停止任务/}).count()===0,`history dropdown has no cancel action ${width}px`);}await noCancel(`${width}px ${target}`);await capture(`${width}-${target.split('/').filter(Boolean).join('-').replaceAll('?','-').replaceAll('=','-')}`);}}
  check(calls.every(call=>!/(?:cancel|abort|terminate)/i.test(call.key)),'UI never calls an unsupported cancel endpoint');
  check(unexpected.length===0,`no unmocked endpoints: ${unexpected.join(',')}`);check(errors.length===0,`no browser exceptions: ${errors.join(',')}`);
  await fs.writeFile(path.join(output,'results.json'),JSON.stringify({checks,browser:browser.version(),apiRequests:calls.length,unexpected,errors,environment:'All business API mocked; synthetic images; no production data or inference'},null,2));console.log(`PASS ${checks} legacy PCB detail/history UI assertions.`);
} finally {if(browser)await browser.close();await server.close();const resolved=await fs.realpath(scratch);assert(path.dirname(resolved)===await fs.realpath(os.tmpdir())&&path.basename(resolved).startsWith('steel-pcb-ui-'));await fs.rm(resolved,{recursive:true});}

// Isolated mock UI regression; no database, real API, worker or model execution.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import zlib from 'node:zlib';
import {createHash} from 'node:crypto';
import {createRequire} from 'node:module';
import {fileURLToPath,pathToFileURL} from 'node:url';
const root=fileURLToPath(new URL('../',import.meta.url)),out=path.resolve(process.argv[3]);
await fs.mkdir(out,{recursive:true});assert(!(await fs.readdir(out)).includes('results.json'));
const req=createRequire(path.join(root,'apps/web/package.json'));
const {createServer}=await import(pathToFileURL(req.resolve('vite'))),{chromium}=createRequire(path.join(path.resolve(process.argv[2]),'package.json'))('./');
const temp=await fs.mkdtemp(path.join(os.tmpdir(),'steel-pcb-batch-ui-'));
function crc(bytes){let n=0xffffffff;for(const b of bytes){n^=b;for(let k=0;k<8;k++)n=n&1?(n>>>1)^0xedb88320:n>>>1;}return (n^0xffffffff)>>>0;}
function png(w,h,gray=false,value=gray?1:110){const chunk=(name,data)=>{const type=Buffer.from(name),length=Buffer.alloc(4),checksum=Buffer.alloc(4);length.writeUInt32BE(data.length);checksum.writeUInt32BE(crc(Buffer.concat([type,data])));return Buffer.concat([length,type,data,checksum]);};const ihdr=Buffer.alloc(13);ihdr.writeUInt32BE(w);ihdr.writeUInt32BE(h,4);ihdr[8]=8;ihdr[9]=gray?0:2;const stride=w*(gray?1:3)+1,pixels=Buffer.alloc(stride*h,value);for(let y=0;y<h;y++)pixels[y*stride]=0;return Buffer.concat([Buffer.from([137,80,78,71,13,10,26,10]),chunk('IHDR',ihdr),chunk('IDAT',zlib.deflateSync(pixels)),chunk('IEND',Buffer.alloc(0))]);}
const file=(name,w=220,h=220,gray=false,value)=>({name,mimeType:'image/png',buffer:png(w,h,gray,value)});
const maskDirIndex=process.argv.indexOf('--mask-dir'),maskDir=maskDirIndex<0?null:path.resolve(process.argv[maskDirIndex+1]);
const realMaskEvidence=[];
const models=['unet','unet_resnet18','unetpp_resnet18'].map((slug,i)=>({slug,name:['U-Net','ResNet18-U-Net','ResNet18-U-Net++'][i],available:true,param_count:7000000}));
const limits={max_images:10,max_image_bytes:10485760,max_batch_bytes:52428800,max_side:2048,max_pixels:4194304,max_total_windows:500,tile_size:220,stride:176};
const checks=[],errors=[],unexpected=[],submissions=[],imageRequests=[];const check=(ok,label)=>{assert(ok,label);checks.push(label);};
let browser,server,passed=false,mode='ready',uploadCount=0,uncertain=true,reruns=0,manifest,uploadNames=[],polls=0,denyBatch=false,brokenLayer=false;
function task(id,model,has_gt=false,status='success'){return {id,status,type:'pcb_segmentation',scene:'pcb',task_kind:'segmentation',model:{id:model.slug,name:model.name},has_gt,include_cam:true,samples:[{sample_key:'image',filename:'a.png',width:220,height:220}],metrics:has_gt?{available:true,defect_dice:.9,iou:.82,precision:.87,recall:.93}:{available:false},cam:has_gt?{status:'ok'}:{status:'not_supported_for_size',reason:'仅原生 220×220 RGB 支持 CAM'},artifacts:['origin','overlay','mask_visual','probability','boundary',...(has_gt?['gt','error','cam']:[])].map(kind=>({kind,url:'/api/tasks/'+id+'/file/'+kind+'/image.png',rel_path:kind+'/image.png',sample_key:'image'})),parent_batch_id:'batch',error_summary:status==='failed'?'SYNTHETIC_FAILED: 模拟单项失败':null};}
function batch(failure=false){const samples=[['a.png',220,220,true],['c.png',221,300,false],['d.png',512,384,false]].map(([filename,width,height,has_gt],i)=>({sample_id:'sample-'+i,client_file_id:manifest?.files[i]?.client_file_id||'file-'+i,filename,width,height,has_gt,windows:i===0?1:i===1?4:6,input_plan:{window_count:i===0?1:i===1?4:6},tasks:models.map((m,j)=>task('task-'+i+'-'+j,m,has_gt,failure&&i===0&&j===0?'failed':'success'))}));if(failure&&reruns)samples[0].tasks.push(task('retry',models[0],true));return {batch_id:failure?'partial':'batch',status:failure?'partial_failed':'success',counts:{total:9+(failure?reruns:0),success:(failure?8:9)+(failure?reruns:0),failed:failure?1:0,queued:0,running:0},samples,image_count:3,total_windows:33,selected_model_ids:models.map(m=>m.slug),include_cam:true,open_path:'/inspect/pcb/batches/batch'};}
function pagedBatch(page){const value=batch();value.batch_id='paged';const tail=Array.from({length:95},(_,i)=>task('historical-'+i,models[i%3],false));value.samples[2].tasks=page===1?tail.slice(0,94):[tail[93],tail[94]];if(page===2)value.samples=[value.samples[2]];value.counts={total:101,success:101,failed:0,queued:0,running:0};value.pagination={page,page_size:100,total:101,has_more:page===1};return value;}
try {
 server=await createServer({root:path.join(root,'apps/web'),configFile:path.join(root,'apps/web/vite.config.ts'),envFile:false,envDir:temp,cacheDir:path.join(temp,'vite'),logLevel:'error',server:{host:'127.0.0.1',port:0,proxy:{}}});await server.listen();const origin='http://127.0.0.1:'+server.httpServer.address().port;
 browser=await chromium.launch({headless:true});const context=await browser.newContext({viewport:{width:1440,height:1100}});
 await context.route('**/*',async route=>{const request=route.request(),url=new URL(request.url()),key=url.pathname;if(url.origin!==origin)return route.abort();if(!key.startsWith('/api/'))return route.continue();const json=data=>route.fulfill({json:data});
  if(key==='/api/auth/me')return json({id:'mock',role:'student',username:'批次模拟验收'});
  if(key==='/api/scenes/pcb/segmentation/models')return mode==='error'?route.fulfill({status:503,json:{message:'目录模拟失败'}}):json({enabled:mode!=='disabled',available:mode!=='disabled',models,default_model:'unet',limits});
  if(key.endsWith('/uploads/batch')){uploadCount++;const body=request.postDataBuffer().toString('latin1');const value=body.match(/name="manifest"\r\n\r\n([^\r]+)/);manifest=JSON.parse(value[1]);uploadNames=[...body.matchAll(/name="([^"]+)"; filename="([^"]+)"/g)].map(m=>({field:m[1],filename:m[2]}));return json({...batch(),status:'uploaded',samples:[],counts:{total:0,success:0,failed:0,queued:0,running:0}});}
  if(key.endsWith('/tasks/batch')){submissions.push({...request.postDataJSON(),key:request.headers()['idempotency-key']});return uncertain?route.fulfill({status:503,json:{message:'模拟不确定提交'}}):json(batch());}
  if(key==='/api/scenes/pcb/segmentation/batches/batch')return denyBatch?route.fulfill({status:404,json:{message:'批次不可访问'}}):json(batch());
  if(key==='/api/scenes/pcb/segmentation/batches/paged')return json(pagedBatch(Number(url.searchParams.get('page')||1)));
  if(key==='/api/scenes/pcb/segmentation/batches/polling'){polls++;const value=batch();value.batch_id='polling';if(polls===1){value.status='running';value.counts={total:9,success:8,failed:0,queued:0,running:1};}return json(value);}
  if(key==='/api/scenes/pcb/segmentation/batches/partial')return json(batch(true));
  if(key.endsWith('/rerun')){reruns++;return json(task('retry',models[0],true));}
  if(key.includes('/file/')){imageRequests.push(key);if(brokenLayer&&key.includes('/task-0-0/file/mask_visual/'))return route.fulfill({status:404});const group=Number(key.match(/task-(\d)-/)?.[1]||0),[w,h]=[[220,220],[221,300],[512,384]][group]||[220,220];return route.fulfill({contentType:'image/png',body:png(w,h,key.includes('/gt/')||key.includes('/mask_visual/'),key.includes('/mask_visual/')?255:undefined)});}
  unexpected.push(key);return route.fulfill({status:404,json:{message:'未模拟接口'}});
 });
 const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));page.setDefaultTimeout(15000);
 const go=async p=>{await page.goto(origin+p,{timeout:60000});await page.waitForLoadState('networkidle');};
 const capture=async name=>{for(const img of await page.locator('img[loading="lazy"]').all())await img.scrollIntoViewIfNeeded();await page.locator('img').evaluateAll(images=>Promise.all(images.map(img=>img.decode())));await page.evaluate(()=>window.scrollTo(0,0));await page.waitForTimeout(100);await page.screenshot({path:path.join(out,name+'.png'),fullPage:true});};
 await go('/inspect/pcb');
 const picker=page.getByRole('button',{name:'点击此区域选择 PCB 原图',exact:true});
 for(const position of [{x:10,y:10},null]){const promise=page.waitForEvent('filechooser');await picker.click(position?{position}:{});const chooser=await promise;check(chooser.isMultiple(),'whole dropzone opens multiple filechooser '+JSON.stringify(position));await chooser.setFiles([]);}
 await picker.focus();const keyboard=page.waitForEvent('filechooser');await page.keyboard.press('Enter');check((await keyboard).isMultiple(),'keyboard opens multiple picker');
 check(await page.getByRole('button',{name:'选择原图',exact:true}).count()===0,'redundant small original picker removed');
 check(await page.locator('.pcb-advanced').count()===0,'advanced collapse removed');
 check(await page.getByRole('heading',{name:'配对 GT 标签（可选）'}).isVisible()&&await page.getByRole('heading',{name:'生成 Grad-CAM 解释图（可选）'}).isVisible(),'GT and CAM settings always visible');
 check(await page.locator('.pcb-model input:checked').count()===1&&await page.locator('.pcb-model input[value="unet"]').isChecked(),'default U-Net only');
 await page.getByLabel('PCB 原图',{exact:true}).setInputFiles([file('a.png'),file('b.png',110,110),file('c.png',221,300)]);await page.locator('.pcb-image-row').nth(2).waitFor();check(await page.locator('.pcb-image-row').count()===3,'multiple chooser adds three files');
 let chooserEvents=0;page.on('filechooser',()=>chooserEvents++);
 await page.getByRole('button',{name:'删除 b.png',exact:true}).click();check(await page.locator('.pcb-image-row').count()===2,'delete one image');
 const d=file('d.png',512,384);await page.evaluate(({bytes,name})=>{const dt=new DataTransfer();dt.items.add(new File([new Uint8Array(bytes)],name,{type:'image/png'}));document.querySelector('.pcb-dropzone').dispatchEvent(new DragEvent('drop',{bubbles:true,dataTransfer:dt}));},{bytes:[...d.buffer],name:d.name});await page.getByRole('button',{name:'删除 d.png',exact:true}).waitFor();check(await page.locator('.pcb-image-row').count()===3,'drop appends image');
 await page.getByLabel('PCB 原图',{exact:true}).setInputFiles([file('a.png')]);await page.getByText('已忽略重复选择的同名同内容文件。').waitFor();check(await page.locator('.pcb-image-row').count()===3,'reselect same file remains stable');
 await page.getByRole('button',{name:'预览 a.png',exact:true}).click();await page.getByRole('dialog').waitFor();await page.keyboard.press('Escape');await page.getByRole('dialog').waitFor({state:'hidden'});check(chooserEvents===0,'delete/preview/drop do not reopen original picker');
 await page.getByRole('button',{name:'全选全部模型',exact:true}).click();check(await page.locator('.pcb-model input:checked').count()===3,'select all three models');check((await page.locator('.pcb-task-equation').innerText()).includes('9'),'3 images x 3 models gives nine tasks');
 await page.getByRole('button',{name:'取消全选',exact:true}).click();check(await page.getByRole('button',{name:'开始批量分割',exact:true}).isDisabled(),'zero models disables submit');await page.getByRole('button',{name:'全选全部模型',exact:true}).click();
 await page.getByLabel('PCB 配对 GT',{exact:true}).setInputFiles([file('a_gt.png',220,220,true),file('unmatched.png',220,220,true)]);await page.getByText('有 1 张 GT 未配对。', {exact:false}).waitFor();check(await page.getByRole('button',{name:'开始批量分割',exact:true}).isEnabled(),'unmatched GT is explicitly warned but does not block submission');
 const extra=(await page.getByLabel('c.png 的 GT').locator('option').allTextContents()).find(x=>x.startsWith('unmatched.png'));
 await page.getByLabel('c.png 的 GT').selectOption({label:extra});check(await page.getByText('GT 与原图尺寸不一致',{exact:true}).isVisible(),'manual GT mismatch visibly rejected');
 await page.getByRole('button',{name:'移除 GT unmatched.png',exact:true}).click();check(await page.getByLabel('a.png 的 GT').inputValue()!=='','strict name GT auto paired');
 await page.getByText('生成 Grad-CAM',{exact:true}).click();check(await page.getByRole('button',{name:'开始批量分割',exact:true}).isDisabled(),'non-native CAM requires explicit acknowledgement');await page.getByText('我确认这些图片仅生成分割图层，不生成 CAM',{exact:true}).click();
 await capture('desktop-form');
 const submit=async()=>{await page.getByRole('button',{name:'开始批量分割',exact:true}).click();await page.getByText('模拟不确定提交',{exact:false}).waitFor();};await submit();await page.locator('.pcb-model input[value="unetpp_resnet18"]').uncheck();await submit();await page.locator('.pcb-model input[value="unetpp_resnet18"]').check();await submit();
 check(uploadCount===1,'uncertain retries reuse one uploaded batch');check(submissions[0].key===submissions[2].key&&submissions[1].key!==submissions[0].key,'selection A-B-A uses stable per-option keys');check(new Set(manifest.files.map(f=>f.client_file_id)).size===3,'manifest has stable unique client IDs');check(manifest.files.filter(f=>f.gt_field).length===1,'manifest explicitly pairs only one GT');
 uncertain=false;await page.getByRole('button',{name:'开始批量分割',exact:true}).click();await page.waitForURL('**/batches/batch');await page.getByRole('heading',{name:'全部完成',exact:true}).waitFor();
 check(await page.locator('.pcb-sample-toggle').count()===0,'result accordion removed');
 check(await page.locator('.pcb-reference-card').count()===2&&await page.locator('.pcb-child-card').count()===3,'first image immediately shows original, GT and three model columns');
 check(await page.locator('.pcb-comparison-grid img').count()===5,'first image layers require no expand click');
 check(await page.locator('.pcb-metrics-table tbody tr').count()===3,'GT metrics shown per current-image model');
 check(await page.getByLabel('选择对比图片',{exact:true}).inputValue()==='sample-0','first source is initially selected');
 check(await page.getByRole('button',{name:'上一张',exact:true}).isDisabled(),'first-image previous navigation is disabled');
 check(imageRequests.every(url=>url.includes('/task-0-')),'only the current source image layers are requested');
 await capture('desktop-montage-mask');
 const firstModelFrame=page.locator('.pcb-child-card .pcb-comparison-frame').first();await firstModelFrame.click();await page.getByRole('dialog').waitFor();
 check(await page.locator('.pcb-zoom-image').count()===1&&(await page.locator('.pcb-zoom-image').getAttribute('src')).includes('/task-0-0/file/mask_visual/'),'model preview opens the selected image and layer');await page.keyboard.press('Escape');await page.getByRole('dialog').waitFor({state:'hidden'});
 await page.getByRole('tab',{name:'错误图拼图',exact:true}).click();
 check(await page.getByRole('tab',{name:'错误图拼图',exact:true}).getAttribute('aria-selected')==='true','GT error montage selectable');
 await page.getByRole('button',{name:'下一张',exact:true}).click();
 check(await page.getByLabel('选择对比图片',{exact:true}).inputValue()==='sample-1','next arrow changes source image');
 check(await page.getByRole('tab',{name:'错误图拼图',exact:true}).isDisabled(),'error layer disabled for no-GT sample');
 check(await page.getByRole('tab',{name:'掩码拼图',exact:true}).getAttribute('aria-selected')==='true','unsupported error layer falls back to mask on sample switch');
 check(await page.locator('.pcb-metrics-table').count()===0,'no-GT source never shows numeric metrics table');
 check(await page.locator('.pcb-reference-card').count()===2&&await page.locator('.pcb-reference-card').nth(1).locator('img').count()===0,'no-GT source retains explicit empty GT column');
 await page.getByRole('tab',{name:'概率热力图',exact:true}).click();check(await page.locator('.pcb-child-card img').count()===3,'probability layers available without CAM');
 await page.getByRole('tab',{name:'Grad-CAM',exact:true}).click();
 check(await page.locator('.pcb-child-card img').count()===0&&(await page.locator('.pcb-child-card').allTextContents()).every(t=>t.includes('CAM')),'unsupported CAM shows individual explanations without fake heatmaps');
 await page.getByRole('tab',{name:'概率热力图',exact:true}).click();
 const download=page.waitForEvent('download');await page.getByRole('button',{name:'下载此图层（原尺寸）',exact:true}).first().click();check((await download).suggestedFilename().endsWith('_probability.png'),'authorized layer download action');
 await capture('desktop-montage-probability');
 await page.getByRole('button',{name:'下一张',exact:true}).click();check(await page.getByRole('button',{name:'下一张',exact:true}).isDisabled(),'last-image next navigation is disabled');
 await page.getByLabel('选择对比图片',{exact:true}).selectOption('sample-0');
 check(await page.locator('.pcb-metrics-table tbody tr').count()===3&&await page.locator('.pcb-child-card img').count()===3,'A-B-A source navigation restores correct GT and models');
 await page.reload();await page.getByRole('heading',{name:'全部完成',exact:true}).waitFor();check(await page.getByLabel('选择对比图片',{exact:true}).locator('option').count()===3,'batch source selector survives browser refresh');
 await go('/inspect/pcb/batches/partial');check(await page.getByRole('button',{name:'仅再跑此项',exact:true}).count()===1,'failed child has independent rerun control');await page.getByRole('button',{name:'仅再跑此项',exact:true}).click();
 await page.waitForFunction(()=>document.querySelector('.pcb-batch-summary')?.textContent.includes('10'));check(reruns===1,'failed item creates only one new task; old successes retained');
 for(const width of [1440,768,390]){await page.setViewportSize({width,height:1000});await go('/inspect/pcb');check(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'form no horizontal overflow '+width);if(width===390)await capture('mobile-form');await go('/inspect/pcb/batches/batch');check(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'montage does not widen page '+width);check(await page.locator('.pcb-reference-card').count()===2&&await page.locator('.pcb-child-card').count()===3,'all comparison columns retained at '+width);if(width===390)await capture('mobile-batch');}
 await page.setViewportSize({width:1440,height:1100});await go('/inspect/pcb/batches/paged');
 check(await page.getByLabel('选择对比图片',{exact:true}).locator('option').count()===3,'authorized pages merge into one source selector');
 await page.getByLabel('选择对比图片',{exact:true}).selectOption('sample-2');
 check(await page.locator('.pcb-child-card').count()===95,'same-source tasks across pages are merged and duplicate IDs removed');
 await go('/inspect/pcb/batches/polling');await page.getByLabel('选择对比图片',{exact:true}).selectOption('sample-1');await page.getByRole('heading',{name:'全部完成',exact:true}).waitFor();
 check(polls>=2&&await page.getByLabel('选择对比图片',{exact:true}).inputValue()==='sample-1','polling preserves selected source ID');
 brokenLayer=true;await go('/inspect/pcb/batches/batch');await page.waitForFunction(()=>document.querySelectorAll('.pcb-child-card img').length===2);
 check(await page.locator('.pcb-child-card').count()===3&&await page.locator('.pcb-reference-card img').count()===2,'failed model preview does not hide other results or reference images');brokenLayer=false;
 await page.getByRole('button',{name:'重新加载图层',exact:true}).click();await page.waitForFunction(()=>document.querySelectorAll('.pcb-child-card img').length===3);
 check(await page.locator('.pcb-child-card img').first().evaluate(img=>img.complete&&img.naturalWidth===220),'failed preview recovers after explicit layer reload');
 denyBatch=true;await page.reload();await page.getByRole('alert').filter({hasText:'批次不可访问'}).waitFor();check(await page.locator('.pcb-comparison-grid').count()===0,'authorization failure removes prior comparison view');denyBatch=false;
 await go('/inspect/pcb');
 const dropped=[file('drop-a.png'),file('drop-b.png',110,110),file('drop-c.png',220,220,true)];
 await page.evaluate(files=>{const dt=new DataTransfer();for(const row of files)dt.items.add(new File([new Uint8Array(row.bytes)],row.name,{type:'image/png'}));document.querySelector('.pcb-dropzone').dispatchEvent(new DragEvent('drop',{bubbles:true,dataTransfer:dt}));},dropped.map(f=>({name:f.name,bytes:[...f.buffer]})));
 await page.locator('.pcb-image-row').nth(2).waitFor();check(await page.locator('.pcb-image-row').count()===3,'drop three files together succeeds');
 await page.getByRole('button',{name:'删除 drop-b.png',exact:true}).click();await page.getByRole('button',{name:'删除 drop-a.png',exact:true}).click();await page.getByText('生成 Grad-CAM',{exact:true}).click();
 check(await page.getByText('有 1 张图片不支持 CAM：drop-c.png',{exact:true}).isVisible()&&await page.getByRole('button',{name:'开始批量分割',exact:true}).isDisabled(),'gray 220 image requires CAM acknowledgement');
 await go('/inspect/pcb');await page.getByLabel('PCB 原图',{exact:true}).setInputFiles([file('pair.png')]);await page.locator('.pcb-image-row').waitFor();
 await page.getByLabel('PCB 配对 GT',{exact:true}).setInputFiles([file('pair_gt.png',220,220,true)]);await page.getByLabel('pair.png 的 GT').locator('option:checked').filter({hasText:'pair_gt.png'}).waitFor({state:'attached'});check(await page.getByLabel('pair.png 的 GT').inputValue()!=='','unique GT initially pairs');
 await page.getByLabel('PCB 配对 GT',{exact:true}).setInputFiles([file('pair_mask.png',220,220,true)]);await page.getByText('有 2 张 GT 未配对。',{exact:false}).waitFor();check(await page.getByLabel('pair.png 的 GT').inputValue()==='','adding competing GT invalidates previous automatic pair');
 const explicit=(await page.getByLabel('pair.png 的 GT').locator('option').allTextContents()).find(x=>x.startsWith('pair_gt.png'));await page.getByLabel('pair.png 的 GT').selectOption({label:explicit});
 await page.getByLabel('PCB 原图',{exact:true}).setInputFiles([file('pair.png',221,220)]);await page.locator('.pcb-image-row').nth(1).waitFor();check((await page.getByLabel('pair.png 的 GT',{exact:true}).all()).length===2,'same-name different-content images remain distinct');check(await page.getByLabel('pair.png 的 GT',{exact:true}).first().inputValue()!=='','explicit GT mapping survives additions');

 // Explicit order mapping never infers semantic identity from unrelated names.
 await go('/inspect/pcb');
 await page.getByLabel('PCB 原图',{exact:true}).setInputFiles([file('photo-one.png'),file('photo-two.png'),file('photo-three.png')]);await page.locator('.pcb-image-row').nth(2).waitFor();
 await page.getByLabel('PCB 配对 GT',{exact:true}).setInputFiles([file('label-99.png',220,220,true),file('label-07.png',220,220,true)]);
 await page.getByText('有 2 张 GT 未配对。',{exact:false}).waitFor();
 await page.getByRole('button',{name:'按列表顺序配对',exact:true}).click();
 const selectedName=async name=>page.getByLabel(name+' 的 GT',{exact:true}).locator('option:checked').textContent();
 check((await selectedName('photo-one.png')).includes('label-99.png')&&(await selectedName('photo-two.png')).includes('label-07.png')&&(await selectedName('photo-three.png')).includes('不配对'),'different filenames map in explicit list order; surplus image remains without GT');
 check(await page.getByRole('button',{name:'开始批量分割',exact:true}).isEnabled(),'fewer GT files than images remains submittable');
 const secondMapping=await page.getByLabel('photo-two.png 的 GT',{exact:true}).inputValue();
 await page.getByRole('button',{name:'删除 photo-one.png',exact:true}).click();
 check(await page.getByLabel('photo-two.png 的 GT',{exact:true}).inputValue()===secondMapping&&(await selectedName('photo-three.png')).includes('不配对'),'deleting an image does not shift remaining explicit mappings');
 const directPicker=page.waitForEvent('filechooser');await page.getByRole('button',{name:'为 photo-three.png 选择掩码',exact:true}).click();const directDialog=await directPicker;
 check(!directDialog.isMultiple(),'per-image mask picker accepts exactly one file');await directDialog.setFiles([file('unrelated-single.png',220,220,false,255)]);
 await page.getByLabel('photo-three.png 的 GT',{exact:true}).locator('option:checked').filter({hasText:'unrelated-single.png'}).waitFor({state:'attached'});
 check((await selectedName('photo-three.png')).includes('unrelated-single.png'),'per-image picker directly associates RGB binary PNG despite different filename');
 await page.getByRole('button',{name:'开始批量分割',exact:true}).click();await page.waitForURL('**/batches/batch');
 check(manifest.files.length===2&&manifest.files.every(row=>row.gt_field)&&uploadNames.some(row=>row.filename==='label-07.png')&&uploadNames.some(row=>row.filename==='unrelated-single.png')&&!uploadNames.some(row=>row.filename==='label-99.png'),'multipart sends only explicitly associated GT, not warned unused files');
 // An optional unpaired GT can be retained without claiming any metrics.
 await go('/inspect/pcb');await page.getByLabel('PCB 原图',{exact:true}).setInputFiles([file('no-label-image.png')]);await page.locator('.pcb-image-row').waitFor();
 await page.getByLabel('PCB 配对 GT',{exact:true}).setInputFiles([file('unused-only.png',220,220,true)]);await page.getByText('有 1 张 GT 未配对。',{exact:false}).waitFor();
 await page.getByRole('button',{name:'开始批量分割',exact:true}).click();await page.waitForURL('**/batches/batch');
 check(!manifest.files[0].gt_field&&!uploadNames.some(row=>row.filename==='unused-only.png'),'unpaired-only warning permits no-GT upload without silently attaching a mask');

 // A rejected per-image file must not trap a corrected or intentionally empty mapping.
 await go('/inspect/pcb');await page.getByLabel('PCB 原图',{exact:true}).setInputFiles([file('recover.png')]);await page.locator('.pcb-image-row').waitFor();
 await page.getByLabel('PCB 配对 GT',{exact:true}).setInputFiles([file('valid-label.png',220,220,true)]);await page.getByText('有 1 张 GT 未配对。',{exact:false}).waitFor();
 const rejectWrongSize=async()=>{const picker=page.waitForEvent('filechooser');await page.getByRole('button',{name:'为 recover.png 选择掩码',exact:true}).click();await(await picker).setFiles([file('wrong-size.png',110,110,true)]);await page.getByRole('alert').filter({hasText:'掩码与这张原图尺寸不一致'}).waitFor();};
 await rejectWrongSize();check(await page.getByRole('button',{name:'开始批量分割',exact:true}).isDisabled(),'wrong-size per-image mask is visibly rejected');
 const validLabel=(await page.getByLabel('recover.png 的 GT').locator('option').allTextContents()).find(x=>x.startsWith('valid-label.png'));
 await page.getByLabel('recover.png 的 GT').selectOption({label:validLabel});check(await page.getByRole('button',{name:'开始批量分割',exact:true}).isEnabled()&&await page.getByRole('alert').filter({hasText:'掩码与这张原图尺寸不一致'}).count()===0,'valid dropdown mapping clears rejected-file error and restores submit');
 await rejectWrongSize();await page.getByLabel('recover.png 的 GT').selectOption('');check(await page.getByRole('button',{name:'开始批量分割',exact:true}).isEnabled(),'choosing no GT after a rejected file restores no-GT submission');
 await rejectWrongSize();await page.getByRole('button',{name:'按列表顺序配对',exact:true}).click();check(await page.getByRole('button',{name:'开始批量分割',exact:true}).isEnabled()&&(await selectedName('recover.png')).includes('valid-label.png'),'explicit order correction clears rejected-file error');
 // Replacing one of two conflicting mappings must preserve the sibling's GT identity.
 await go('/inspect/pcb');await page.getByLabel('PCB 原图',{exact:true}).setInputFiles([file('shared-a.png'),file('shared-b.png')]);await page.locator('.pcb-image-row').nth(1).waitFor();
 await page.getByLabel('PCB 配对 GT',{exact:true}).setInputFiles([file('shared-label.png',220,220,true)]);await page.getByText('有 1 张 GT 未配对。',{exact:false}).waitFor();
 const sharedLabel=(await page.getByLabel('shared-a.png 的 GT').locator('option').allTextContents()).find(x=>x.startsWith('shared-label.png'));
 await page.getByLabel('shared-a.png 的 GT').selectOption({label:sharedLabel});await page.getByLabel('shared-b.png 的 GT').selectOption({label:sharedLabel});const sharedId=await page.getByLabel('shared-b.png 的 GT').inputValue();
 check(await page.getByRole('button',{name:'开始批量分割',exact:true}).isDisabled(),'same GT assigned to two images is rejected');
 const sharedReplacement=page.waitForEvent('filechooser');await page.getByRole('button',{name:'为 shared-a.png 选择掩码',exact:true}).click();await(await sharedReplacement).setFiles([file('new-a-label.png',220,220,true)]);
 await page.getByLabel('shared-a.png 的 GT').locator('option:checked').filter({hasText:'new-a-label.png'}).waitFor({state:'attached'});
 check(await page.locator('.pcb-gt-file').count()===2&&await page.getByLabel('shared-b.png 的 GT').inputValue()===sharedId&&(await selectedName('shared-b.png')).includes('shared-label.png')&&await page.getByRole('button',{name:'开始批量分割',exact:true}).isEnabled(),'per-image replacement retains sibling shared GT and restores two valid mappings');
 // Full batch replacement must not be mistaken for adding an eleventh GT.
 await go('/inspect/pcb');
 const tenImages=Array.from({length:10},(_,i)=>file('image-'+i+'.png')),tenGT=Array.from({length:10},(_,i)=>file('annotation-'+i+'.png',220,220,true));
 await page.getByLabel('PCB 原图',{exact:true}).setInputFiles(tenImages);await page.locator('.pcb-image-row').nth(9).waitFor();
 await page.getByLabel('PCB 配对 GT',{exact:true}).setInputFiles(tenGT);await page.getByText('有 10 张 GT 未配对。',{exact:false}).waitFor();await page.getByRole('button',{name:'按列表顺序配对',exact:true}).click();
 const replacementPicker=page.waitForEvent('filechooser');await page.getByRole('button',{name:'为 image-0.png 选择掩码',exact:true}).click();await (await replacementPicker).setFiles([file('replacement.png',220,220,true)]);
 await page.getByLabel('image-0.png 的 GT',{exact:true}).locator('option:checked').filter({hasText:'replacement.png'}).waitFor({state:'attached'});
 check(await page.locator('.pcb-gt-file').count()===10&&(await selectedName('image-9.png')).includes('annotation-9.png')&&await page.getByRole('button',{name:'开始批量分割',exact:true}).isEnabled(),'ten-file GT limit allows targeted replacement without shifting siblings');

 const lastGT=(await page.getByLabel('image-0.png 的 GT').locator('option').allTextContents()).find(x=>x.startsWith('annotation-9.png'));await page.getByLabel('image-0.png 的 GT').selectOption({label:lastGT});const ninthGT=await page.getByLabel('image-9.png 的 GT').inputValue();
 const fullSharedPicker=page.waitForEvent('filechooser');await page.getByRole('button',{name:'为 image-0.png 选择掩码',exact:true}).click();await(await fullSharedPicker).setFiles([file('eleventh.png',220,220,true)]);
 await page.getByRole('alert').filter({hasText:'掩码列表已满'}).waitFor();check(await page.locator('.pcb-gt-file').count()===10&&await page.getByLabel('image-9.png 的 GT').inputValue()===ninthGT&&(await selectedName('image-9.png')).includes('annotation-9.png'),'full list refuses replacing shared GT without deleting sibling data');
 const previous=(await page.getByLabel('image-0.png 的 GT').locator('option').allTextContents()).find(x=>x.startsWith('replacement.png'));await page.getByLabel('image-0.png 的 GT').selectOption({label:previous});check(await page.getByRole('button',{name:'开始批量分割',exact:true}).isEnabled(),'full-list conflict recovers by selecting the unused existing GT');
 // Real user masks are read only with an explicit path, never production images or APIs.
 if(maskDir){
  const supplied=[];for(let i=1;i<=5;i++){const name=`99-10e302a02-2-8-9_10-${i}_Cur.png`,buffer=await fs.readFile(path.join(maskDir,name));supplied.push({name,mimeType:'image/png',buffer});realMaskEvidence.push({filename:name,width:buffer.readUInt32BE(16),height:buffer.readUInt32BE(20),bitDepth:buffer[24],colorType:buffer[25],sha256:createHash('sha256').update(buffer).digest('hex')});}
  await go('/inspect/pcb');await page.getByLabel('PCB 原图',{exact:true}).setInputFiles(realMaskEvidence.map((row,i)=>file('synthetic-source-'+(i+1)+'.png',row.width,row.height)));await page.locator('.pcb-image-row').nth(4).waitFor();
  await page.getByLabel('PCB 配对 GT',{exact:true}).setInputFiles(supplied);await page.getByText('有 5 张 GT 未配对。',{exact:false}).waitFor();
  check(await page.locator('.pcb-gt-file').count()===5,'all five actual user masks pass frontend format selection');await page.getByRole('button',{name:'按列表顺序配对',exact:true}).click();
  for(let i=0;i<5;i++)check((await selectedName('synthetic-source-'+(i+1)+'.png')).includes(supplied[i].name),'actual mask explicitly paired by order '+(i+1));
  await capture('actual-mask-order-desktop');await page.setViewportSize({width:390,height:1000});check(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'actual mask pairing has no horizontal mobile overflow');await capture('actual-mask-order-mobile');
  await page.getByRole('button',{name:'开始批量分割',exact:true}).click();await page.waitForURL('**/batches/batch');
  check(manifest.files.length===5&&manifest.files.every((row,i)=>uploadNames.some(part=>part.field===row.gt_field&&part.filename===supplied[i].name)),'actual mask multipart manifest preserves five explicit pairings');
  await fs.writeFile(path.join(out,'actual-mask-selection.json'),JSON.stringify({scope:'Real mask bytes with synthetic same-size images; mock API only, not inference or accuracy',status:'PASS',masks:realMaskEvidence,manifest,uploadNames},null,2));
  await page.setViewportSize({width:1440,height:1100});
 }
 await go('/inspect/pcb');await page.getByLabel('PCB 原图',{exact:true}).setInputFiles([file('huge-a.png',2048,2048),file('huge-b.png',2048,2048)]);await page.locator('.pcb-image-row').nth(1).waitFor();await page.getByRole('button',{name:'全选全部模型',exact:true}).click();await page.getByText('窗口推理预算超限，请减少图像、尺寸或模型数量。',{exact:true}).waitFor();check(await page.getByRole('button',{name:'开始批量分割',exact:true}).isDisabled(),'window-model budget rejects 864 requested windows');
 for(const state of ['disabled','error']){mode=state;await go('/inspect/pcb');check(await page.getByRole('button',{name:'开始批量分割',exact:true}).isDisabled(),state+' cannot submit');}
 check(errors.length===0,'no browser JS errors');check(unexpected.length===0,'no unexpected API calls');passed=true;console.log('PASS '+checks.length+' PCB batch UI assertions');
} finally {await fs.writeFile(path.join(out,'results.json'),JSON.stringify({status:passed?'PASS':'FAIL',checks:checks.length,assertions:checks,errors,unexpected,scope:'mock API; not CPU or actual queue',realMasksChecked:realMaskEvidence.length},null,2));if(browser)await browser.close();if(server)await server.close();const resolved=await fs.realpath(temp);assert(path.dirname(resolved)===await fs.realpath(os.tmpdir())&&path.basename(resolved).startsWith('steel-pcb-batch-ui-'));await fs.rm(resolved,{recursive:true});}

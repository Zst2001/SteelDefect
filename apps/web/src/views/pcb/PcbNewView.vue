<template>
  <div class="pcb-scope pcb-new">
    <PcbTabs />
    <header class="pcb-head pcb-workbench-head">
      <div><p class="pcb-eyebrow">PCB / 表面缺陷分割</p><h1>PCB 表面缺陷分割工作台</h1></div>
      <div class="pcb-quick-guide" aria-label="操作流程">
        <ol><li>上传原图</li><li>选择模型</li><li>查看对比</li></ol>
        <p>GT 标签与 Grad-CAM 按需开启</p>
      </div>
    </header>
    <div v-if="loading" class="pcb-state" role="status">正在检查 PCB 模型与服务状态…</div>
    <div v-else-if="catalogError" class="pcb-state error" role="alert"><strong>PCB 模型目录暂不可用</strong><p>{{ catalogError }}</p><el-button @click="loadCatalog">重新加载目录</el-button></div>
    <div v-else-if="!ready" class="pcb-state" role="status"><strong>PCB 分割暂未启用</strong><p>三个模型须完成本机准入并启用服务。已有结果仍可从历史记录查看。</p><el-button @click="loadCatalog">重新检查状态</el-button></div>
    <div class="pcb-batch-form">
      <section class="pcb-panel pcb-images-panel">
        <div class="pcb-panel-head"><div><h2>上传 PCB 原图</h2><p>原生 220 × 220 保持原协议；其他尺寸按原像素滑窗处理。</p></div><span class="pcb-pill">{{ images.length }} / {{ limits.max_images }} 张</span></div>
        <label for="pcb-batch-images" class="pcb-dropzone" :class="{ dragging, disabled: !ready || busy }" :tabindex="ready && !busy ? 0 : -1" role="button" :aria-disabled="!ready || busy" aria-label="点击此区域选择 PCB 原图" @click="blockPicker" @keydown.enter.prevent="openImages" @keydown.space.prevent="openImages" @dragover.prevent="dragging = ready && !busy" @dragleave.prevent="dragging = false" @drop.prevent.stop="dropImages">
          <el-icon><UploadFilled /></el-icon><strong>点击此区域选择 PCB 原图</strong><span>也可以将多张图片拖到这里</span><small>PNG / JPG · 最多 {{ limits.max_images }} 张 · 单张 {{ mib(limits.max_image_bytes) }} · 最长边 {{ limits.max_side }} px</small>
        </label>
        <input id="pcb-batch-images" ref="imageInput" class="pcb-file-input" type="file" multiple accept=".png,.jpg,.jpeg" aria-label="PCB 原图" :disabled="!ready || busy" @change="chooseImages" />
        <p v-if="validating" role="status" class="pcb-muted">正在检查图像，请稍候…</p>
        <div v-if="imageErrors.length" class="pcb-error" role="alert"><p v-for="message in imageErrors" :key="message">{{ message }}</p></div>
        <p v-if="notice" class="pcb-muted" role="status">{{ notice }}</p>
        <div v-if="images.length" class="pcb-image-list" aria-label="已选原图">
          <article v-for="row in images" :key="row.id" class="pcb-image-row">
            <button type="button" class="pcb-thumb" :aria-label="'预览 ' + row.file.name" @click="preview = row"><img :src="row.url" :alt="row.file.name" /></button>
            <div class="pcb-image-info"><strong>{{ row.file.name }}</strong><span>{{ row.width }} × {{ row.height }} · {{ mib(row.file.size) }}</span><small>{{ windows(row) }} 个窗口 · {{ gtFor(row) ? '已配对 GT' : '无 GT，仅展示分割' }}</small></div>
            <button type="button" class="pcb-text-button" :disabled="busy" :aria-label="'删除 ' + row.file.name" @click="removeImage(row.id)">删除</button>
          </article>
        </div>
        <p class="pcb-muted">支持 RGB 与 8 位灰度图；灰度将复制为三通道。颜色模式、EXIF、文件内容和 GT 由服务端再次核验。</p>
      </section>
      <section class="pcb-panel pcb-models-panel">
        <div class="pcb-panel-head"><div><h2>选择分割模型</h2><p>每张图像与每个模型形成独立结果</p></div><span class="pcb-pill">已选 {{ selected.length }} / {{ models.length }}</span></div>
        <div class="pcb-actions pcb-select-actions"><el-button :disabled="!ready || busy" @click="selected = models.filter(m => m.available).map(m => m.slug)">全选全部模型</el-button><el-button :disabled="busy || !selected.length" @click="selected = []">取消全选</el-button></div>
        <div class="pcb-models" role="group" aria-label="PCB 分割模型"><label v-for="model in models" :key="model.slug" class="pcb-model" :class="{ selected: selected.includes(model.slug) }"><input v-model="selected" type="checkbox" :value="model.slug" :disabled="!ready || !model.available || busy" /><span><strong>{{ model.name }}</strong><small>参数量 {{ formatParamCount(model.param_count) }}</small></span><em>{{ model.slug === 'unet' ? '默认' : '备选' }}</em></label></div>
      </section>
      <section class="pcb-panel pcb-analysis-panel">
        <div class="pcb-panel-head"><div><h2>附加分析选项</h2><p>均为可选；未配对 GT 的图像不计算指标</p></div></div>
        <div class="pcb-option-card">
          <h3>配对 GT 标签（可选）</h3><p class="pcb-muted">文件名无需一致。可逐张选择掩码，或批量添加后按列表顺序配对；请核对原图与掩码内容。掩码须为同尺寸二值 PNG。</p>
          <div class="pcb-actions"><el-button :disabled="!ready || busy || !images.length" @click="gtInput?.click()">添加 GT 标签</el-button><el-button :disabled="!ready || busy || !images.length || !gts.length" @click="pairByOrder">按列表顺序配对</el-button></div>
          <input ref="gtInput" class="pcb-file-input" type="file" multiple accept=".png" aria-label="PCB 配对 GT" :disabled="!ready || busy || !images.length" @change="chooseGT" />
          <input ref="rowGTInput" class="pcb-file-input" type="file" accept=".png" aria-label="为当前原图选择掩码" :disabled="!ready || busy" @change="chooseRowGT" />
          <p v-for="message in gtErrors" :key="message" class="pcb-error" role="alert">{{ message }}</p>
          <p v-if="gtNotice" class="pcb-muted" role="status">{{ gtNotice }}</p>
          <div v-if="images.length" class="pcb-gt-pairs">
            <div v-for="(row,index) in images" :key="row.id" class="pcb-gt-pair">
              <div class="pcb-gt-pair-head"><span>{{ index + 1 }}. {{ row.file.name }}</span><button type="button" class="pcb-text-button" :disabled="!ready || busy" :aria-label="'为 ' + row.file.name + ' 选择掩码'" @click="openRowGT(row.id)">选择掩码</button></div>
              <select :value="gtMap[row.id] || ''" :disabled="busy" :aria-label="row.file.name + ' 的 GT'" @change="assignGT(row.id, ($event.target as HTMLSelectElement).value)"><option value="">不配对 GT</option><option v-for="(g,maskIndex) in gts" :key="g.id" :value="g.id">{{ g.file.name }} · {{ g.width }}×{{ g.height }} · 掩码 {{ maskIndex + 1 }}</option></select>
              <button v-if="gtFor(row)" type="button" class="pcb-text-button pcb-mask-preview" :aria-label="'预览 ' + row.file.name + ' 的掩码'" @click="preview = gtFor(row) || null">预览已配对掩码</button><small v-if="pairError(row)" class="pcb-error">{{ pairError(row) }}</small>
            </div>
            <div v-for="(g,index) in gts" :key="g.id" class="pcb-gt-file"><span>掩码 {{ index + 1 }} · {{ g.file.name }} · {{ Object.values(gtMap).includes(g.id) ? '已关联' : '未配对，本次不上传' }}</span><button type="button" class="pcb-text-button" :disabled="busy" :aria-label="'移除 GT ' + g.file.name" @click="removeGT(g.id)">移除</button></div>
          </div>
          <p v-if="unpairedGT" class="pcb-muted" role="status">有 {{ unpairedGT }} 张 GT 未配对。本次不会上传这些掩码；未配对 GT 的原图仅生成分割结果，不计算指标。</p>
        </div>
        <div class="pcb-option-card">
          <h3>生成 Grad-CAM 解释图（可选）</h3><el-checkbox v-model="includeCam" :disabled="!ready || busy">生成 Grad-CAM</el-checkbox><p class="pcb-muted">会增加 CPU 耗时，仅原生 220 × 220 RGB 图片支持。关闭后仍可查看缺陷概率热力图。</p>
          <div v-if="includeCam && unsupportedCAM.length" class="pcb-cam-confirm"><p>有 {{ unsupportedCAM.length }} 张图片不支持 CAM：{{ unsupportedCAM.map(i => i.file.name).join('、') }}</p><el-checkbox v-model="acceptUnsupported" :disabled="busy">我确认这些图片仅生成分割图层，不生成 CAM</el-checkbox></div>
        </div>
      </section>
      <section class="pcb-panel pcb-submit">
        <div class="pcb-panel-head"><div><h2>提交摘要</h2><p>确认本次选择，提交后查看各模型结果</p></div></div><p class="pcb-task-equation"><strong>{{ images.length }}</strong> 张图片 × <strong>{{ selected.length }}</strong> 个模型 = <strong>{{ taskCount }}</strong> 个子任务</p>
        <dl class="pcb-budget"><div><dt>窗口推理次数</dt><dd>{{ totalWindows }} / {{ limits.max_total_windows }}</dd></div><div><dt>原图与 GT 总大小</dt><dd>{{ mib(totalBytes) }} / {{ mib(limits.max_batch_bytes) }}</dd></div></dl>
        <p v-if="budgetError" class="pcb-error" role="alert">{{ budgetError }}</p><p v-if="submitError" class="pcb-error" role="alert">{{ submitError }}</p><p v-if="uploadedBatch && submitError" class="pcb-muted">上传已保存；相同选项重试会复用同一批次和请求身份。</p>
        <el-button type="primary" :disabled="!canSubmit" :loading="submitting" @click="submit">{{ submitting ? submitStage : '开始批量分割' }}</el-button>
        <p class="pcb-muted">CPU 按队列逐项执行。大图需要更多时间，单项失败不会删除其他结果。{{ PCB_CANCEL_NOTICE }}。</p><router-link to="/records?type=pcb_segmentation">查看 PCB 历史记录 →</router-link>
      </section>
    </div>
    <el-dialog :model-value="!!preview" :title="preview?.file.name || '图像预览'" width="min(900px, 94vw)" destroy-on-close @update:model-value="preview = null"><img v-if="preview" class="pcb-full-preview" :src="preview.url" :alt="preview.file.name + ' 放大预览'" /><p class="pcb-muted">{{ preview?.width }} × {{ preview?.height }} 原始像素；页面按比例缩放显示。</p></el-dialog>
  </div>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { UploadFilled } from "@element-plus/icons-vue";
import { http, formatError } from "../../api/http";
import { formatParamCount } from "../../api/labels";
import PcbTabs from "./PcbTabs.vue";
import { PCB_CANCEL_NOTICE, type PcbCatalog, type PcbLimits, type PcbBatch } from "./types";
import "./pcb.css";
type Picked = { id:string; file:File; url:string; width:number; height:number; hash:string; native:boolean };
const router=useRouter(), catalog=ref<PcbCatalog|null>(null), loading=ref(true), catalogError=ref("");
const images=ref<Picked[]>([]), gts=ref<Picked[]>([]), gtMap=reactive<Record<string,string>>({}), selected=ref<string[]>(["unet"]);
const imageInput=ref<HTMLInputElement|null>(null), gtInput=ref<HTMLInputElement|null>(null), preview=ref<Picked|null>(null);
const rowGTInput=ref<HTMLInputElement|null>(null), rowGTTarget=ref(''), gtNotice=ref('');
const imageErrors=ref<string[]>([]), gtErrors=ref<string[]>([]), notice=ref(""), dragging=ref(false), validating=ref(false), submitting=ref(false), submitStage=ref(""), submitError=ref("");
const includeCam=ref(false), acceptUnsupported=ref(false), uploadedBatch=ref("");
const requestKeys=new Map<string,string>(), manualGT=new Set<string>(); let disposed=false, generation=0;
const fallback:PcbLimits={max_images:10,max_image_bytes:10485760,max_batch_bytes:52428800,max_side:2048,max_pixels:4194304,max_total_windows:500,tile_size:220,stride:176};
const limits=computed(()=>({...fallback,...catalog.value?.limits})), models=computed(()=>catalog.value?.models || []);
const ready=computed(()=>catalog.value?.enabled===true && catalog.value.available===true && models.value.length===3 && models.value.every(m=>m.available));
const busy=computed(()=>validating.value || submitting.value);
const taskCount=computed(()=>images.value.length*selected.value.length);
function windows(row:Picked) { const {tile_size:t,stride:s}=limits.value; const count=(n:number)=>Math.max(1,Math.ceil((n-t)/s)+1); return count(row.width)*count(row.height); }
const totalWindows=computed(()=>images.value.reduce((sum,row)=>sum+windows(row),0)*selected.value.length);
const totalBytes=computed(()=>[...images.value,...gts.value].reduce((sum,row)=>sum+row.file.size,0));
const unsupportedCAM=computed(()=>images.value.filter(row=>!row.native));
const unpairedGT=computed(()=>gts.value.filter(g=>!Object.values(gtMap).includes(g.id)).length);
const budgetError=computed(()=>totalBytes.value>limits.value.max_batch_bytes ? '本批文件超过总大小限制，请减少图片或标签。' : totalWindows.value>limits.value.max_total_windows ? '窗口推理预算超限，请减少图像、尺寸或模型数量。' : '');
const canSubmit=computed(()=>ready.value && !busy.value && images.value.length>0 && selected.value.length>0 && !budgetError.value && !imageErrors.value.length && !gtErrors.value.length && !images.value.some(row=>pairError(row)) && (!includeCam.value || !unsupportedCAM.value.length || acceptUnsupported.value));
function mib(bytes:number) { return (bytes/1048576).toFixed(bytes<1048576?2:1)+' MiB'; }
function resetUpload() { uploadedBatch.value=''; requestKeys.clear(); submitError.value=''; acceptUnsupported.value=false;gtNotice.value=''; }
function gtFor(row:Picked) { return gts.value.find(g=>g.id===gtMap[row.id]); }
function pairError(row:Picked) { const g=gtFor(row); if(!g)return ''; if(g.width!==row.width||g.height!==row.height)return 'GT 与原图尺寸不一致'; if(Object.values(gtMap).filter(id=>id===g.id).length!==1)return '同一 GT 不能关联多张原图'; return ''; }
function assignGT(id:string,gt:string) { manualGT.add(id);gtMap[id]=gt;gtErrors.value=[];resetUpload();autoPair(); }
function pairByOrder() {
  if(!ready.value||busy.value)return;
  for(const [index,row] of images.value.entries()){manualGT.add(row.id);gtMap[row.id]=gts.value[index]?.id||'';}
  gtErrors.value=[];resetUpload();gtNotice.value='已按当前列表顺序配对 '+Math.min(images.value.length,gts.value.length)+' 组。文件选择顺序可能与预期不同，请逐项核对；也可用下拉框调整。';
}
function openRowGT(id:string) { if(!ready.value||busy.value)return;rowGTTarget.value=id;rowGTInput.value?.click(); }
async function chooseRowGT(event:Event) {
  const input=event.target as HTMLInputElement,file=input.files?.[0],target=images.value.find(row=>row.id===rowGTTarget.value);input.value='';
  if(!file||!target||!ready.value||busy.value)return;
  validating.value=true;gtErrors.value=[];let picked:Picked|undefined;
  try {
    picked=await inspect(file,true);
    if(disposed)return;
    if(picked.width!==target.width||picked.height!==target.height)throw new Error('掩码与这张原图尺寸不一致，请选择对应掩码');
    const existing=gts.value.find(row=>row.hash===picked!.hash&&row.file.name===file.name),old=gtFor(target);
    const replaceable=old&&!Object.entries(gtMap).some(([id,mask])=>id!==target.id&&mask===old.id)?old:undefined;
    if(existing&&Object.entries(gtMap).some(([id,mask])=>id!==target.id&&mask===existing.id))throw new Error('这张掩码已关联其他原图，请核对配对');
    if(existing){assignGT(target.id,existing.id);return;}
    if(!replaceable&&gts.value.length>=limits.value.max_images)throw new Error('掩码列表已满，请先移除未使用的掩码或纠正重复配对');
    if(totalBytes.value-(replaceable?.file.size||0)+file.size>limits.value.max_batch_bytes)throw new Error('本批原图与掩码超过总大小限制');
    if(replaceable){const index=gts.value.findIndex(row=>row.id===replaceable.id);gts.value.splice(index,1,picked);URL.revokeObjectURL(replaceable.url);if(preview.value?.id===replaceable.id)preview.value=null;}
    else gts.value.push(picked);
    assignGT(target.id,picked.id);picked=undefined;
  } catch(error) { if(!disposed)gtErrors.value=[file.name+'：'+(error instanceof Error?error.message:'无法读取掩码')]; }
  finally { if(picked)URL.revokeObjectURL(picked.url);if(!disposed)validating.value=false; }
}
function blockPicker(event:MouseEvent) { if(!ready.value||busy.value)event.preventDefault(); }
function openImages() { if(ready.value&&!busy.value)imageInput.value?.click(); }
function removeImage(id:string) { if(busy.value)return; const row=images.value.find(r=>r.id===id); if(row)URL.revokeObjectURL(row.url); if(preview.value?.id===id)preview.value=null;images.value=images.value.filter(r=>r.id!==id); delete gtMap[id];manualGT.delete(id); imageErrors.value=[]; notice.value=''; resetUpload();autoPair(); }
function removeGT(id:string) { if(busy.value)return; const row=gts.value.find(r=>r.id===id); if(row)URL.revokeObjectURL(row.url);if(preview.value?.id===id)preview.value=null; gts.value=gts.value.filter(r=>r.id!==id); for(const key of Object.keys(gtMap))if(gtMap[key]===id){delete gtMap[key];manualGT.delete(key);} gtErrors.value=[]; resetUpload();autoPair(); }
async function inspect(file:File,gt=false):Promise<Picked> {
  if(!file.size||file.size>limits.value.max_image_bytes)throw new Error('文件须非空且不超过 '+mib(limits.value.max_image_bytes));
  const bytes=new Uint8Array(await file.arrayBuffer()), png=[137,80,78,71,13,10,26,10].every((v,i)=>bytes[i]===v), jpeg=bytes[0]===255&&bytes[1]===216&&bytes[2]===255;
  if(!(png&&/\.png$/i.test(file.name)||!gt&&jpeg&&/\.jpe?g$/i.test(file.name)))throw new Error('文件格式与扩展名不一致，仅支持 '+(gt?'PNG GT':'PNG/JPEG'));
  if(png) {
    const depth=bytes[24],color=bytes[25];
    const supportedGT=([0,3].includes(color)&&[1,2,4,8].includes(depth))||(color===2&&depth===8);
    if(gt?!supportedGT:depth!==8||![0,2].includes(color))throw new Error(gt?'掩码须为二值 PNG，支持灰度、黑白调色板或黑白 RGB；不接受透明/16 位图像':'PNG 须为 8 位 RGB 或灰度，不接受透明/16 位图像');
  }
  let channels=png?(bytes[25]===2?3:1):0;
  if(jpeg) {
    for(let offset=2;offset+4<bytes.length;) {
      if(bytes[offset]!==255)break;
      while(bytes[offset]===255)offset++;
      const marker=bytes[offset++]; if(marker===217||marker===218)break;
      const length=(bytes[offset]<<8)|bytes[offset+1];if(length<2||offset+length>bytes.length)break;
      if(marker>=192&&marker<=207&&![196,200,204].includes(marker)) { if(bytes[offset+2]!==8)throw new Error('JPEG 须为 8 位图像');channels=bytes[offset+7];break; }
      offset+=length;
    }
    if(![1,3].includes(channels))throw new Error('JPEG 须为 RGB 或灰度，不接受 CMYK 或无法识别的通道');
  }
  const url=URL.createObjectURL(file);
  try { const im=new Image();im.src=url;await im.decode();const width=im.naturalWidth,height=im.naturalHeight;
    if(width<1||height<1||Math.max(width,height)>limits.value.max_side||width*height>limits.value.max_pixels)throw new Error('图像尺寸超限，最长边 '+limits.value.max_side+' px');
    const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))).map(n=>n.toString(16).padStart(2,'0')).join('');
    return {id:crypto.randomUUID(),file,url,width,height,hash,native:width===220&&height===220&&channels===3};
  } catch(error) { URL.revokeObjectURL(url);throw error; }
}
function autoPair() {
  const stem=(name:string)=>name.replace(/\.[^.]+$/,'');
  // Recheck automatic matches after additions; later duplicate names must not retain a guessed pair.
  for(const row of images.value)if(!manualGT.has(row.id))delete gtMap[row.id];
  for(const g of gts.value) {
    if(Object.values(gtMap).includes(g.id))continue;
    const base=stem(g.file.name), matches=images.value.filter(row=>base===stem(row.file.name)||base===stem(row.file.name)+'_mask'||base===stem(row.file.name)+'_gt');
    // Never guess through duplicated names, dimensions or competing GT choices.
    if(matches.length!==1||manualGT.has(matches[0].id)||gtMap[matches[0].id]||g.width!==matches[0].width||g.height!==matches[0].height)continue;
    const target=stem(matches[0].file.name);
    const competitors=gts.value.filter(x=>[target,target+'_mask',target+'_gt'].includes(stem(x.file.name)));
    if(competitors.length===1)gtMap[matches[0].id]=g.id;
  }
}
async function addFiles(files:File[],gt=false) {
  if(!ready.value||busy.value||!files.length)return;
  validating.value=true;notice.value=''; const errors:string[]=[]; const accepted:Picked[]=[];
  if(gt)gtErrors.value=[];else imageErrors.value=[];
  try {
    const existing=gt?gts.value:images.value;
    if(existing.length+files.length>limits.value.max_images)throw new Error('一次最多保留 '+limits.value.max_images+' 张'+(gt?' GT':'原图'));
    if(totalBytes.value+files.reduce((sum,f)=>sum+f.size,0)>limits.value.max_batch_bytes)throw new Error('本批原图与 GT 总大小不能超过 '+mib(limits.value.max_batch_bytes));
    for(const file of files) { try { const row=await inspect(file,gt); if(disposed){URL.revokeObjectURL(row.url);continue;} if([...existing,...accepted].some(x=>x.hash===row.hash&&x.file.name===file.name)){URL.revokeObjectURL(row.url);notice.value='已忽略重复选择的同名同内容文件。';}else accepted.push(row); }catch(error){errors.push(file.name+'：'+(error instanceof Error?error.message:'无法读取图片'));} }
    if(!disposed) { if(gt)gts.value.push(...accepted);else images.value.push(...accepted); if(accepted.length){resetUpload();autoPair();} }
  } catch(error) { errors.push(error instanceof Error?error.message:'无法添加图像'); }
  finally { if(!disposed){if(gt)gtErrors.value=errors;else imageErrors.value=errors;validating.value=false;}else accepted.forEach(r=>URL.revokeObjectURL(r.url)); }
}
function chooseImages(event:Event) { const input=event.target as HTMLInputElement; const files=Array.from(input.files||[]);input.value='';void addFiles(files); }
function chooseGT(event:Event) { const input=event.target as HTMLInputElement; const files=Array.from(input.files||[]);input.value='';void addFiles(files,true); }
function dropImages(event:DragEvent) { dragging.value=false;void addFiles(Array.from(event.dataTransfer?.files||[])); }
async function loadCatalog() { const current=++generation;loading.value=true;catalogError.value='';try {const {data}=await http.get<PcbCatalog>('/scenes/pcb/segmentation/models');if(!disposed&&current===generation){catalog.value=data;selected.value=[data.default_model];}}catch(error){if(!disposed&&current===generation)catalogError.value=formatError(error);}finally{if(!disposed&&current===generation)loading.value=false;} }
async function submit() {
  if(!canSubmit.value)return;submitting.value=true;submitError.value='';submitStage.value='正在上传…';
  try {
    if(!uploadedBatch.value){const form=new FormData();const files=images.value.map((row,index)=>{const file_field='image_'+index, g=gtFor(row),gt_field=g?'gt_'+index:undefined;form.append(file_field,row.file);if(g&&gt_field)form.append(gt_field,g.file);return {client_file_id:row.id,file_field,...(gt_field?{gt_field}:{})};});form.append('manifest',JSON.stringify({files}));const {data}=await http.post<PcbBatch>('/scenes/pcb/segmentation/uploads/batch',form);if(disposed)return;uploadedBatch.value=data.batch_id;}
    const model_ids=models.value.filter(m=>selected.value.includes(m.slug)).map(m=>m.slug);
    const body={batch_id:uploadedBatch.value,model_ids,include_cam:includeCam.value,accept_unsupported_cam:includeCam.value&&unsupportedCAM.value.length>0&&acceptUnsupported.value};
    const identity=JSON.stringify(body);let key=requestKeys.get(identity);if(!key){key=crypto.randomUUID();requestKeys.set(identity,key);}
    submitStage.value='正在创建子任务…';const {data}=await http.post<PcbBatch>('/scenes/pcb/segmentation/tasks/batch',body,{headers:{'Idempotency-Key':key}});
    if(!disposed)await router.push('/inspect/pcb/batches/'+encodeURIComponent(data.batch_id));
  } catch(error) {if(!disposed)submitError.value=formatError(error);} finally {if(!disposed)submitting.value=false;}
}
watch([selected,includeCam,acceptUnsupported],()=>{submitError.value='';},{deep:true});
onMounted(loadCatalog);onBeforeUnmount(()=>{disposed=true;generation++;[...images.value,...gts.value].forEach(row=>URL.revokeObjectURL(row.url));});
</script>
<style scoped>
.pcb-workbench-head { align-items:center;gap:24px;margin-bottom:26px; }
.pcb-workbench-head h1 { margin-bottom:0; }
.pcb-quick-guide { padding:5px 0 5px 24px;border-left:1px solid var(--pcb-line); }
.pcb-quick-guide ol { display:flex;flex-wrap:wrap;gap:10px 0;list-style:none;padding:0;margin:0 0 8px;color:#365c75;font-size:15px;font-weight:600; }
.pcb-quick-guide li+li::before { content:'→';margin:0 14px;color:#8a9faf;font-weight:400; }
.pcb-quick-guide p { font-size:13px;color:#60778c; }
.pcb-batch-form { display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:22px;align-items:stretch; }
.pcb-batch-form>.pcb-panel h2 { color:#4a83bd; }
.pcb-image-list { max-height:200px;overflow-y:auto;scrollbar-gutter:stable; }
.pcb-gt-pair-head { display:flex;align-items:center;justify-content:space-between;gap:10px; }.pcb-gt-pair-head>span { min-width:0;overflow-wrap:anywhere; }.pcb-mask-preview { justify-self:start;padding:2px 0; }.pcb-gt-pairs { max-height:320px;overflow-y:auto;scrollbar-gutter:stable; }
.pcb-submit { display:flex;flex-direction:column;align-items:stretch; }
.pcb-submit .pcb-task-equation { margin:0 0 6px; }
.pcb-submit>.el-button { margin-top:auto; }
.pcb-submit>.pcb-budget { margin-bottom:24px; }
@media(max-width:1000px) {
  .pcb-workbench-head { align-items:flex-start;gap:18px; }
  .pcb-quick-guide { width:100%;padding:0;border:0; }
  .pcb-submit>.el-button { margin-top:12px; }
}

.pcb-dropzone { display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;text-align:center;min-height:160px;padding:24px 16px;background:#f5f8fd;border:1.5px dashed #a9bfdc;border-radius:9px;cursor:pointer;color:#476483;transition:background .15s,border-color .15s; }.pcb-dropzone:hover,.pcb-dropzone.dragging { background:#eaf2ff;border-color:#477fc7; }.pcb-dropzone:focus-visible { outline:3px solid #91b4ef;outline-offset:3px; }.pcb-dropzone.disabled { opacity:.6;cursor:not-allowed; }.pcb-dropzone .el-icon { font-size:38px;color:#4679b9; }.pcb-dropzone strong { font-size:18px;color:#264e7a; }.pcb-dropzone small { font-size:12px;line-height:1.8; }.pcb-image-list { display:grid;gap:12px;margin-top:20px; }.pcb-image-row { display:flex;align-items:center;gap:12px;padding:11px;border:1px solid #e2e9f2;border-radius:8px; }.pcb-thumb { width:68px;height:68px;flex:none;display:grid;place-items:center;border:0;background:#edf2f7;border-radius:5px;padding:4px;cursor:zoom-in; }.pcb-thumb img { width:100%;height:100%;min-width:0;min-height:0;object-fit:contain; }.pcb-image-info { min-width:0;flex:1;display:grid;gap:5px; }.pcb-image-info strong { font-size:14px;color:#294967;overflow-wrap:anywhere; }.pcb-image-info span,.pcb-image-info small { font-size:12px;color:#59728d; }.pcb-text-button { color:#315f99;background:none;border:0;padding:8px 3px;cursor:pointer;flex:none;font:inherit;font-size:13px; }.pcb-text-button:disabled { opacity:.5;cursor:not-allowed; }.pcb-select-actions { margin-bottom:15px; }.pcb-models { display:grid;gap:10px; }.pcb-model { display:flex;align-items:center;gap:12px;border:1px solid #dce6f2;border-radius:7px;padding:15px;cursor:pointer; }.pcb-model.selected { background:#f1f6ff;border-color:#86aee4; }.pcb-model input { accent-color:#2e6cc9;width:17px;height:17px; }.pcb-model>span { display:grid;gap:5px;flex:1; }.pcb-model strong { font-size:16px;color:#274767; }.pcb-model small { color:#5b7491;font-size:12px; }.pcb-model em { font-size:12px;font-style:normal;color:#547396; }.pcb-option-card { padding:18px 0;border-top:1px solid #e3eaf3; }.pcb-option-card:last-child { padding-bottom:0; }.pcb-option-card h3 { font-size:16px;color:#294967;margin:0 0 10px; }.pcb-option-card .pcb-muted { margin:5px 0 13px; }.pcb-gt-pairs { display:grid;gap:12px;margin-top:15px; }.pcb-gt-pair { display:grid;gap:7px;font-size:13px;color:#466281;overflow-wrap:anywhere; }.pcb-gt-pairs select { min-width:0;width:100%;padding:9px;background:#f8faff;border:1px solid #bfcee0;border-radius:5px;font:inherit;color:#294967; }.pcb-gt-file { display:flex;align-items:center;gap:8px;justify-content:space-between;font-size:12px;color:#617b96;overflow-wrap:anywhere; }.pcb-cam-confirm { padding:12px;background:#fff7ec;border:1px solid #eedbc0;border-radius:6px;color:#78552c;font-size:13px;line-height:1.7; }.pcb-cam-confirm p { margin:0 0 8px;overflow-wrap:anywhere; }.pcb-cam-confirm :deep(.el-checkbox) { white-space:normal;height:auto;align-items:flex-start; }.pcb-cam-confirm :deep(.el-checkbox__label) { white-space:normal;line-height:1.7; }.pcb-task-equation { color:#526c88;font-size:15px;line-height:1.8; }.pcb-task-equation strong { font-size:24px;color:#24528a;font-variant-numeric:tabular-nums; }.pcb-budget { margin:16px 0; }.pcb-budget>div { display:flex;gap:14px;justify-content:space-between;padding:9px 0;border-bottom:1px solid #edf1f6;font-size:13px;color:#56708d; }.pcb-budget dd { margin:0;color:#294967; }.pcb-submit>.el-button { width:100%;min-height:44px; }.pcb-full-preview { display:block;max-width:100%;max-height:70vh;object-fit:contain;margin:auto; }.pcb-error p { margin:4px 0; }
@media(max-width:1000px) { .pcb-batch-form { grid-template-columns:minmax(0,1fr); }.pcb-dropzone { min-height:180px; } } @media(prefers-reduced-motion:reduce) { .pcb-dropzone { transition:none; } }
</style>

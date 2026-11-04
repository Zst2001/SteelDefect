<template>
  <div class="pcb-scope pcb-batch-result">
    <PcbTabs />
    <header class="pcb-head"><div><p class="pcb-eyebrow">PCB / 批次结果</p><h1>PCB 分割对照结果</h1><p class="pcb-code">批次 {{ batchId }}</p></div><div class="pcb-actions"><router-link to="/inspect/pcb">新建批量分割</router-link><router-link to="/records?type=pcb_segmentation">历史记录</router-link></div></header>
    <div v-if="loading && !batch" class="pcb-state" role="status">正在读取批次…</div>
    <div v-if="error" class="pcb-state error" role="alert"><p>{{ error }}</p><el-button @click="refresh">重新加载批次</el-button></div>
    <template v-if="batch && !error">
      <section class="pcb-panel pcb-batch-summary" aria-label="批次进度">
        <div><h2>{{ statusLabel }}</h2><p class="pcb-muted">{{ batch.samples.length }} 张图片 · 各模型独立执行，结果自动更新</p></div>
        <dl><div v-for="item in countItems" :key="item.key"><dt>{{ item.label }}</dt><dd>{{ batch.counts[item.key] }}</dd></div></dl>
        <p v-if="batch.counts.failed" class="pcb-note">失败项可单独再跑，已成功的结果仍可查看和下载。</p>
      </section>

      <section class="pcb-panel pcb-viewer" aria-label="PCB 分割图层查看器">
        <div class="pcb-viewer-toolbar">
          <div class="pcb-view-tabs" role="tablist" aria-label="对比图层">
            <button v-for="option in layerOptions" :key="option.kind" type="button" role="tab" :aria-selected="layer === option.kind" :disabled="!currentSample || (option.kind === 'error' && !currentSample.has_gt)" @click="selectLayer(option.kind)">{{ option.label }}</button>
          </div>
          <div class="pcb-sample-nav">
            <select v-if="batch.samples.length" :value="sampleId" aria-label="选择对比图片" @change="selectSample(($event.target as HTMLSelectElement).value)"><option v-for="(sample,index) in batch.samples" :key="sample.sample_id" :value="sample.sample_id">{{ index + 1 }}. {{ sample.filename }}</option></select>
            <span class="pcb-sample-counter">{{ currentSample ? sampleIndex + 1 : 0 }} / {{ batch.samples.length }}</span>
            <el-button :icon="ArrowLeft" :disabled="sampleIndex <= 0" aria-label="上一张" title="上一张" @click="stepSample(-1)" />
            <el-button :icon="ArrowRight" :disabled="sampleIndex < 0 || sampleIndex >= batch.samples.length - 1" aria-label="下一张" title="下一张" @click="stepSample(1)" />
          </div>
        </div>
        <template v-if="currentSample">
          <div class="pcb-image-heading"><strong>原图、GT 与模型输出</strong><span>{{ currentSample.filename }} · {{ currentSample.width }} × {{ currentSample.height }}</span></div>
          <div class="pcb-montage-scroll" tabindex="0" aria-label="当前图片横向模型对比">
            <div class="pcb-comparison-grid" :style="{'--pcb-columns': tiles.length}">
              <article v-for="tile in tiles" :key="tile.key" class="pcb-comparison-tile" :class="tile.reference ? 'pcb-reference-card' : 'pcb-child-card'">
                <div class="pcb-tile-heading"><strong :title="tile.title">{{ tile.title }}</strong><TaskStatus v-if="!tile.reference && tile.task" :status="tile.task.status" /></div>
                <button v-if="tile.artifact && !failedImages[tile.artifact.url]" type="button" class="pcb-frame pcb-comparison-frame" :aria-label="'放大 ' + tile.title + ' · ' + currentSample.filename" @click="openZoom(tile)">
                  <img :src="tile.artifact.url" :alt="currentSample.filename + ' · ' + tile.title + ' · ' + tile.kind" :class="{'pcb-mask':tile.kind === 'gt' || tile.kind === 'pred_mask'}" @error="failedImages[tile.artifact!.url] = true" />
                </button>
                <div v-else class="pcb-frame pcb-comparison-frame pcb-layer-empty" :role="tile.task?.status === 'failed' ? 'alert' : 'status'"><p>{{ tileMessage(tile) }}</p></div>
                <div class="pcb-tile-actions">
                  <button v-if="tile.artifact && tile.task" class="pcb-layer-download" type="button" :disabled="!!downloading" @click="download(tile.task,tile.kind)">{{ downloading === tile.task.id + tile.kind ? '正在下载…' : tile.reference ? '下载' + tile.title : '下载此图层（原尺寸）' }}</button>
                  <template v-if="!tile.reference && tile.task">
                    <button v-if="layer === 'mask_visual' && artifact(tile.task,'pred_mask')" type="button" class="pcb-text-action" :disabled="!!downloading" @click="download(tile.task,'pred_mask')">原始 0/1 掩码</button>
                    <el-button v-if="tile.task.status === 'failed'" :loading="retrying === tile.task.id" :disabled="!!retrying" @click="rerun(tile.task)">仅再跑此项</el-button>
                    <router-link :to="'/inspect/pcb/tasks/' + encodeURIComponent(tile.task.id)">打开独立详情 →</router-link>
                    <small class="pcb-code" :title="tile.task.id">任务 {{ tile.task.id.slice(0,8) }}</small>
                  </template>
                </div>
              </article>
            </div>
          </div>
          <div class="pcb-viewer-footer">
            <div v-if="layer === 'error'" class="pcb-layer-legend"><span><i style="background:#28b446"></i>TP 命中</span><span><i style="background:#dc2828"></i>FP 误检</span><span><i style="background:#285adc"></i>FN 漏检</span></div>
            <span v-else-if="layer === 'probability'" class="pcb-muted">缺陷概率热力图：紫色低、黄色高，不是 Grad-CAM 或精度。</span>
            <span v-else-if="layer === 'cam'" class="pcb-muted">Grad-CAM 表示模型关注区域，仅原生 220 × 220 RGB 支持。</span>
            <span v-else class="pcb-muted">GT / 掩码中白色为缺陷、黑色为背景；GT 始终为配对标注。</span>
            <button type="button" class="pcb-text-action" @click="retryImages">重新加载图层</button>
          </div>
          <p class="pcb-preview-hint">点击图像放大，下载保留原始尺寸。窄屏可在对比区横向滚动；仅加载当前图片的图层。</p>
        </template>
        <div v-else class="pcb-state">{{ batch.status === 'uploaded' ? '图片已上传，尚未建立子任务，请从工作台完成提交。' : '暂无获授权的图片结果。' }}</div>
      </section>

      <section v-if="currentSample" class="pcb-panel pcb-metrics-panel">
        <div class="pcb-panel-head"><div><h2>当前图片参考指标</h2><p>{{ currentSample.has_gt ? '根据本张配对 GT 在原图尺寸上计算，不代表完整数据集性能。' : '未配对 GT，仅展示分割结果，不计算 Dice、IoU 等指标。' }}</p></div><span class="pcb-pill">{{ currentSample.tasks.length }} 项结果</span></div>
        <div v-if="currentSample.has_gt" class="pcb-table-scroll">
          <table class="pcb-metrics-table"><thead><tr><th>模型 / 任务</th><th>状态</th><th>Dice</th><th>IoU</th><th>Precision</th><th>Recall</th></tr></thead><tbody><tr v-for="task in currentTasks" :key="task.id" class="pcb-child-metrics"><td><strong>{{ task.model?.name || '模型信息暂不可用' }}</strong><router-link class="pcb-code" :to="'/inspect/pcb/tasks/' + encodeURIComponent(task.id)">{{ task.id.slice(0,8) }}</router-link></td><td><TaskStatus :status="task.status" /></td><td v-for="key in metricKeys" :key="key">{{ task.status === 'success' && task.has_gt && task.metrics?.available ? percent(task.metrics[key]) : '—' }}</td></tr></tbody></table>
          <p class="pcb-muted">“—”表示未完成、不可用或无定义；各任务独立计算，重跑结果不会覆盖原任务。</p>
        </div>
      </section>
      <p v-if="actionError" class="pcb-error" role="alert">{{ actionError }}</p>
      <p class="pcb-muted pcb-batch-explainer">{{ PCB_CANCEL_NOTICE }}。仅显示当前获授权的结果，历史任务可从独立详情查看。</p>
    </template>
    <el-dialog :model-value="!!zoom" :title="zoom?.title || '图层预览'" width="min(1080px, 94vw)" destroy-on-close @update:model-value="zoom = null"><img v-if="zoom" class="pcb-zoom-image" :class="{'pcb-mask':zoom.kind === 'gt' || zoom.kind === 'pred_mask'}" :src="zoom.url" :alt="zoom.title" /><p class="pcb-muted">页面按比例显示；授权下载保留原始像素。</p></el-dialog>
  </div>
</template>
<script setup lang="ts">
import {computed,onBeforeUnmount,reactive,ref,watch} from 'vue';
import {useRoute} from 'vue-router';
import {ArrowLeft,ArrowRight} from '@element-plus/icons-vue';
import {http,formatError} from '../../api/http';
import {downloadAuthFile} from '../../api/labels';
import TaskStatus from '../../components/TaskStatus.vue';
import PcbTabs from './PcbTabs.vue';
import {PCB_CANCEL_NOTICE,PCB_MODELS,type PcbBatch,type PcbBatchSample,type PcbTask,type PcbArtifact,type PcbArtifactKind} from './types';
import './pcb.css';
type Tile={key:string;title:string;kind:PcbArtifactKind;reference:boolean;task?:PcbTask;artifact?:PcbArtifact};
const route=useRoute(),batchId=computed(()=>String(route.params.batchId||'')),batch=ref<PcbBatch|null>(null),loading=ref(false),error=ref(''),actionError=ref(''),retrying=ref(''),downloading=ref('');
const sampleId=ref(''),layer=ref<PcbArtifactKind>('mask_visual'),failedImages=reactive<Record<string,boolean>>({}),zoom=ref<{title:string;url:string;kind:PcbArtifactKind}|null>(null);
let disposed=false,generation=0,retryToken=0,downloadToken=0,timer:ReturnType<typeof setTimeout>|undefined,controller:AbortController|undefined;
const countItems=[{key:'total',label:'子任务'},{key:'success',label:'成功'},{key:'running',label:'运行中'},{key:'queued',label:'排队'},{key:'failed',label:'失败'}] as const;
const metricKeys=['defect_dice','iou','precision','recall'] as const;
const statuses:Record<string,string>={uploaded:'已上传，等待提交',queued:'批次已排队',running:'正在分割',success:'全部完成',partial_failed:'部分任务失败',failed:'批次任务失败'};
const statusLabel=computed(()=>statuses[batch.value?.status||'']||'批次状态待核验');
const layerOptions: {kind:PcbArtifactKind;label:string}[]=[{kind:'mask_visual',label:'掩码拼图'},{kind:'overlay',label:'叠加拼图'},{kind:'probability',label:'概率热力图'},{kind:'cam',label:'Grad-CAM'},{kind:'boundary',label:'边界拼图'},{kind:'error',label:'错误图拼图'}];
const sampleIndex=computed(()=>batch.value?.samples.findIndex(s=>s.sample_id===sampleId.value)??-1);
const currentSample=computed(()=>batch.value?.samples[sampleIndex.value]);
const currentTasks=computed(()=>[...(currentSample.value?.tasks||[])].sort((a,b)=>PCB_MODELS.indexOf(a.model?.id as typeof PCB_MODELS[number])-PCB_MODELS.indexOf(b.model?.id as typeof PCB_MODELS[number])));
function artifact(task:PcbTask|undefined,kind:PcbArtifactKind){return task?.status==='success'&&Array.isArray(task.artifacts)?task.artifacts.find(a=>a.kind===kind&&a.url.startsWith('/api/tasks/'+encodeURIComponent(task.id)+'/file/')&&!a.url.includes('..')):undefined;}
const tiles=computed<Tile[]>(()=>{
  if(!currentSample.value)return [];
  const refs=(['origin','gt'] as const).map(kind=>{const task=currentTasks.value.find(t=>(kind!=='gt'||t.has_gt)&&artifact(t,kind));return {key:kind,title:kind==='origin'?'原图':'GT',kind,reference:true,task,artifact:artifact(task,kind)};});
  return [...refs,...currentTasks.value.map(task=>({key:task.id,title:task.model?.name||'模型信息暂不可用',kind:layer.value,reference:false,task,artifact:artifact(task,layer.value)}))];
});
function percent(value:number|null|undefined){return typeof value==='number'&&Number.isFinite(value)?(value*100).toFixed(2)+'%':'—';}
function camReason(task:PcbTask){return task.cam?.reason||(task.cam?.status==='not_supported_for_size'?'仅原生 220 × 220 RGB 图片支持 CAM，本项仍可查看分割与概率图层。':task.cam?.status==='not_requested'?'本项未请求 Grad-CAM。':'本项 Grad-CAM 不可用，基础分割结果保留。');}
function tileMessage(tile:Tile){if(tile.artifact&&failedImages[tile.artifact.url])return '图层加载失败，可点击下方“重新加载图层”重试。';if(tile.reference)return tile.kind==='gt'&&!currentSample.value?.has_gt?'未配对 GT，不计算指标。':'结果生成后可查看'+tile.title+'。';const task=tile.task!;if(task.status!=='success')return task.error_summary||(task.status==='failed'?'本项执行失败，可单独再跑。':task.status==='running'?'CPU 正在处理此图像…':'等待队列执行…');return tile.kind==='cam'?camReason(task):'此图层暂不可用，请打开独立详情核查。';}
function selectLayer(kind:PcbArtifactKind){layer.value=kind;zoom.value=null;}
function selectSample(id:string){sampleId.value=id;zoom.value=null;}
function stepSample(delta:number){const next=batch.value?.samples[sampleIndex.value+delta];if(next)selectSample(next.sample_id);}
watch(currentSample,s=>{if(layer.value==='error'&&!s?.has_gt)layer.value='mask_visual';});
function openZoom(tile:Tile){if(tile.artifact)zoom.value={title:currentSample.value!.filename+' · '+tile.title,url:tile.artifact.url,kind:tile.kind};}
function retryImages(){for(const key of Object.keys(failedImages))delete failedImages[key];void refresh();}
function stop(){if(timer)clearTimeout(timer);timer=undefined;}
function validBatch(data:PcbBatch,id:string){if(data.batch_id!==id||!Array.isArray(data.samples)||!data.counts||data.samples.some(s=>!s.sample_id||!Array.isArray(s.tasks)||s.tasks.some(t=>t.type!=='pcb_segmentation'||t.scene!=='pcb')))throw new Error('批次返回数据不符合 PCB 分割契约');}
async function refresh(){
  if(disposed||loading.value)return;stop();const current=generation,id=batchId.value;loading.value=true;error.value='';const abort=new AbortController();controller=abort;
  try {
    const getPage=async(page:number)=>{const {data}=await http.get<PcbBatch>('/scenes/pcb/segmentation/batches/'+encodeURIComponent(id),{params:{page,page_size:100},signal:abort.signal});validBatch(data,id);return data;};
    const first=await getPage(1),merged=new Map<string,PcbBatchSample>();
    const merge=(data:PcbBatch)=>{for(const sample of data.samples){const prior=merged.get(sample.sample_id);if(!prior)merged.set(sample.sample_id,{...sample,tasks:[...sample.tasks]});else{const ids=new Set(prior.tasks.map(t=>t.id));for(const task of sample.tasks)if(!ids.has(task.id)){prior.tasks.push(task);ids.add(task.id);}}}};
    merge(first);let part=first;
    const total=first.pagination?.total??first.counts.total;
    if(!Number.isSafeInteger(total)||total<0)throw new Error('批次任务数量无效');
    for(let page=2;part.pagination?.has_more&&page<=Math.ceil(total/100);page++){part=await getPage(page);merge(part);}
    if(disposed||current!==generation)return;
    batch.value={...first,samples:[...merged.values()]};
    if(!batch.value.samples.some(s=>s.sample_id===sampleId.value))sampleId.value=batch.value.samples[0]?.sample_id||'';
    if(zoom.value&&!tiles.value.some(t=>t.artifact?.url===zoom.value!.url))zoom.value=null;
    if(first.counts.queued||first.counts.running)timer=setTimeout(()=>void refresh(),2500);
  }catch(err){if(!disposed&&current===generation){error.value=formatError(err);batch.value=null;zoom.value=null;}}
  finally{if(!disposed&&current===generation)loading.value=false;}
}
async function rerun(task:PcbTask){if(retrying.value)return;const current=generation,token=++retryToken;retrying.value=task.id;actionError.value='';try{await http.post('/records/'+encodeURIComponent(task.id)+'/rerun');if(!disposed&&current===generation&&token===retryToken){controller?.abort();generation++;loading.value=false;await refresh();}}catch(err){if(!disposed&&token===retryToken)actionError.value=formatError(err);}finally{if(!disposed&&token===retryToken)retrying.value='';}}
async function download(task:PcbTask,kind:PcbArtifactKind){const item=artifact(task,kind);if(!item||downloading.value)return;const token=++downloadToken;downloading.value=task.id+kind;actionError.value='';try{await downloadAuthFile(item.url.replace(/^\/api/,''),task.id+'_'+kind+'.png');}catch(err){if(!disposed&&token===downloadToken)actionError.value=formatError(err);}finally{if(!disposed&&token===downloadToken)downloading.value='';}}
watch(batchId,()=>{generation++;retryToken++;downloadToken++;controller?.abort();stop();batch.value=null;sampleId.value='';loading.value=false;error.value='';actionError.value='';retrying.value='';downloading.value='';zoom.value=null;layer.value='mask_visual';for(const key of Object.keys(failedImages))delete failedImages[key];void refresh();},{immediate:true});
onBeforeUnmount(()=>{disposed=true;generation++;retryToken++;downloadToken++;controller?.abort();stop();});
</script>
<style scoped>
.pcb-batch-summary { display:flex;align-items:center;flex-wrap:wrap;gap:20px 40px;margin-bottom:22px; }
.pcb-batch-summary h2,.pcb-metrics-panel h2 { color:#365d86;font-size:20px; }.pcb-batch-summary p { margin:7px 0 0; }.pcb-batch-summary dl { display:flex;flex:1;justify-content:flex-end;gap:clamp(18px,3vw,48px);margin:0; }.pcb-batch-summary dt { color:#5b7390;font-size:13px; }.pcb-batch-summary dd { margin:6px 0 0;font:600 25px var(--lab-font-mono);color:#294e78; }.pcb-batch-summary .pcb-note { flex-basis:100%;margin:0; }
.pcb-viewer { padding:0;overflow:hidden;margin-bottom:22px; }.pcb-viewer-toolbar { display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap;padding:18px 20px;border-bottom:1px solid var(--pcb-line); }.pcb-view-tabs { display:flex;flex-wrap:wrap;gap:6px; }.pcb-view-tabs button { padding:9px 12px;border:1px solid #dce5f1;border-radius:5px;background:#fff;font:600 14px var(--lab-font-sans, sans-serif);color:#59718d;cursor:pointer; }.pcb-view-tabs button[aria-selected=true] { background:#edf4ff;border-color:#9cbde8;color:#255b9c; }.pcb-view-tabs button:disabled { color:#8a99aa;background:#f7f9fc;cursor:not-allowed; }.pcb-view-tabs button:not(:disabled):hover { border-color:#729bd0;color:#234c7a; }
.pcb-sample-nav { display:flex;align-items:center;gap:8px;min-width:0; }.pcb-sample-nav select { width:210px;max-width:100%;padding:9px 10px;border:1px solid #d3dfec;border-radius:5px;background:#fff;color:#355778;font:14px var(--lab-font-sans, sans-serif);text-overflow:ellipsis; }.pcb-sample-counter { font-size:13px;color:#617690;white-space:nowrap; }.pcb-sample-nav .el-button { width:34px;padding:0;margin:0;color:#294e78;border-color:#c4d3e5;background:#f5f8fc; }.pcb-sample-nav .el-button:disabled { color:#7386a0;background:#eef2f7;border-color:#d7e0eb; }.pcb-sample-nav :deep(.el-icon) { font-size:18px; }.pcb-sample-nav .el-button:not(:disabled):hover { color:#173a63;border-color:#8aa8cc;background:#e8f1ff; }
.pcb-image-heading { display:flex;justify-content:space-between;gap:14px;flex-wrap:wrap;padding:20px 20px 13px;font-size:14px; }.pcb-image-heading strong { color:#365778; }.pcb-image-heading>span { color:#6b8198;overflow-wrap:anywhere; }.pcb-montage-scroll { margin:0 20px;overflow-x:auto;overscroll-behavior-x:contain; }.pcb-comparison-grid { display:grid;grid-template-columns:repeat(var(--pcb-columns),minmax(160px,1fr));gap:10px;padding:12px;background:#f3f6fa;border:1px solid #e1e8f1;border-radius:7px; }.pcb-comparison-tile { min-width:0; }.pcb-tile-heading { display:flex;align-items:flex-start;flex-direction:column;gap:5px;height:76px;box-sizing:border-box;padding:3px 2px 8px; }.pcb-tile-heading strong { color:#294967;font-size:14px;line-height:1.5;overflow-wrap:anywhere;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden; }.pcb-comparison-frame { width:100%;height:clamp(180px,19vw,320px);padding:0;border-radius:4px;cursor:zoom-in;background:#182433;border:1px solid #c9d6e6; }.pcb-comparison-frame img { width:100%;height:100%;object-fit:contain; }.pcb-layer-empty { cursor:default;background:#eaf0f6;padding:14px;box-sizing:border-box;overflow-y:auto; }.pcb-layer-empty p { font-size:13px;line-height:1.8;color:#516983;margin:0;overflow-wrap:anywhere; }.pcb-tile-actions { display:flex;align-items:flex-start;flex-direction:column;gap:10px;padding:12px 2px 4px; }.pcb-tile-actions a,.pcb-text-action { color:#315e96;font-size:13px; }.pcb-tile-actions .pcb-code { color:#6a7f95; }.pcb-layer-download { padding:7px 9px;font-size:12px;color:#315f99;border:1px solid #cad9ea;border-radius:4px;background:#fff;cursor:pointer; }.pcb-layer-download:disabled { opacity:.5;cursor:wait; }.pcb-text-action { padding:0;background:none;border:0;cursor:pointer;text-align:left; }.pcb-viewer-footer { margin:18px 20px 0;padding:13px 15px;border:1px solid #e1e8f2;border-radius:6px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px; }.pcb-layer-legend { display:flex;flex-wrap:wrap;gap:15px;font-size:13px;color:#4a6483; }.pcb-layer-legend span { display:flex;align-items:center;gap:6px; }.pcb-layer-legend i { width:10px;height:10px;border-radius:2px; }.pcb-preview-hint { color:#74879b;font-size:12px;line-height:1.8;padding:0 20px;margin:12px 0 18px; }
.pcb-table-scroll { overflow-x:auto; }.pcb-metrics-table { width:100%;border-collapse:collapse;min-width:630px;text-align:left;font-size:14px; }.pcb-metrics-table th { color:#486486;background:#f3f6fb;font-weight:600; }.pcb-metrics-table td,.pcb-metrics-table th { padding:15px 12px;border-bottom:1px solid #e5ecf4; }.pcb-metrics-table td { color:#3f6083;font-variant-numeric:tabular-nums; }.pcb-metrics-table td:first-child strong { display:block;font-size:14px;font-weight:500; }.pcb-metrics-table td:first-child a { display:inline-block;margin-top:5px; }.pcb-batch-explainer { margin:18px 0;font-size:12px; }.pcb-zoom-image { display:block;width:100%;max-height:70vh;object-fit:contain;background:#182433; }
@media(max-width:650px) { .pcb-batch-summary { padding:20px 16px;gap:20px; }.pcb-batch-summary dl { flex-basis:100%;justify-content:space-between;gap:10px; }.pcb-batch-summary dd { font-size:22px; }.pcb-viewer-toolbar { padding:15px;gap:15px; }.pcb-sample-nav { width:100%; }.pcb-sample-nav select { flex:1;min-width:0;width:0; }.pcb-view-tabs button { padding:8px 10px;font-size:13px; }.pcb-image-heading { padding:17px 15px 12px; }.pcb-montage-scroll { margin:0 15px; }.pcb-comparison-grid { grid-template-columns:repeat(var(--pcb-columns),minmax(185px,1fr)); }.pcb-comparison-frame { height:220px; }.pcb-viewer-footer { margin:15px 15px 0; }.pcb-preview-hint { padding:0 15px; } }
</style>

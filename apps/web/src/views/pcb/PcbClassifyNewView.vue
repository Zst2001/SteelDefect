<template>
  <div class="pcb-scope pcb-classify">
    <PcbTabs classification />
    <header class="pcb-head roi-head">
      <div><p class="pcb-eyebrow">PCB / 单缺陷 ROI 六分类</p><h1>PCB 缺陷分类工作台</h1></div>
      <div class="roi-guide" aria-label="操作流程"><ol><li>上传图像</li><li>选择模型</li><li>查看分类</li></ol><p>选择以单个缺陷为主的局部图像，可同时使用多个模型</p></div>
    </header>
    <div v-if="loading" class="pcb-state" role="status">正在检查分类模型准入…</div>
    <div v-else-if="catalogError" class="pcb-state error" role="alert"><strong>模型目录读取失败</strong><p>{{ catalogError }}</p><el-button @click="loadCatalog">重试目录</el-button></div>
    <div v-else-if="!ready" class="pcb-state" role="status"><strong>PCB 分类暂未启用</strong><p>两模型须通过本机 CPU 准入，并由管理员开启分类功能。已有结果仍可查看。</p><el-button @click="loadCatalog">重新检查状态</el-button></div>
    <div class="roi-grid">
      <section class="pcb-panel roi-images-panel">
        <div class="pcb-panel-head"><div><h2>上传 PCB 图像</h2><p>无需固定尺寸或灰度格式，系统自动适配分类输入。</p></div><span class="pcb-pill">{{ file ? 1 : 0 }} / 1 张</span></div>
        <button type="button" class="roi-dropzone" :class="{ dragging }" :disabled="!ready || busy" aria-label="上传 PCB 图像" @click="input?.click()" @dragover.prevent="dragging = ready && !busy" @dragleave.prevent="dragging = false" @drop.prevent.stop="dropImage">
          <img v-if="preview" :src="preview" alt="待分类 ROI 预览" />
          <el-icon v-else><UploadFilled /></el-icon>
          <strong>{{ file ? '点击此区域更换 PCB 图像' : '点击此区域选择 PCB 图像' }}</strong>
          <span>{{ file && !preview ? '已选择 TIFF，浏览器暂不提供预览' : '也可以将图片拖到这里' }}</span>
          <small>PNG / JPG / WebP / BMP / TIFF / GIF · 单张静态图 · 最多 {{ mib(maxBytes) }}</small>
        </button>
        <input ref="input" class="pcb-file-input" type="file" accept="image/*,.png,.jpg,.jpeg,.webp,.bmp,.tif,.tiff,.gif" aria-label="PCB 分类 ROI" :disabled="!ready || busy" @change="choose" />
        <div v-if="file || imageError" class="roi-file-row"><div><strong class="roi-filename">{{ file?.name || '未选择有效图像' }}</strong><span v-if="file">{{ size || '尺寸由服务端检查' }} · {{ mib(file.size) }}</span></div><el-button :disabled="submitting" @click="clearImage">移除图像</el-button></div>
        <p v-if="validating" role="status" class="pcb-muted">正在检查图片…</p><p v-if="imageError" class="pcb-error" role="alert">{{ imageError }}</p>
        <p v-if="file && !preview" role="status" class="pcb-muted">提交时会检查 TIFF 内容，动画、多页或损坏文件会给出具体提示。</p>
        <p class="pcb-muted roi-upload-hint">支持彩色与灰度图片。建议上传已裁剪的单缺陷局部图像；尺寸和文件内容由服务端再次检查。</p>
      </section>
      <section class="pcb-panel roi-models-panel">
        <div class="pcb-panel-head"><div><h2>选择分类模型</h2><p>每个选中的模型独立执行，可分别查看结果。</p></div><span class="pcb-pill">已选 {{ selected.length }} / {{ models.length }}</span></div>
        <div class="pcb-actions roi-select-actions"><el-button :disabled="!ready || busy" @click="selectAll">全选全部模型</el-button><el-button :disabled="busy || !selected.length" @click="selected = []">取消全选</el-button></div>
        <div class="roi-models" role="group" aria-label="PCB 分类模型">
          <label v-for="model in models" :key="model.model_id" class="roi-model-card" :class="{selected:selected.includes(model.model_id), unavailable:!ready || !model.available}"><input v-model="selected" type="checkbox" :value="model.model_id" :disabled="!ready || !model.available || busy" /><span><strong>{{ model.name }}</strong><small>参数量 {{ formatParamCount(model.params) }} · CPU 推理</small></span><em>{{ model.default ? '默认' : '轻量备选' }}</em></label>
        </div>
        <p class="pcb-muted roi-model-hint">两个模型采用同一六类标签，分类结果与置信度分别记录。</p>
      </section>
      <section class="pcb-panel roi-scope-panel">
        <div class="pcb-panel-head"><div><h2>分类范围</h2><p>识别以下六类 PCB 缺陷</p></div></div>
        <div class="roi-classes" aria-label="六类缺陷"><span v-for="label in catalog?.classes || []" :key="label.class_id">{{ label.label_zh }}<small>{{ label.label_en }}</small></span></div>
        <p class="pcb-muted">模型面向单缺陷局部图像，不包含正常类，也不提供整板定位或自动裁框。置信度表示六类倾向，不是准确率。</p>
        <p class="pcb-muted">原生 224 × 224 灰度 PNG 保留像素；其他支持的图片按既有协议转换。格式适配不代表模型适用于任意场景。</p>
      </section>
      <section class="pcb-panel roi-summary">
        <div class="pcb-panel-head"><div><h2>提交摘要</h2><p>同一张图像只上传一次，各模型独立创建任务。</p></div></div>
        <p class="roi-equation"><strong>{{ file ? 1 : 0 }}</strong> 张图像 × <strong>{{ selected.length }}</strong> 个模型 = <strong>{{ file ? selected.length : 0 }}</strong> 个任务</p>
        <p v-if="uploadNotice" class="pcb-muted roi-adaptation" role="status">{{ uploadNotice }}</p>
        <p v-if="submitError" class="pcb-error" role="alert">{{ submitError }}</p><p v-if="batch && submitError" class="pcb-muted">图片已上传。重试仅提交尚未确认的模型，已创建的任务不会重复提交。</p>
        <el-button class="roi-submit" type="primary" :disabled="!canSubmit" :loading="submitting" @click="submit">{{ submitting ? stage : '开始 PCB 分类' }}</el-button>
        <p v-if="allSelectedSubmitted" role="status" class="pcb-muted">所选模型均已提交，可从下方打开结果。更换图像可开始新的分类。</p>
        <div v-if="submissionRows.length" class="roi-submission-results" aria-label="已提交分类任务">
          <div v-for="row in submissionRows" :key="row.id" class="roi-submission-row" :data-model-id="row.modelId"><div><strong>{{ row.name }}</strong><span>{{ submittedStatus(row.status) }} · 提交时状态</span></div><router-link :to="'/inspect/pcb/classification/tasks/' + encodeURIComponent(row.id)">查看结果 →</router-link></div>
        </div>
        <p class="pcb-muted">CPU 按队列执行。关闭页面不会取消任务，结果可在历史记录中查看或提交导师。</p><router-link to="/records?type=pcb_classify">查看 PCB 分类历史 →</router-link>
      </section>
    </div>
  </div>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { UploadFilled } from "@element-plus/icons-vue";
import { formatError, http } from "../../api/http";
import { formatParamCount } from "../../api/labels";
import PcbTabs from "./PcbTabs.vue";
import type { RoiCatalog } from "./classification-types";
import "./pcb.css";

type Submission = {id:string; modelId:string; name:string; status:string};
const router = useRouter(), catalog = ref<RoiCatalog | null>(null), loading = ref(true), catalogError = ref("");
const file = ref<File | null>(null), preview = ref(""), input = ref<HTMLInputElement | null>(null), size = ref(""), imageError = ref("");
const selected = ref<string[]>([]), submitting = ref(false), validating = ref(false), dragging = ref(false), submitError = ref(""), stage = ref(""), batch = ref(""), uploadNotice = ref("");
const submitted = ref<Record<string,Submission>>({});
let disposed = false, revision = 0, request = 0;
// A response can be lost after a task is saved. Reuse each batch/model identity,
// including after selection A → B → A and partial multi-model submissions.
const requestKeys = new Map<string,string>();
const models = computed(() => catalog.value?.models || []);
const ready = computed(() => catalog.value?.enabled === true && catalog.value?.available === true && models.value.length === 2 && models.value.every(m => m.available));
const maxBytes = computed(() => catalog.value?.max_image_bytes || 10485760);
const maxPixels = computed(() => catalog.value?.max_pixels || 16777216);
const busy = computed(() => submitting.value || validating.value);
const selectedModels = computed(() => models.value.filter(m => selected.value.includes(m.model_id) && m.available));
const submissionRows = computed(() => models.value.map(m => submitted.value[m.model_id]).filter((row):row is Submission => !!row));
const pendingModels = computed(() => selectedModels.value.filter(m => !submitted.value[m.model_id]));
const allSelectedSubmitted = computed(() => selectedModels.value.length > 0 && pendingModels.value.length === 0);
const canSubmit = computed(() => ready.value && !loading.value && !catalogError.value && !!file.value && !imageError.value && !busy.value && pendingModels.value.length > 0);
watch(selected, () => { submitError.value = ""; }, {deep:true});
function mib(bytes:number) { return `${(bytes / 1048576).toFixed(1)} MiB`; }
function selectAll() { selected.value = models.value.filter(m => m.available).map(m => m.model_id); }
function submittedStatus(status:string) { return ({queued:'已排队',running:'运行中',success:'已完成',failed:'任务失败'} as Record<string,string>)[status] || '已创建'; }
function clearImage() {
  if (submitting.value) return;
  revision++;
  if (preview.value) URL.revokeObjectURL(preview.value);
  preview.value = ""; file.value = null; size.value = ""; batch.value = "";
  validating.value = false; imageError.value = ""; submitError.value = ""; uploadNotice.value = ""; submitted.value = {}; requestKeys.clear();
}
async function loadCatalog() {
  const current = ++request; loading.value = true; catalogError.value = "";
  try { const {data} = await http.get<RoiCatalog>("/scenes/pcb/classification/models"); if (!disposed && current === request) { catalog.value = data; selected.value = [data.default_model]; } }
  catch (err) { if (!disposed && current === request) catalogError.value = formatError(err); }
  finally { if (!disposed && current === request) loading.value = false; }
}
function contentFormat(bytes:Uint8Array) {
  const ascii = (start:number,end:number) => String.fromCharCode(...bytes.slice(start,end));
  if ([137,80,78,71,13,10,26,10].every((n,i) => bytes[i] === n)) return 'png';
  if (bytes[0] === 255 && bytes[1] === 216 && bytes[2] === 255) return 'jpeg';
  if (ascii(0,4) === 'RIFF' && ascii(8,12) === 'WEBP') return 'webp';
  if (ascii(0,2) === 'BM') return 'bmp';
  if (['GIF87a','GIF89a'].includes(ascii(0,6))) return 'gif';
  if ((bytes[0] === 73 && bytes[1] === 73 && [42,43].includes(bytes[2]) && bytes[3] === 0) || (bytes[0] === 77 && bytes[1] === 77 && bytes[2] === 0 && [42,43].includes(bytes[3]))) return 'tiff';
  return '';
}
async function choose(event:Event) {
  const element = event.target as HTMLInputElement, files = Array.from(element.files || []); element.value = "";
  if (files.length) await chooseFiles(files);
}
async function dropImage(event:DragEvent) {
  dragging.value = false;
  const files = Array.from(event.dataTransfer?.files || []);
  if (files.length) await chooseFiles(files);
}
async function chooseFiles(files:File[]) {
  if (!ready.value || busy.value) return;
  if (files.length !== 1) { imageError.value = '请一次选择一张单缺陷图像，可同时使用多个模型。'; return; }
  const chosen = files[0], current = ++revision; validating.value = true; imageError.value = ""; let url = "";
  try {
    if (!chosen.size || chosen.size > maxBytes.value) throw new Error(`请选择非空图片，单张不超过 ${mib(maxBytes.value)}。`);
    const format = contentFormat(new Uint8Array(await chosen.slice(0,16).arrayBuffer()));
    if (!format) throw new Error('无法识别图片内容，请选择 PNG、JPEG、WebP、BMP、TIFF 或静态 GIF。');
    let dimensions = '';
    // TIFF is decoded authoritatively on the server; browsers generally cannot
    // preview it. Other formats are previewed from their content MIME, not name.
    if (format !== 'tiff') {
      url = URL.createObjectURL(new Blob([chosen], {type:`image/${format}`}));
      const image = new Image(); image.src = url;
      try { await image.decode(); } catch { throw new Error('无法解码图片，请检查文件是否损坏或换一张图片。'); }
      if (image.naturalWidth * image.naturalHeight > maxPixels.value) throw new Error('图像像素过大，请缩小图片或裁剪缺陷区域后重试。');
      dimensions = `${image.naturalWidth} × ${image.naturalHeight}`;
    }
    if (disposed || current !== revision) return;
    if (preview.value) URL.revokeObjectURL(preview.value);
    preview.value = url; url = ""; file.value = chosen; size.value = dimensions;
    batch.value = ""; requestKeys.clear(); submitted.value = {}; submitError.value = ""; uploadNotice.value = "";
  } catch (err) { if (!disposed && current === revision) imageError.value = err instanceof Error ? err.message : "无法解码图像"; }
  finally { if (url) URL.revokeObjectURL(url); if (!disposed && current === revision) validating.value = false; }
}
async function submit() {
  if (!canSubmit.value || !file.value) return;
  const chosenModels = [...selectedModels.value], pending = [...pendingModels.value];
  submitting.value = true; submitError.value = ""; stage.value = "正在上传…";
  try {
    if (!batch.value) {
      const form = new FormData(); form.append("file", file.value);
      const {data} = await http.post("/scenes/pcb/classification/uploads", form);
      if (disposed) return;
      if (typeof data.batch_id !== 'string' || !data.batch_id) throw new Error('上传响应缺少批次标识，请重试。');
      batch.value = data.batch_id;
      uploadNotice.value = typeof data.source_image?.conversion_notice === 'string' ? data.source_image.conversion_notice : '';
    }
    const failures:string[] = [];
    for (const [index,model] of pending.entries()) {
      if (disposed) return;
      const identity = `${batch.value}\0${model.model_id}`;
      let idempotencyKey = requestKeys.get(identity);
      if (!idempotencyKey) { idempotencyKey = crypto.randomUUID(); requestKeys.set(identity,idempotencyKey); }
      stage.value = `正在提交 ${index + 1} / ${pending.length}…`;
      try {
        const {data} = await http.post("/scenes/pcb/classification/tasks", {batch_id:batch.value,model_id:model.model_id}, {headers:{"Idempotency-Key":idempotencyKey}});
        if (disposed) return;
        if (typeof data.id !== 'string' || !data.id || (data.model?.id && data.model.id !== model.model_id)) throw new Error('任务响应身份不一致，请重试确认。');
        submitted.value[model.model_id] = {id:data.id,modelId:model.model_id,name:model.name,status:typeof data.status === 'string' ? data.status : ''};
      } catch (err) { if (disposed) return; failures.push(`${model.name}：${formatError(err)}`); }
    }
    if (disposed) return;
    submitError.value = failures.join('；');
    if (!failures.length && chosenModels.length === 1) await router.push(`/inspect/pcb/classification/tasks/${encodeURIComponent(submitted.value[chosenModels[0].model_id].id)}`);
  } catch (err) { if (!disposed) submitError.value = formatError(err); }
  finally { if (!disposed) submitting.value = false; }
}
onMounted(loadCatalog);
onBeforeUnmount(() => { disposed = true; revision++; request++; if (preview.value) URL.revokeObjectURL(preview.value); });
</script>
<style scoped>
.roi-head { align-items:center; }.roi-guide { max-width:450px;padding-left:22px;border-left:2px solid #d9e6f5; }.roi-guide ol { display:flex;flex-wrap:wrap;gap:12px;list-style:none;margin:0 0 7px;padding:0;color:#365f8e;font-size:14px; }.roi-guide li+li:before { content:'→';margin-right:12px;color:#829bb8; }.roi-guide p { font-size:13px; }
.roi-grid { display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:22px;align-items:stretch; }.roi-grid>.pcb-panel h2 { color:#4a83bd; }.roi-dropzone { display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;width:100%;min-height:244px;padding:24px 16px;text-align:center;background:#f5f8fd;border:1.5px dashed #a9bfdc;border-radius:9px;cursor:pointer;color:#476483;font:inherit;transition:background .15s,border-color .15s; }.roi-dropzone:not(:disabled):hover,.roi-dropzone.dragging { background:#eaf2ff;border-color:#477fc7; }.roi-dropzone:disabled { opacity:.6;cursor:not-allowed; }.roi-dropzone .el-icon { font-size:38px;color:#4679b9; }.roi-dropzone strong { font-size:18px;color:#264e7a; }.roi-dropzone span { font-size:15px; }.roi-dropzone small { font-size:12px;line-height:1.8; }.roi-dropzone img { display:block;width:176px;height:176px;max-width:100%;object-fit:contain;border:1px solid #dbe5f1;border-radius:5px;background:#e9eef5; }.roi-file-row { display:flex;align-items:center;justify-content:space-between;gap:14px;margin-top:16px;padding:12px;background:#f7f9fc;border:1px solid #e4ebf4;border-radius:6px; }.roi-file-row>div { display:grid;gap:5px;min-width:0; }.roi-filename { color:#365979;font-size:14px;overflow-wrap:anywhere; }.roi-file-row span { font-size:12px;color:#617b95; }.roi-upload-hint { margin-bottom:0; }
.roi-select-actions { margin-bottom:15px; }.roi-models { display:grid;gap:12px; }.roi-model-card { display:flex;align-items:center;gap:12px;padding:20px 17px;border:1px solid #dce6f2;border-radius:8px;cursor:pointer; }.roi-model-card.selected { background:#f1f6ff;border-color:#86aee4; }.roi-model-card.unavailable { opacity:.6;cursor:not-allowed; }.roi-model-card input { accent-color:#2e6cc9;width:17px;height:17px;flex:none; }.roi-model-card>span { display:grid;gap:8px;flex:1;min-width:0; }.roi-model-card strong { color:#274767;font-size:18px;overflow-wrap:anywhere; }.roi-model-card small { color:#5b7491;font-size:13px; }.roi-model-card em { font-style:normal;font-size:12px;color:#547396;white-space:nowrap; }.roi-model-hint { margin-top:20px; }.roi-classes { display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:9px; }.roi-classes>span { padding:11px 12px;background:#f3f6fa;border:1px solid #e4ebf4;border-radius:6px;font-size:15px;color:#294967; }.roi-classes small { display:block;margin-top:4px;color:#58728c;font-size:12px; }.roi-scope-panel>.pcb-muted:last-child { margin-bottom:0; }
.roi-summary { display:flex;flex-direction:column;align-items:stretch; }.roi-equation { margin:0 0 20px;color:#526c88;font-size:15px;line-height:1.8; }.roi-equation strong { font-size:25px;color:#24528a;font-variant-numeric:tabular-nums; }.roi-submit { width:100%;min-height:44px; }.roi-submission-results { display:grid;gap:10px;margin-top:16px; }.roi-submission-row { display:flex;align-items:center;justify-content:space-between;gap:14px;padding:12px;border:1px solid #dce6f2;border-radius:6px;background:#f7faff; }.roi-submission-row>div { display:grid;gap:6px;min-width:0; }.roi-submission-row strong { font-size:14px;color:#365979;overflow-wrap:anywhere; }.roi-submission-row span { font-size:12px;color:#617b95; }.roi-submission-row a { white-space:nowrap;font-size:13px; }.roi-summary>a { font-size:14px; }
@media(max-width:1000px) { .roi-grid { grid-template-columns:minmax(0,1fr); }.roi-guide { width:100%;max-width:none;border:0;padding:0; }.roi-scope-panel { order:3; }.roi-summary { order:2; } }
@media(max-width:600px) { .pcb-panel-head { flex-wrap:wrap; }.roi-dropzone { min-height:230px; }.roi-model-card { padding:17px 12px;gap:10px; }.roi-model-card strong { font-size:16px; }.roi-model-card em { font-size:11px; }.roi-classes>span { padding:10px; } }
@media(prefers-reduced-motion:reduce) { .roi-dropzone { transition:none; } }
</style>

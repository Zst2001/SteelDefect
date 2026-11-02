<template>
  <div class="pcb-scope pcb-new">
    <PcbTabs />
    <header class="pcb-head"><div><p class="pcb-eyebrow">PCB / 表面缺陷分割</p><h1>PCB 表面缺陷分割工作台</h1><p>上传一张电路板图像，在原图坐标下查看缺陷区域与边界。</p></div><span class="pcb-pill">CPU · 单图推理</span></header>
    <p class="pcb-muted pcb-cancel-notice">{{ PCB_CANCEL_NOTICE }}。原系统尚无统一取消协议；关闭页面不会停止任务，结果可从历史记录查看。</p>
    <div v-if="loading" class="pcb-state" role="status">正在检查 PCB 模型与服务状态…</div>
    <div v-else-if="catalogError" class="pcb-state error" role="alert"><strong>PCB 模型目录暂不可用</strong><p>{{ catalogError }}</p><el-button @click="loadCatalog">重新加载目录</el-button></div>
    <template v-else-if="catalog">
      <div v-if="!ready" class="pcb-state" role="status"><strong>PCB 分割暂未启用</strong><p>{{ catalog.reason || '三个模型需要全部完成本机准入，并由管理员启用服务后才能提交。已有结果仍可从历史记录查看。' }}</p><div class="pcb-actions"><el-button @click="loadCatalog">重新检查状态</el-button><router-link to="/records?type=pcb_segmentation">查看 PCB 历史记录 →</router-link></div></div>
      <p v-else class="pcb-note">仅支持 <strong>220 × 220 RGB</strong> 原图。不提供 GT 也可完成分割；只有配对 GT 通过校验后才计算当前图像的指标。</p>
      <div class="pcb-new-grid">
        <section class="pcb-panel">
          <div class="pcb-panel-head"><div><h2>待分割图像</h2><p>PNG / JPEG，单张不超过 2 MiB</p></div><span class="pcb-pill">220 × 220</span></div>
          <div class="pcb-upload-preview pcb-frame" :class="{ populated: image }"><img v-if="image" :src="image.url" alt="待分割 PCB 原图" /><div v-else class="pcb-upload-placeholder"><el-icon><Picture /></el-icon><strong>选择 PCB 原图</strong><span>保留原始尺寸、颜色与像素位置</span></div></div>
          <div class="pcb-actions upload-actions"><el-button :disabled="!ready || submitting || validating.image" @click="imageInput?.click()">{{ image ? '更换原图' : '选择原图' }}</el-button><el-button v-if="image" text :disabled="submitting" @click="clear('image')">移除原图</el-button><span v-if="image" class="pcb-muted image-name">{{ image.file.name }}</span></div>
          <input ref="imageInput" class="pcb-file-input" type="file" accept=".png,.jpg,.jpeg" aria-label="PCB 原图" :disabled="!ready || submitting" @change="selectFile($event, 'image')" />
          <p v-if="validating.image" role="status" class="pcb-muted">正在检查图像尺寸…</p><p v-if="errors.image" class="pcb-error" role="alert">{{ errors.image }}</p>
          <p class="pcb-muted input-policy">不自动缩放或裁剪。灰度、透明通道和带旋转方向的图像不符合本次输入协议；颜色模式与 EXIF 由服务端再次校验。</p>
          <details class="pcb-advanced"><summary>高级选项 · 配对 GT 与解释图层</summary><div class="pcb-advanced-content">
            <el-checkbox v-model="withGT" :disabled="!ready || submitting">添加配对 GT</el-checkbox><p class="pcb-muted">可选。GT 必须为 220 × 220 单通道 PNG，只含 0/1 或 0/255；仅用于评价，不作为模型输入。</p>
            <div v-if="withGT" class="gt-upload"><div class="pcb-actions"><el-button :disabled="!ready || submitting || validating.gt" @click="gtInput?.click()">{{ gt ? '更换 GT' : '选择 GT' }}</el-button><el-button v-if="gt" text :disabled="submitting" @click="clear('gt')">移除 GT</el-button><span v-if="gt" class="pcb-muted image-name">{{ gt.file.name }}</span></div><img v-if="gt" :src="gt.url" class="gt-preview pcb-mask" alt="配对 GT 预览" /><input ref="gtInput" class="pcb-file-input" type="file" accept=".png" aria-label="PCB 配对 GT" :disabled="!ready || submitting" @change="selectFile($event, 'gt')" /><p v-if="errors.gt" class="pcb-error" role="alert">{{ errors.gt }}</p></div>
            <el-checkbox v-model="includeCam" :disabled="!ready || submitting">生成 Grad-CAM</el-checkbox><p class="pcb-muted">额外计算模型关注区域，耗时更长。无预测前景时可能不可用，不影响基础分割结果；它与缺陷概率图不同。</p>
          </div></details>
        </section>
        <div class="pcb-side-stack">
          <section class="pcb-panel"><div class="pcb-panel-head"><div><h2>选择分割模型</h2><p>每次运行一个模型，结果独立保存</p></div><span class="pcb-pill">二类输出</span></div>
            <div class="pcb-models" role="radiogroup" aria-label="PCB 分割模型"><label v-for="model in models" :key="model.slug" class="pcb-model" :class="{ selected: selected === model.slug, unavailable: !ready || !model.available }"><input v-model="selected" type="radio" name="pcb-model" :value="model.slug" :disabled="!ready || !model.available || submitting" /><span class="pcb-model-info"><strong>{{ model.name }}</strong><span>参数量 {{ formatParamCount(model.param_count) }}</span></span><span class="pcb-model-badge">{{ !model.available ? '未就绪' : model.slug === 'unet' ? '默认候选' : '内置模型' }}</span></label></div>
            <p class="pcb-muted model-note">background / defect · 三模型使用同一输入协议。离线实验成绩不代表当前图像的精度。</p>
          </section>
          <section class="pcb-panel pcb-submit"><div class="pcb-panel-head"><div><h2>运行分割</h2><p>输入与模型配置随任务保存</p></div></div><dl class="pcb-submit-summary"><div><dt>原图</dt><dd>{{ image ? '1 张' : '尚未选择' }}</dd></div><div><dt>配对 GT</dt><dd>{{ withGT ? gt ? '已选择' : '等待选择' : '未提供' }}</dd></div><div><dt>Grad-CAM</dt><dd>{{ includeCam ? '按需生成' : '不生成' }}</dd></div></dl>
            <p v-if="submitError" class="pcb-error" role="alert">{{ submitError }}</p><p v-if="uploadedBatch && submitError" class="pcb-muted">原图批次已保存，重试将沿用该批次。</p>
            <el-button type="primary" :disabled="!canSubmit" :loading="submitting" @click="submit">{{ submitting ? submitStage : '开始 PCB 分割' }}</el-button><p v-if="!canSubmit && !submitting" class="pcb-muted submit-hint">{{ !ready ? '服务未启用，暂不可提交。' : !image ? '请选择一张符合协议的原图。' : withGT && !gt ? '请选择配对 GT，或关闭 GT 选项。' : '请检查图像与模型选择。' }}</p><router-link to="/records?type=pcb_segmentation">查看 PCB 历史记录 →</router-link>
          </section>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { Picture } from "@element-plus/icons-vue";
import { formatError, http } from "../../api/http";
import { formatParamCount } from "../../api/labels";
import { PCB_CANCEL_NOTICE, PCB_MODELS, type PcbCatalog } from "./types";
import "./pcb.css";
import PcbTabs from "./PcbTabs.vue";
type ImageChoice = { file: File; url: string };
const router = useRouter(), catalog = ref<PcbCatalog | null>(null), loading = ref(true), catalogError = ref("");
const image = ref<ImageChoice | null>(null), gt = ref<ImageChoice | null>(null), withGT = ref(false), includeCam = ref(false), selected = ref("unet");
const imageInput = ref<HTMLInputElement | null>(null), gtInput = ref<HTMLInputElement | null>(null);
const errors = reactive({ image: "", gt: "" }), validating = reactive({ image: false, gt: false });
const submitting = ref(false), submitError = ref(""), submitStage = ref(""), uploadedBatch = ref<string | null>(null);
let disposed = false, catalogRequest = 0;
const revisions = { image: 0, gt: 0 };
const models = computed(() => (catalog.value?.models ?? []).map(m => ({ ...m, slug: m.slug || m.id || "" })).filter(m => PCB_MODELS.includes(m.slug as typeof PCB_MODELS[number])));
const ready = computed(() => catalog.value?.enabled === true && catalog.value?.available === true && models.value.length === 3 && PCB_MODELS.every(id => models.value.some(m => m.slug === id && m.available)));
const canSubmit = computed(() => ready.value && !loading.value && !catalogError.value && !submitting.value && !validating.image && !validating.gt && !!image.value && !errors.image && (!withGT.value || (!!gt.value && !errors.gt)) && models.value.some(m => m.slug === selected.value && m.available));
function invalidateBatch() { uploadedBatch.value = null; submitError.value = ""; }
function clear(kind: "image" | "gt") { revisions[kind]++; validating[kind] = false; const field = kind === "image" ? image : gt; if (field.value) URL.revokeObjectURL(field.value.url); field.value = null; errors[kind] = ""; invalidateBatch(); }
watch(withGT, () => { clear("gt"); });
async function loadCatalog() { const request = ++catalogRequest; loading.value = true; catalogError.value = ""; try { const { data } = await http.get<PcbCatalog>("/scenes/pcb/segmentation/models"); if (!disposed && request === catalogRequest) { catalog.value = data; selected.value = PCB_MODELS.includes(data.default_model as typeof PCB_MODELS[number]) ? data.default_model : "unet"; } } catch (err) { if (!disposed && request === catalogRequest) catalogError.value = formatError(err); } finally { if (!disposed && request === catalogRequest) loading.value = false; } }
async function selectFile(event: Event, kind: "image" | "gt") {
  const input = event.target as HTMLInputElement, file = input.files?.[0]; input.value = "";
  if (!file || !ready.value || submitting.value) return;
  const revision = ++revisions[kind]; validating[kind] = true; errors[kind] = ""; let url = "";
  try {
    if (!file.size || file.size > Math.min(catalog.value?.max_image_bytes ?? 2097152, 2097152)) throw new Error("请选择非空图像，单张不超过 2 MiB。");
    const isPNG = /\.png$/i.test(file.name), isJPEG = /\.jpe?g$/i.test(file.name);
    if ((!isPNG && !isJPEG) || (kind === "gt" && !isPNG)) throw new Error(kind === "gt" ? "GT 只接受单通道 PNG。" : "原图只接受 PNG 或 JPEG。");
    const bytes = new Uint8Array(await file.slice(0, 32).arrayBuffer());
    if (isPNG && (![137,80,78,71,13,10,26,10].every((b,i) => bytes[i] === b) || bytes[24] !== 8 || bytes[25] !== (kind === "gt" ? 0 : 2))) throw new Error(kind === "gt" ? "GT 必须是 8 位单通道 PNG；二值像素由服务端校验。" : "PNG 原图必须是 8 位 RGB，不支持灰度或透明通道。");
    if (isJPEG && !(bytes[0] === 255 && bytes[1] === 216 && bytes[2] === 255)) throw new Error("文件内容不是有效 JPEG，请重新导出图像。");
    url = URL.createObjectURL(file); const preview = new Image(); preview.src = url;
    await preview.decode(); if (preview.naturalWidth !== 220 || preview.naturalHeight !== 220) throw new Error(`图像必须为 220 × 220；当前为 ${preview.naturalWidth} × ${preview.naturalHeight}，请按输入协议重新导出。`);
    if (disposed || revision !== revisions[kind]) return;
    const field = kind === "image" ? image : gt; if (field.value) URL.revokeObjectURL(field.value.url); field.value = { file, url }; url = ""; invalidateBatch();
  } catch (err) { if (!disposed && revision === revisions[kind]) errors[kind] = err instanceof Error ? err.message : "无法解码图像，请检查文件。"; }
  finally { if (url) URL.revokeObjectURL(url); if (!disposed && revision === revisions[kind]) validating[kind] = false; }
}
async function submit() {
  if (!canSubmit.value || !image.value) return;
  submitting.value = true; submitError.value = ""; submitStage.value = "正在上传…";
  try {
    if (!uploadedBatch.value) { const form = new FormData(); form.append("file", image.value.file); if (withGT.value && gt.value) form.append("gt", gt.value.file); const { data } = await http.post("/scenes/pcb/segmentation/uploads", form); if (disposed) return; uploadedBatch.value = data.batch_id; }
    submitStage.value = "正在提交…";
    const { data } = await http.post("/scenes/pcb/segmentation/tasks", { batch_id: uploadedBatch.value, model_id: selected.value, include_cam: includeCam.value });
    if (!disposed) await router.push(`/inspect/pcb/tasks/${encodeURIComponent(data.id)}`);
  } catch (err) { if (!disposed) submitError.value = formatError(err); } finally { if (!disposed) submitting.value = false; }
}
onMounted(loadCatalog);
onBeforeUnmount(() => { disposed = true; catalogRequest++; for (const choice of [image.value, gt.value]) if (choice) URL.revokeObjectURL(choice.url); });
</script>

<style scoped>
.pcb-new-grid { display:grid; grid-template-columns:minmax(0,1.1fr) minmax(0,1fr); gap:22px; align-items:start; }.pcb-side-stack { display:grid; gap:20px; min-width:0; }.pcb-upload-preview { min-height:290px; background:linear-gradient(#dae4ee60 1px,transparent 1px),linear-gradient(90deg,#dae4ee60 1px,transparent 1px),#f4f7fb; background-size:22px 22px; }.pcb-upload-preview img { width:220px; height:220px; box-shadow:0 3px 12px #203b5c18; }.pcb-upload-placeholder { display:grid; text-align:center; gap:10px; padding:25px; color:#527394; }.pcb-upload-placeholder .el-icon { margin:auto; font-size:36px; color:#7392b8; }.pcb-upload-placeholder strong { color:#345473; font-size:18px; }.pcb-upload-placeholder span { font-size:14px; }.upload-actions { margin-top:18px; }.image-name { overflow-wrap:anywhere; min-width:0; }.input-policy { margin:16px 0 0; }.pcb-advanced { margin-top:22px; padding-top:18px; border-top:1px solid #e3eaf3; }.pcb-advanced summary { cursor:pointer; color:#305e93; font-size:15px; }.pcb-advanced-content { padding-top:16px; }.pcb-advanced-content .pcb-muted { margin:5px 0 16px; }.gt-upload { margin-bottom:18px; }.gt-preview { display:block; width:90px; height:90px; object-fit:contain; margin-top:12px; border:1px solid #dce6f2; }.pcb-models { display:grid; gap:12px; }.pcb-model { display:flex; align-items:center; gap:11px; padding:17px 14px; border:1px solid #dce6f2; border-radius:8px; cursor:pointer; min-width:0; }.pcb-model.selected { background:#f1f6ff; border-color:#85a9e5; }.pcb-model.unavailable { cursor:not-allowed; background:#f8fafc; }.pcb-model input { margin:0; accent-color:#2f6be5; width:16px; height:16px; flex:none; }.pcb-model-info { display:grid; gap:7px; min-width:0; }.pcb-model-info strong { font-size:17px; color:#203b5c; overflow-wrap:anywhere; }.pcb-model-info>span { font-size:13px; color:#526c89; }.pcb-model-badge { margin-left:auto; font-size:12px; color:#436a9a; white-space:nowrap; }.model-note { margin:16px 0 0; }.pcb-submit-summary { margin:0 0 20px; }.pcb-submit-summary>div { display:flex; justify-content:space-between; padding:10px 0; border-bottom:1px solid #e8edf5; font-size:14px; }.pcb-submit-summary dt { color:#526b87; }.pcb-submit-summary dd { margin:0; color:#244367; font-weight:500; }.pcb-submit>.el-button { width:100%; min-height:44px; }.pcb-submit>a { display:inline-block; margin-top:17px; font-size:14px; }.submit-hint { margin:10px 0 0; }
@media(max-width:1050px) { .pcb-new-grid { grid-template-columns:minmax(0,1fr); }.pcb-side-stack { grid-template-columns:minmax(0,1fr); } } @media(max-width:600px) { .pcb-upload-preview { min-height:260px; }.pcb-model { padding:14px 10px; }.pcb-model-info strong { font-size:16px; }.pcb-model-badge { font-size:11px; } }
</style>

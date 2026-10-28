<template>
  <div class="classification-new cls-scope">
    <aside class="cls-notice">
      <strong>NEU-CLS · 六类已知缺陷，单张图像一个类别</strong>
      <p>不包含正常 / 良品类，也不能据此排除未知缺陷。没有真实图级标签时，只展示预测类别与得分，不计算准确率。</p>
      <ul v-if="classes.length" class="cls-class-list"><li v-for="item in classes" :key="item.id"><b>{{ item.id }}</b>{{ item.display_zh }}</li></ul>
    </aside>
    <div v-if="loading" class="cls-state" role="status">正在校验本地分类模型目录…</div>
    <div v-else-if="catalogError" class="cls-state error" role="alert"><strong>分类模型目录暂不可用</strong><p>{{ catalogError }}</p><el-button @click="loadCatalog">重新加载目录</el-button></div>
    <div v-else-if="catalog" class="cls-grid">
      <section class="cls-panel">
        <div class="cls-panel-head"><div><h2>上传待分类图像</h2><p>最多 {{ catalog.max_images }} 张，单张不超过 {{ maxMegabytes }} MB</p></div><span class="cls-count">{{ images.length }} / {{ catalog.max_images }}</span></div>
        <div class="upload-controls cls-actions">
          <el-button :disabled="submitting" @click="fileInput?.click()"><el-icon><UploadFilled /></el-icon>选择图像</el-button>
          <input ref="fileInput" class="file-input" type="file" multiple accept=".png,.jpg,.jpeg,.bmp,.tif,.tiff" aria-label="分类原图" :disabled="submitting" @change="addImages" />
          <el-button v-if="images.length" :disabled="submitting" text @click="clearImages">清空</el-button>
          <span class="cls-muted">PNG / JPEG / BMP / TIFF</span>
        </div>
        <p class="cls-muted image-policy">支持单帧图像，不超过 400 万像素，长宽比不超过 4:1；同一批不重复上传相同图像。</p>
        <p v-if="fileError" class="cls-error" role="alert">{{ fileError }}</p>
        <div class="labels-control"><el-checkbox v-model="withLabels" :disabled="submitting || !classes.length">填写真实图级标签</el-checkbox><p class="cls-muted">{{ withLabels ? '请为每张图选择已知真值；未标完整时不能提交。模型预测不能作为标签。' : '可以直接分类；本次不会生成 Accuracy、Macro-F1 或混淆矩阵。' }}</p></div>
        <div v-if="!images.length" class="cls-state upload-empty"><el-icon><Picture /></el-icon><strong>添加钢铁表面原图</strong><p>图像保留原始内容，预处理由分类模型协议统一执行。</p></div>
        <ul v-else class="image-list" aria-label="待分类图像">
          <li v-for="(item, index) in images" :key="item.id">
            <div class="image-preview"><img v-if="!item.previewFailed" :src="item.url" :alt="item.file.name" @error="item.previewFailed = true" /><span v-else>浏览器无法预览</span></div>
            <div class="image-info"><strong :title="item.file.name">{{ item.file.name }}</strong><span>{{ (item.file.size / 1024).toFixed(0) }} KB</span>
              <label v-if="withLabels" class="class-select"><span>真实类别</span><select v-model="item.classId" :aria-label="`${item.file.name} 真实类别`" :disabled="submitting" @change="invalidateBatch"><option :value="null">请选择标签</option><option v-for="label in classes" :key="label.id" :value="label.id">{{ label.id }} · {{ label.display_zh }}</option></select></label>
            </div>
            <el-button text :disabled="submitting" :aria-label="`移除 ${item.file.name}`" @click="removeImage(index)">移除</el-button>
          </li>
        </ul>
        <p v-if="withLabels && images.length" class="cls-muted">已标注 {{ labeledCount }} / {{ images.length }} 张</p>
      </section>
      <div class="model-stack">
        <section class="cls-panel">
          <div class="cls-panel-head"><div><h2>选择内置分类模型</h2><p>同一批图像，依次在 CPU 上运行</p></div><span class="cls-count">{{ selected.length }} / {{ catalog.max_models }}</span></div>
          <el-checkbox-group v-model="selected" class="classification-models" :disabled="submitting">
            <el-checkbox v-for="model in catalog.models" :key="model.slug" :label="model.slug" :disabled="!model.available || (selected.length >= catalog.max_models && !selected.includes(model.slug))">
              <strong>{{ model.name }}</strong><span v-if="model.slug === catalog.default_model" class="default-model">默认模型</span>
              <span class="model-spec">参数量 <b>{{ formatParamCount(model.param_count) }}</b></span>
              <span :class="model.available ? 'model-ready' : 'model-unavailable'">{{ model.available ? 'CPU 已校验' : model.reason || '当前不可用' }}</span>
            </el-checkbox>
          </el-checkbox-group>
          <p v-if="!catalog.models.some(model => model.available)" class="cls-error">当前没有通过本机校验的分类权重，暂不可提交。</p>
          <p class="cls-muted protocol-note">六类标签顺序和图像预处理来自导出资产。网站不训练模型，不将离线测试成绩作为本批图像的指标。</p>
        </section>
        <section class="cls-panel submit-panel">
          <div class="cls-panel-head"><div><h2>运行分类</h2><p>{{ withLabels ? '完整标签用于本批分类指标' : '无标签预测 · 仅展示类别和得分' }}</p></div><span class="cls-count">CPU</span></div>
          <div class="submit-summary"><span><strong>{{ images.length }}</strong> 张图像</span><span><strong>{{ selected.length }}</strong> 个模型</span><span>{{ withLabels ? `${labeledCount} 张标签` : '未提供标签' }}</span></div>
          <p v-if="submitError" class="cls-error" role="alert">{{ submitError }}</p>
          <p v-if="uploadedBatch && submitError" class="cls-muted">图像批次已保存，重试将沿用该批次。</p>
          <el-button type="primary" :disabled="!canSubmit" :loading="submitting" @click="submit">{{ submitting ? submitStage : '开始分类' }}</el-button>
          <p v-if="!canSubmit && !submitting" class="cls-muted">{{ submitHint }}</p>
          <router-link to="/records">查看历史记录 →</router-link>
        </section>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { Picture, UploadFilled } from "@element-plus/icons-vue";
import { formatError, http } from "../../api/http";
import { formatParamCount } from "../../api/labels";
import type { ClassificationCatalog } from "./types";
import "./classification.css";

type ImageItem = { id: number; file: File; url: string; classId: number | null; previewFailed: boolean };
const router = useRouter();
const catalog = ref<ClassificationCatalog | null>(null);
const loading = ref(true), catalogError = ref(""), fileError = ref(""), submitError = ref("");
const selected = ref<string[]>([]), images = ref<ImageItem[]>([]);
const fileInput = ref<HTMLInputElement | null>(null);
const withLabels = ref(false), submitting = ref(false), submitStage = ref("正在上传…");
const uploadedBatch = ref<string | null>(null);
let sequence = 0, request = 0, disposed = false;
const classes = computed(() => catalog.value?.models.find(m => m.available)?.classes ?? []);
const maxMegabytes = computed(() => ((catalog.value?.max_image_bytes ?? 0) / 1024 / 1024).toFixed(0));
const labeledCount = computed(() => images.value.filter(item => Number.isInteger(item.classId) && classes.value.some(label => label.id === item.classId)).length);
const canSubmit = computed(() => !submitting.value && !loading.value && !catalogError.value && !!catalog.value && images.value.length > 0 && images.value.length <= catalog.value.max_images && selected.value.length > 0 && selected.value.length <= catalog.value.max_models && selected.value.every(slug => catalog.value?.models.some(model => model.slug === slug && model.available)) && (!withLabels.value || labeledCount.value === images.value.length));
const submitHint = computed(() => !images.value.length ? "请选择至少 1 张图像。" : !selected.value.length ? "请选择至少 1 个可用模型。" : withLabels.value && labeledCount.value !== images.value.length ? "请补全每张图的真实标签，或关闭标签填写后只做预测。" : "请检查图像数量与模型可用状态。");
function invalidateBatch() { uploadedBatch.value = null; submitError.value = ""; }
watch(withLabels, invalidateBatch);

async function loadCatalog() {
  const token = ++request; loading.value = true; catalogError.value = "";
  try {
    const { data } = await http.get<ClassificationCatalog>("/classification/models");
    if (disposed || token !== request) return;
    catalog.value = data;
    selected.value = data.models.some(m => m.slug === data.default_model && m.available) ? [data.default_model] : [];
  } catch (err) { if (!disposed && token === request) catalogError.value = formatError(err); }
  finally { if (!disposed && token === request) loading.value = false; }
}
function addImages(event: Event) {
  const input = event.target as HTMLInputElement; const added = Array.from(input.files ?? []); input.value = "";
  if (!catalog.value || submitting.value) return;
  fileError.value = "";
  if (images.value.length + added.length > catalog.value.max_images) { fileError.value = `单次最多 ${catalog.value.max_images} 张，请减少后重新选择。`; return; }
  if (added.some(file => !/\.(png|jpe?g|bmp|tiff?)$/i.test(file.name) || !file.size || file.size > catalog.value!.max_image_bytes)) { fileError.value = `请选择有效的 PNG、JPEG、BMP 或 TIFF 图像，单张不超过 ${maxMegabytes.value} MB。`; return; }
  if (added.some(file => images.value.some(item => item.file.name === file.name && item.file.size === file.size && item.file.lastModified === file.lastModified))) { fileError.value = "同一文件已在列表中，请移除重复选择。"; return; }
  images.value.push(...added.map(file => ({ id: ++sequence, file, url: URL.createObjectURL(file), classId: null, previewFailed: false })));
  invalidateBatch();
}
function removeImage(index: number) { const [item] = images.value.splice(index, 1); if (item) URL.revokeObjectURL(item.url); invalidateBatch(); }
function clearImages() { images.value.forEach(item => URL.revokeObjectURL(item.url)); images.value = []; fileError.value = ""; invalidateBatch(); }
async function submit() {
  if (!canSubmit.value) return;
  submitting.value = true; submitError.value = ""; submitStage.value = "正在上传…";
  const modelSlugs = [...selected.value];
  try {
    if (!uploadedBatch.value) {
      const form = new FormData(); images.value.forEach(item => form.append("files", item.file));
      if (withLabels.value) form.append("labels_json", JSON.stringify(images.value.map(item => item.classId)));
      const { data } = await http.post("/classification/uploads", form);
      if (disposed) return;
      uploadedBatch.value = data.batch_id;
    }
    submitStage.value = "正在提交…";
    const { data } = await http.post("/classification/tasks", { batch_id: uploadedBatch.value, model_slugs: modelSlugs });
    if (!disposed) await router.push(`/classification/${data.id}`);
  } catch (err) { if (!disposed) submitError.value = formatError(err); }
  finally { if (!disposed) submitting.value = false; }
}
onMounted(loadCatalog);
onBeforeUnmount(() => { disposed = true; request++; images.value.forEach(item => URL.revokeObjectURL(item.url)); });
</script>

<style scoped>
.file-input { position: absolute; width: 1px; height: 1px; opacity: 0; overflow: hidden; }
.upload-controls { margin-bottom: 18px; }
.labels-control { padding: 13px 15px; background: #f5f8fc; border-radius: 8px; margin-bottom: 18px; }
.labels-control p { margin: 5px 0 0; }
.upload-empty { text-align: center; padding: 48px 20px; }
.upload-empty .el-icon { display: block; margin: 0 auto 12px; color: #557eac; font-size: 34px; }
.image-list { margin: 0; padding: 0; list-style: none; max-height: 580px; overflow-y: auto; }
.image-list li { display: flex; align-items: center; gap: 14px; padding: 12px 0; border-bottom: 1px solid #e7edf5; }
.image-preview { width: 86px; height: 86px; flex: none; background: #edf2f8; border-radius: 6px; overflow: hidden; display: grid; place-items: center; }
.image-preview img { width: 100%; height: 100%; object-fit: contain; }
.image-preview span { text-align: center; color: #4f627b; font-size: 12px; padding: 8px; }
.image-info { min-width: 0; flex: 1; }
.image-info > strong { display: block; font-size: 15px; overflow-wrap: anywhere; }
.image-info > span { display: block; font-size: 13px; color: #5e7188; margin-top: 5px; }
.class-select { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin-top: 9px; color: #4f627b; font-size: 13px; }
.class-select select { min-width: 0; max-width: 100%; padding: 6px 8px; border: 1px solid #cbd9ea; border-radius: 5px; background: #fff; color: #243e60; font-size: 14px; }
.model-stack { display: grid; gap: 20px; min-width: 0; }
.classification-models { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.classification-models :deep(.el-checkbox) { height: auto; margin: 0; padding: 15px 12px; border: 1px solid #d7e2f0; border-radius: 8px; align-items: flex-start; min-width: 0; white-space: normal; }
.classification-models :deep(.el-checkbox.is-checked) { border-color: #89b0ed; background: #f1f6ff; }
.classification-models :deep(.el-checkbox.is-disabled) { background: #f7f9fc; }
.classification-models :deep(.el-checkbox__input) { margin-top: 4px; }
.classification-models :deep(.el-checkbox__label) { min-width: 0; padding-left: 8px; }
.classification-models strong { font-size: 17px; line-height: 1.5; display: block; color: #1d3454; overflow-wrap: anywhere; }
.model-spec { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 10px; color: #4f627b; font-size: 13px; }
.model-spec b { font-weight: 500; color: #294465; }
.default-model { display: inline-block; margin-top: 5px; color: #285e9a; font-size: 12px; }
.model-ready, .model-unavailable { display: block; font-size: 13px; line-height: 1.6; margin-top: 5px; }
.model-ready { color: #23735c; }.model-unavailable { color: #725952; }
.protocol-note { margin-bottom: 0; }
.submit-summary { display: flex; flex-wrap: wrap; gap: 15px; padding-bottom: 18px; color: #4f627b; font-size: 14px; }.submit-summary strong { font-size: 22px; color: #1e3a5c; margin-right: 5px; }
.submit-panel > .el-button { width: 100%; min-height: 43px; }.submit-panel > a { display: inline-block; font-size: 14px; margin-top: 16px; }
@media (max-width: 600px) { .classification-models { grid-template-columns: minmax(0, 1fr); }.image-preview { width: 66px; height: 76px; }.image-list li { gap: 9px; }.image-list .el-button { padding: 6px; } }
</style>

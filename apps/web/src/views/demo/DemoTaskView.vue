<template>
  <div class="wb-result evidence-result">
    <header class="head result-heading">
      <div class="heading-main">
        <p class="eyebrow">公开演示 · 钢铁表面缺陷分割</p>
        <div class="title-row"><h1>演示结果</h1><TaskStatus v-if="task" :status="task.status" /><span v-else class="context-badge">读取中</span><span class="context-badge">仅可视化 · 不计算精度</span></div>
        <div class="task-reference"><span>任务编号</span><code>{{ taskId }}</code></div>
      </div>
      <router-link class="back-link" to="/demo"><el-icon><ArrowLeft /></el-icon>再选样例</router-link>
    </header>
    <p class="demo-disclaimer">{{ task?.disclaimer || "公开演示 / 预备样例 / 不代表测试集性能" }}</p>
    <el-alert v-if="loadError" :title="loadError" type="error" show-icon class="mb" />
    <el-alert v-if="task?.error_summary" :title="task.error_summary" type="warning" show-icon class="mb" />
    <el-alert v-if="pending" title="正在对预备样例做内置模型推理，完成后显示拼图。" type="info" show-icon class="mb" />

    <section class="result-viewer" aria-label="公开演示图层查看器">
      <div class="viewer-topbar">
        <el-radio-group v-model="view" class="view-tabs" aria-label="图层类型"><el-radio-button label="mask">彩色掩码拼图</el-radio-button><el-radio-button label="overlay">叠加拼图</el-radio-button><el-radio-button label="cam">热力图</el-radio-button></el-radio-group>
        <div class="sample-nav">
          <el-select v-if="previewSamples.length" v-model="index" aria-label="选择样本" class="sample-select"><el-option v-for="(sample, sampleIndex) in previewSamples" :key="sample.id" :label="sample.sample_key" :value="sampleIndex" /></el-select>
          <span class="sample-counter">{{ previewSamples.length ? `${index + 1} / ${previewSamples.length}` : "暂无拼图" }}</span>
          <el-button :icon="ArrowLeft" :disabled="index <= 0" aria-label="上一张" title="上一张" @click="index -= 1" />
          <el-button :icon="ArrowRight" :disabled="index >= previewSamples.length - 1" aria-label="下一张" title="下一张" @click="index += 1" />
        </div>
      </div>
      <div class="viewer-body">
        <div class="image-heading"><span><el-icon><Picture /></el-icon>{{ view === 'cam' ? "模型关注区域" : "原图与模型输出" }}</span><span>{{ currentSample?.sample_key || "等待结果生成" }}</span></div>
        <div v-if="currentSample" class="stage">
          <OverlayMontage v-if="view === 'overlay' && originUrl && overlayPanels.length" :origin-url="originUrl" :panels="overlayPanels" :alpha="defectAlpha" />
          <img v-else-if="view === 'cam' && camUrl" :src="camUrl" :alt="`${currentSample.sample_key} Grad-CAM`" />
          <div v-else-if="view === 'cam'" class="viewer-empty cam-empty"><el-icon><Picture /></el-icon><p>暂无热力图</p><span>演示只对内置模型生成 Grad-CAM。</span></div>
          <img v-else-if="montageUrl" :src="montageUrl" :alt="currentSample.sample_key" />
          <div v-else class="viewer-empty"><el-icon><Picture /></el-icon><p>当前样本暂无可用图层</p><span>任务运行中时会自动刷新，也可以选择其他样本。</span></div>
        </div>
        <div v-else class="viewer-empty"><el-icon><Picture /></el-icon><p>{{ pending ? "正在生成演示结果" : "暂无可展示的样本" }}</p><span>内置模型输出将在任务完成后展示。</span></div>
        <p v-if="view === 'cam'" class="cam-note">{{ task?.cam_disclaimer || "解释图：热区表示模型对该类预测的贡献，不是标注。蓝低红高。" }}</p>
      </div>
      <div class="viewer-controls">
        <div class="legend"><span class="control-label">类别图例</span><span v-for="item in task?.legend ?? []" :key="item.id" class="chip"><i :style="{ background: item.color }"></i>{{ item.name }}</span></div>
        <div v-if="view === 'overlay'" class="control-group opacity-control"><span class="control-label">缺陷透明度</span><el-slider v-model="defectAlpha" :min="0" :max="100" aria-label="缺陷透明度" /><span class="alpha-val">{{ defectAlpha }}%</span></div>
        <div v-if="view === 'cam'" class="control-group cam-control"><span class="control-label">热力图类别</span><el-radio-group v-model="camClass" size="small"><el-radio-button v-for="item in camClasses" :key="item.id" :label="item.id">{{ item.name }}</el-radio-button></el-radio-group><span class="jet" title="Jet：蓝低红高"><i></i>蓝低 · 红高</span></div>
        <span v-if="view === 'mask'" class="viewer-hint">切换图层，查看预测细节</span>
      </div>
    </section>

    <div class="result-details">
      <section class="detail-card execution-card">
        <div class="section-title"><span class="section-icon"><el-icon><Connection /></el-icon></span><h2>模型执行状态</h2><span class="section-meta">{{ task?.models?.length ?? 0 }} 个模型</span></div>
        <div v-for="model in task?.models ?? []" :key="model.model_version_id" class="model-row"><div class="model-identity"><strong>{{ model.name }}</strong><span>内置模型</span></div><TaskStatus :status="model.status" /><p v-if="model.fail_stage || model.fail_message" class="model-failure">{{ model.fail_stage }}<template v-if="model.fail_stage && model.fail_message"> · </template>{{ model.fail_message }}</p></div>
        <p v-if="!task?.models?.length" class="card-note">模型信息将在任务加载后展示。</p>
      </section>
      <section class="detail-card trace-card">
        <div class="section-title"><span class="section-icon"><el-icon><Files /></el-icon></span><h2>演示信息</h2></div>
        <dl class="trace-list"><div><dt>样本来源</dt><dd>预备样例</dd></div><div><dt>样本数量</dt><dd>{{ task?.n ?? task?.samples?.length ?? 0 }} 张</dd></div><div><dt>当前样本</dt><dd class="mono">{{ currentSample?.sample_key || '—' }}</dd></div><div><dt>结果用途</dt><dd>观察分割效果，不作为精度依据</dd></div></dl>
      </section>
      <section class="detail-card download-card">
        <div class="section-title"><span class="section-icon"><el-icon><Download /></el-icon></span><h2>下载结果</h2></div>
        <div class="layer-downloads">
          <el-button v-if="originUrl" plain @click="openLayer(originUrl, `${currentSample?.sample_key}_origin.png`)">原图</el-button>
          <el-button v-if="maskUrl" plain @click="openLayer(maskUrl, `${currentSample?.sample_key}__mask.png`)">本张掩码拼图</el-button>
          <el-button v-if="overlayUrl" plain @click="openLayer(overlayUrl, `${currentSample?.sample_key}__overlay.png`)">本张叠加拼图</el-button>
          <el-button v-if="camUrl" plain @click="openLayer(camUrl, `${currentSample?.sample_key}__cam_c${camClass}.png`)">本张热力图拼图</el-button>
        </div>
        <el-button class="bundle-button" type="primary" :icon="Download" :disabled="!bundleReady" @click="downloadBundle">下载图层包</el-button>
        <p v-if="!bundleReady && task?.bundle_unavailable_reason" class="card-note">{{ task.bundle_unavailable_reason }}</p><p v-if="task?.artifact_notice" class="card-note">{{ task.artifact_notice }}</p>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ArrowLeft, ArrowRight, Download, Files, Picture, Connection } from "@element-plus/icons-vue";
import TaskStatus from "../../components/TaskStatus.vue";
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useRoute } from "vue-router";
import { ElMessage } from "element-plus";
import OverlayMontage, { type OverlayPanel } from "../../components/OverlayMontage.vue";
import { formatError, http } from "../../api/http";
import { downloadAuthFile } from "../../api/labels";

type Artifact = { kind: string; sample_key: string | null; url: string; model_version_id?: string | null };
type Sample = { id: string; sample_key: string };
type Task = {
  id: string;
  status: string;
  disclaimer?: string;
  error_summary: string | null;
  n?: number;
  samples: Sample[];
  preview_sample_keys?: string[];
  artifacts: Artifact[];
  legend: Array<{ id: number; name: string; color: string }>;
  cam_disclaimer?: string;
  models: Array<{ model_version_id: string; name: string; status: string; fail_stage?: string; fail_message?: string }>;
  bundle_ready?: boolean;
  bundle_unavailable_reason?: string | null;
  artifact_notice?: string | null;
};

const route = useRoute();
const taskId = computed(() => String(route.params.taskId));
const task = ref<Task | null>(null);
const loadError = ref("");
const index = ref(0);
const view = ref<"mask" | "overlay" | "cam">("mask");
const defectAlpha = ref(45);
const camClass = ref(1);
let timer: number | undefined;

const previewSamples = computed(() => {
  const all = task.value?.samples ?? [];
  const keys = task.value?.preview_sample_keys ?? [];
  if (!keys.length) return all;
  const byKey = new Map(all.map((sample) => [sample.sample_key, sample]));
  return keys.map((key) => byKey.get(key)).filter((sample): sample is Sample => Boolean(sample));
});
const currentSample = computed(() => previewSamples.value[index.value]);
const pending = computed(() => ["queued", "running"].includes(task.value?.status ?? ""));

function sampleUrl(kind: string, needle?: string, modelVersionId?: string | null) {
  const key = currentSample.value?.sample_key;
  if (!key || !task.value) return undefined;
  return task.value.artifacts.find((item) => {
    if (item.sample_key !== key) return false;
    if (item.kind !== kind) return false;
    if (needle && !item.url.includes(needle)) return false;
    if (modelVersionId && item.model_version_id !== modelVersionId) return false;
    return true;
  })?.url;
}

const maskUrl = computed(() => sampleUrl("montage", "__mask"));
const overlayUrl = computed(() => sampleUrl("montage", "__overlay"));
const originUrl = computed(() => sampleUrl("origin"));
const camClasses = computed(() => {
  const rows = (task.value?.legend ?? []).filter((item) => Number(item.id) > 0);
  return rows.length ? rows : [
    { id: 1, name: "夹渣", color: "#e23d2e" },
    { id: 2, name: "斑块", color: "#2f9e44" },
    { id: 3, name: "划痕", color: "#2f6fed" },
  ];
});
const camUrl = computed(() => sampleUrl("montage", `__cam_c${camClass.value}.png`));
const montageUrl = computed(() => {
  if (view.value === "overlay") return overlayUrl.value;
  if (view.value === "cam") return camUrl.value;
  return maskUrl.value;
});
const overlayPanels = computed((): OverlayPanel[] => {
  const rows: OverlayPanel[] = [{ title: "origin" }];
  for (const model of task.value?.models ?? []) {
    if (model.status !== "success") continue;
    const colorUrl = sampleUrl("pred_color", undefined, model.model_version_id);
    if (!colorUrl) continue;
    rows.push({ title: model.name, colorUrl });
  }
  return rows;
});
const bundleReady = computed(
  () => task.value?.bundle_ready === true,
);

async function openLayer(url: string, filename: string) {
  try {
    await downloadAuthFile(url.replace(/^\/api/, ""), filename);
  } catch (error) {
    ElMessage.error(formatError(error));
  }
}

async function downloadBundle() {
  try {
    await downloadAuthFile(`/demo/tasks/${taskId.value}/bundle`, `${taskId.value}_demo.zip`);
  } catch (error) {
    ElMessage.error(formatError(error));
  }
}

async function refresh() {
  const { data } = await http.get(`/demo/tasks/${taskId.value}`);
  task.value = data;
  if (index.value >= previewSamples.value.length) {
    index.value = 0;
  }
}

onMounted(async () => {
  try {
    await refresh();
    timer = window.setInterval(async () => {
      if (!task.value || pending.value) {
        await refresh();
      }
    }, 2500);
  } catch (error) {
    loadError.value = formatError(error);
  }
});

onUnmounted(() => {
  if (timer) window.clearInterval(timer);
});
</script>

<style scoped>
.evidence-result { min-width: 0; }
.result-heading { display: flex; justify-content: space-between; align-items: center; gap: 20px; margin-bottom: 22px; }
.heading-main { min-width: 0; }
.eyebrow { margin: 0 0 9px; color: #778aa5; font-size: 14px; font-weight: 600; letter-spacing: .13em; }
.title-row { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; }
.title-row h1 { margin: 0; color: #162743; font-size: clamp(24px, 2.2vw, 30px); letter-spacing: -.035em; }
.context-badge { display: inline-flex; padding: 5px 10px; border-radius: 6px; color: #677b98; background: #eaf0f8; font-size: 15px; }
.task-reference { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-top: 12px; color: #71829a; font-size: 15px; }
.task-reference code { overflow-wrap: anywhere; color: #526782; font-family: var(--lab-font-mono); }
.analyze-link { display: inline-flex; flex-shrink: 0; align-items: center; gap: 9px; padding: 12px 17px; border-radius: 8px; background: #2469ee; box-shadow: 0 4px 10px #2469ee20; color: #fff; text-decoration: none; font-size: 16px; font-weight: 600; }
.analyze-link:hover { background: #1559d9; }
.result-viewer, .detail-card { min-width: 0; background: #fff; border: 1px solid #e3eaf4; border-radius: 12px; box-shadow: 0 4px 18px #20375a04; }
.result-viewer { margin-bottom: 18px; overflow: hidden; }
.viewer-topbar { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 14px; padding: 16px 20px; border-bottom: 1px solid #eaf0f6; }
.view-tabs { display: flex; flex-wrap: wrap; gap: 6px; }
.view-tabs :deep(.el-radio-button__inner) { padding: 10px 13px; border: 0 !important; border-radius: 6px !important; box-shadow: none !important; background: transparent; color: #6d7f98; font-weight: 600; }
.view-tabs :deep(.el-radio-button__original-radio:checked + .el-radio-button__inner) { background: #eef4ff; color: #2469ee; }
.sample-nav { display: flex; align-items: center; gap: 8px; min-width: 0; }
.sample-select { width: 160px; }
.sample-counter { color: #8391a8; font-size: 15px; white-space: nowrap; }
.sample-nav .el-button { width: 32px; padding: 0; margin-left: 0; border-color: #edf1f7; background: #f6f9fd; }
.viewer-body { padding: 19px 20px 16px; }
.image-heading { display: flex; align-items: center; justify-content: space-between; gap: 16px; color: #405572; font-size: 15px; margin-bottom: 12px; }
.image-heading > span:first-child { display: flex; align-items: center; gap: 7px; font-weight: 600; }
.image-heading > span:last-child { color: #8795a9; overflow-wrap: anywhere; text-align: right; }
.evidence-result .stage { background: #f3f6fb; border: 1px solid #e5ebf3; border-radius: 8px; padding: 10px; overflow: auto; }
.stage > img, .stage :deep(.board) { display: block; min-width: 640px; width: 100%; max-width: none; height: auto; border-radius: 4px; }
.viewer-empty { display: flex; min-height: 250px; align-items: center; justify-content: center; flex-direction: column; gap: 12px; padding: 28px 20px; color: #8999b0; text-align: center; }
.viewer-empty > .el-icon { font-size: 36px; padding: 14px; border-radius: 16px; background: #e9eff8; color: #8fa6c8; box-sizing: content-box; }
.viewer-empty p { margin: 3px 0 0; color: #506681; font-size: 16px; font-weight: 600; }
.viewer-empty span { max-width: 430px; font-size: 15px; line-height: 1.8; }
.viewer-controls { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 16px; margin: 0 20px 20px; padding: 15px 16px; border: 1px solid #e6edf6; border-radius: 8px; background: #fcfdff; }
.legend, .control-group { display: flex; align-items: center; flex-wrap: wrap; gap: 15px; }
.control-label { color: #52657e; font-size: 15px; font-weight: 600; }
.chip { display: inline-flex; align-items: center; gap: 7px; color: #5a6c84; font-size: 15px; }
.chip i { display: block; width: 10px; height: 10px; border-radius: 3px; box-shadow: inset 0 0 0 1px #00000010; }
.opacity-control .el-slider { width: 150px; }
.alpha-val { color: #527092; font-size: 15px; font-variant-numeric: tabular-nums; }
.viewer-hint { color: #94a0b3; font-size: 15px; }
.jet { display: inline-flex; align-items: center; gap: 7px; color: #7b8da6; font-size: 14px; }
.jet i { width: 58px; height: 6px; border-radius: 3px; background: linear-gradient(90deg, #0000aa, #00ffff, #00ff00, #ffff00, #ff0000); }
.cam-note { margin: 12px 0 0; color: #8290a6; font-size: 15px; line-height: 1.8; }
.result-details { display: grid; grid-template-columns: minmax(0, 1.15fr) minmax(0, 1fr) minmax(220px, .8fr); gap: 16px; align-items: start; }
.detail-card { padding: 18px; }
.section-title { display: flex; align-items: center; gap: 10px; margin-bottom: 18px; }
.section-title h2 { margin: 0; color: #203753; font-size: 17px; font-weight: 650; }
.section-icon { display: inline-flex; align-items: center; justify-content: center; flex-shrink: 0; width: 29px; height: 29px; border-radius: 7px; background: #edf4ff; color: #2870eb; font-size: 19px; }
.section-meta { margin-left: auto; font-size: 14px; color: #91a0b4; }
.model-row { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 12px; border: 1px solid #e8edf5; border-radius: 7px; padding: 13px 12px; margin-top: 9px; }
.model-identity { display: flex; flex-direction: column; gap: 5px; min-width: 0; }
.model-identity strong { color: #334b68; font-size: 16px; overflow-wrap: anywhere; }
.model-identity > span { color: #98a4b5; font-size: 14px; }
.model-failure { flex-basis: 100%; padding-top: 10px; border-top: 1px solid #f1e6df; color: #a76b41; font-size: 15px; line-height: 1.7; overflow-wrap: anywhere; margin: 0; }
.trace-list { margin: 0; font-size: 15px; }
.trace-list > div { display: grid; grid-template-columns: 70px minmax(0, 1fr); gap: 12px; border-top: 1px solid #edf1f7; padding: 12px 0; }
.trace-list dt { color: #74859b; }
.trace-list dd { margin: 0; color: #465e7b; overflow-wrap: anywhere; line-height: 1.5; }
.trace-tag { display: inline-flex; background: #f0f5fc; color: #7086a5; padding: 2px 5px; border-radius: 3px; margin-left: 5px; font-size: 14px; }
.mono { font-family: var(--lab-font-mono); }
.layer-downloads { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; margin-bottom: 10px; }
.layer-downloads .el-button { width: 100%; margin: 0; padding: 0 5px; color: #55739b; border-color: #e3eaf5; font-size: 15px; }
.bundle-button { width: 100%; min-height: 36px; margin: 0 !important; font-size: 15px; }
.card-note { margin: 10px 0 0; color: #8d9bb0; font-size: 14px; line-height: 1.8; overflow-wrap: anywhere; }
.metrics { margin-bottom: 18px; }
.disclaimer, .meta { color: #8492a7; font-size: 15px; line-height: 1.8; margin: 0 0 8px; }
.cls { display: inline-block; margin-right: 12px; }
.acc-details { color: #7b8da4; font-size: 15px; margin-top: 12px; }
.acc-details summary { cursor: pointer; }
.acc-details ul { padding-left: 18px; line-height: 1.8; }
.mb { margin-bottom: 16px; }
@media (max-width: 1200px) {
  .result-details { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .download-card { grid-column: 1 / -1; }
  .download-card .layer-downloads { display: flex; flex-wrap: wrap; }
  .download-card .layer-downloads .el-button { width: auto; padding: 0 12px; }
  .download-card .bundle-button { width: auto; min-width: 220px; }
}
@media (max-width: 700px) {
  .result-heading { align-items: flex-start; flex-direction: column; gap: 14px; }
  .title-row { gap: 8px; }
  .title-row h1 { flex-basis: 100%; font-size: 26px; }
  .task-reference { gap: 6px; }
  .task-reference code { font-size: 14px; }
  .analyze-link { padding: 10px 13px; }
  .viewer-topbar, .viewer-body { padding: 12px; }
  .view-tabs { gap: 2px; }
  .view-tabs :deep(.el-radio-button__inner) { padding: 9px 10px; font-size: 15px; }
  .sample-nav { flex-wrap: wrap; gap: 6px; }
  .sample-select { width: 135px; }
  .viewer-controls { margin: 0 12px 12px; padding: 12px; }
  .control-group, .legend { gap: 12px; }
  .result-details { grid-template-columns: minmax(0, 1fr); }
  .download-card { grid-column: auto; }
  .detail-card { padding: 15px; }
  .viewer-empty { min-height: 220px; }
  .image-heading { align-items: flex-start; }
}
.demo-disclaimer { margin: -5px 0 20px; padding: 11px 14px; border: 1px solid #dfeafb; border-radius: 8px; background: #f4f8ff; color: #7184a0; font-size: 15px; line-height: 1.7; }
.back-link { display: inline-flex; flex-shrink: 0; align-items: center; gap: 6px; color: #4e6e97; font-size: 16px; text-decoration: none; padding: 10px 14px; border: 1px solid #dde6f2; border-radius: 7px; background: #fff; }
.back-link:hover { color: #2469ee; border-color: #a8c5fb; }
</style>

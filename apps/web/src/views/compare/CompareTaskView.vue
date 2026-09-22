<template>
  <div>
    <header class="head">
      <p class="eyebrow">{{ isEval ? "正式评测" : "缺陷分割" }}</p>
      <h1>任务 {{ taskId }}</h1>
      <p>
        状态 <strong>{{ task ? taskStatusLabel(task.status) : "读取中" }}</strong>
        · 样本量 {{ task?.n ?? task?.samples?.length ?? 0 }}
        · {{ task?.has_gt ? "有 GT" : "无 GT，不计算精度" }}
        <template v-if="isEval && previewSamples.length">
          · 抽样拼图 {{ previewSamples.length }} 张
        </template>
      </p>
      <p v-if="task?.dataset?.name" class="meta">
        数据 {{ task.dataset.name }}
        <template v-if="task.dataset.is_fixed_test"> · 固定测试集</template>
      </p>
    </header>

    <el-alert v-if="task?.error_summary" :title="task.error_summary" type="warning" show-icon class="mb" />
    <el-alert
      v-if="evalPending"
      title="正在对全部样本计算指标，完成后展示按文件名排序的前 8 张拼图。"
      type="info"
      show-icon
      class="mb"
    />

    <section v-if="metrics?.available" class="metrics">
      <h2>{{ isEval ? "正式评测指标" : "参考指标" }}</h2>
      <p class="disclaimer">{{ metrics.disclaimer || (isEval ? "本数据版本全量指标。当前固定集为 NEU-20，不是论文完整 test split。" : "快速对比参考指标，不代表完整测试集性能") }}</p>
      <p class="meta">n = {{ metrics.n }} · 在原图显示尺寸上计算 · {{ metrics.scope }}</p>
      <el-table :data="metrics.models ?? []" size="small" class="mb">
        <el-table-column prop="name" label="模型" min-width="140" />
        <el-table-column label="mIoU" width="110">
          <template #default="{ row }">{{ formatScore(row.mIoU) }}</template>
        </el-table-column>
        <el-table-column label="mDice" width="110">
          <template #default="{ row }">{{ formatScore(row.mDice) }}</template>
        </el-table-column>
        <el-table-column label="逐类 IoU" min-width="280">
          <template #default="{ row }">
            <span v-for="item in row.classes ?? []" :key="item.id" class="cls">
              {{ item.name }} {{ formatScore(item.iou) }}
            </span>
          </template>
        </el-table-column>
      </el-table>
      <details v-if="isEval && hasAcc" class="acc-details">
        <summary>像素准确率 Acc（辅助指标，不作为主结论）</summary>
        <ul>
          <li v-for="row in metrics.models ?? []" :key="row.model_version_id">
            {{ row.name }} · Acc {{ formatScore(row.Acc) }}
          </li>
        </ul>
      </details>
    </section>

    <div class="legend">
      <span v-for="item in task?.legend ?? []" :key="item.id" class="chip">
        <i :style="{ background: item.color }"></i>{{ item.name }}
      </span>
    </div>
    <div v-if="view === 'error'" class="legend">
      <span v-for="item in task?.error_legend ?? []" :key="item.id" class="chip">
        <i :style="{ background: item.color }"></i>{{ item.name }}
      </span>
    </div>

    <el-radio-group v-model="view" class="mb">
      <el-radio-button label="mask">彩色掩码拼图</el-radio-button>
      <el-radio-button label="overlay">叠加拼图</el-radio-button>
      <el-radio-button label="cam">热力图</el-radio-button>
      <el-radio-button v-if="task?.has_gt" label="error">错误图拼图</el-radio-button>
    </el-radio-group>
    <p v-if="view === 'cam'" class="cam-note">{{ task?.cam_disclaimer || "解释图：热区表示模型对该类预测的贡献，不是标注。蓝低红高。" }}</p>

    <div v-if="currentSample" class="stage">
      <div class="toolbar">
        <span>{{ currentSample.sample_key }}</span>
        <template v-if="view === 'overlay'">
          <span class="alpha-label">缺陷透明度</span>
          <el-slider v-model="defectAlpha" :min="0" :max="100" style="width: 180px" />
          <span class="alpha-val">{{ defectAlpha }}%</span>
        </template>
        <template v-if="view === 'cam'">
          <span class="alpha-label">缺陷类别</span>
          <el-radio-group v-model="camClass" size="small">
            <el-radio-button v-for="item in camClasses" :key="item.id" :label="item.id">{{ item.name }}</el-radio-button>
          </el-radio-group>
          <span class="jet" title="Jet：蓝低红高"><i></i>蓝低 · 红高</span>
        </template>
      </div>
      <OverlayMontage
        v-if="view === 'overlay' && originUrl && overlayPanels.length"
        :origin-url="originUrl"
        :panels="overlayPanels"
        :alpha="defectAlpha"
      />
      <img v-else-if="view === 'cam' && camUrl" :src="camUrl" :alt="`${currentSample.sample_key} Grad-CAM`" />
      <p v-else-if="view === 'cam'" class="cam-empty">暂无热力图。第一版只覆盖内置模型，学生模型不计算 Grad-CAM。</p>
      <img v-else-if="montageUrl" :src="montageUrl" :alt="currentSample.sample_key" />
    </div>

    <div class="pager">
      <el-button :disabled="index <= 0" @click="index -= 1">上一张</el-button>
      <span>{{ previewSamples.length ? `${index + 1} / ${previewSamples.length}` : "暂无拼图" }}</span>
      <el-button :disabled="index >= previewSamples.length - 1" @click="index += 1">下一张</el-button>
    </div>

    <div class="downloads">
      <el-button v-if="originUrl" link type="primary" @click="openLayer(originUrl, `${currentSample?.sample_key}_origin.png`)">原图</el-button>
      <el-button v-if="gtUrl" link type="primary" @click="openLayer(gtUrl, `${currentSample?.sample_key}_gt.png`)">本张 GT</el-button>
      <el-button v-if="maskUrl" link type="primary" @click="openLayer(maskUrl, `${currentSample?.sample_key}__mask.png`)">本张掩码拼图</el-button>
      <el-button v-if="overlayUrl" link type="primary" @click="openLayer(overlayUrl, `${currentSample?.sample_key}__overlay.png`)">本张叠加拼图</el-button>
      <el-button v-if="camUrl" link type="primary" @click="openLayer(camUrl, `${currentSample?.sample_key}__cam_c${camClass}.png`)">本张热力图拼图</el-button>
      <el-button v-if="errorUrl" link type="primary" @click="openLayer(errorUrl, `${currentSample?.sample_key}__error.png`)">本张错误图拼图</el-button>
      <el-button type="primary" :disabled="!bundleReady" @click="downloadBundle">下载图层包（供 Draw.io）</el-button>
    </div>

    <section class="models">
      <h3>模型</h3>
      <ul>
        <li v-for="model in task?.models ?? []" :key="model.model_version_id">
          {{ model.name }}（{{ model.role === "baseline" ? "baseline" : "学生模型" }}）· {{ taskStatusLabel(model.status) }}
          <template v-if="model.fail_stage"> · {{ model.fail_stage }} / {{ model.fail_message }}</template>
        </li>
      </ul>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useRoute } from "vue-router";
import { ElMessage } from "element-plus";
import OverlayMontage, { type OverlayPanel } from "../../components/OverlayMontage.vue";
import { formatError, http } from "../../api/http";
import { downloadAuthFile, taskStatusLabel } from "../../api/labels";

type Artifact = { kind: string; sample_key: string | null; url: string; model_version_id: string | null };
type Sample = { id: string; sample_key: string };
type Task = {
  id: string;
  type?: string;
  type_label?: string;
  status: string;
  has_gt: boolean;
  error_summary: string | null;
  n?: number;
  samples: Sample[];
  preview_sample_keys?: string[];
  artifacts: Artifact[];
  dataset?: { id?: string | null; name?: string | null; is_fixed_test?: boolean };
  legend: Array<{ id: number; name: string; color: string }>;
  error_legend?: Array<{ id: string; name: string; color: string }>;
  cam_disclaimer?: string;
  models: Array<{ model_version_id: string; name: string; role: string; status: string; fail_stage?: string; fail_message?: string }>;
  bundle_ready?: boolean;
};
type MetricModel = {
  model_version_id: string;
  name: string;
  mIoU: number;
  mDice: number;
  Acc?: number;
  IoU_per_class?: number[];
  classes?: Array<{ id: number; name: string; iou: number }>;
};
type Metrics = {
  available: boolean;
  scope?: string;
  n?: number;
  disclaimer?: string;
  models?: MetricModel[];
};

const route = useRoute();
const taskId = computed(() => String(route.params.taskId));
const task = ref<Task | null>(null);
const metrics = ref<Metrics | null>(null);
const index = ref(0);
const view = ref<"mask" | "overlay" | "cam" | "error">("mask");
const defectAlpha = ref(45);
const camClass = ref(1);
let timer: number | undefined;

const currentSample = computed(() => previewSamples.value[index.value]);
const isEval = computed(() => task.value?.type === "eval");
const evalPending = computed(() => isEval.value && ["queued", "running"].includes(task.value?.status ?? ""));
const previewSamples = computed(() => {
  const all = task.value?.samples ?? [];
  const keys = task.value?.preview_sample_keys ?? [];
  if (!keys.length) {
    return isEval.value ? [] : all;
  }
  const byKey = new Map(all.map((sample) => [sample.sample_key, sample]));
  return keys.map((key) => byKey.get(key)).filter((sample): sample is Sample => Boolean(sample));
});
const hasAcc = computed(() => (metrics.value?.models ?? []).some((row) => typeof row.Acc === "number"));

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
const errorUrl = computed(() => sampleUrl("montage", "__error"));
const originUrl = computed(() => sampleUrl("origin"));
const gtUrl = computed(() => sampleUrl("gt"));
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
  if (view.value === "error") return errorUrl.value;
  if (view.value === "cam") return camUrl.value;
  return maskUrl.value;
});
const overlayPanels = computed((): OverlayPanel[] => {
  const rows: OverlayPanel[] = [{ title: "origin" }];
  if (gtUrl.value) rows.push({ title: "GT", colorUrl: gtUrl.value });
  for (const model of task.value?.models ?? []) {
    if (model.status !== "success") continue;
    const colorUrl = sampleUrl("pred_color", undefined, model.model_version_id);
    if (!colorUrl) continue;
    rows.push({ title: model.name, colorUrl });
  }
  return rows;
});
const bundleReady = computed(
  () => task.value?.bundle_ready === true || ["success", "partial_success"].includes(task.value?.status ?? ""),
);

function formatScore(value: number | undefined) {
  if (typeof value !== "number" || Number.isNaN(value)) return "—";
  return value.toFixed(4);
}

async function openLayer(url: string, filename: string) {
  try {
    const path = url.replace(/^\/api/, "");
    await downloadAuthFile(path, filename);
  } catch (error) {
    ElMessage.error(formatError(error));
  }
}

async function downloadBundle() {
  try {
    await downloadAuthFile(`/tasks/${taskId.value}/bundle`, `${taskId.value}_drawio.zip`);
  } catch (error) {
    ElMessage.error(formatError(error));
  }
}

async function refresh() {
  const { data } = await http.get(`/tasks/${taskId.value}`);
  task.value = data;
  const metricsRes = await http.get(`/tasks/${taskId.value}/metrics`);
  metrics.value = metricsRes.data?.available ? metricsRes.data : { available: false };
  if (!task.value?.has_gt && view.value === "error") {
    view.value = "mask";
  }
  if (index.value >= previewSamples.value.length) {
    index.value = 0;
  }
}

onMounted(async () => {
  await refresh();
  timer = window.setInterval(async () => {
    if (!task.value || ["queued", "running"].includes(task.value.status)) {
      await refresh();
    }
  }, 2500);
});

onUnmounted(() => {
  if (timer) window.clearInterval(timer);
});
</script>

<style scoped>
.eyebrow {
  color: var(--lab-accent-2);
  letter-spacing: 0.16em;
  font-size: 12px;
}
.head p,
.models,
.meta,
.disclaimer {
  color: var(--lab-muted);
}
.disclaimer {
  font-size: 13px;
  margin: 0 0 8px;
}
.acc-details {
  color: var(--lab-muted);
  margin: 0 0 12px;
}
.acc-details summary {
  cursor: pointer;
  margin-bottom: 8px;
}
.acc-details ul {
  margin: 0;
  padding-left: 18px;
  line-height: 1.7;
}
.metrics {
  border: 1px solid var(--lab-line);
  padding: 16px 18px 8px;
  margin-bottom: 20px;
  background: #14181e;
}
.metrics h2 {
  margin: 0 0 8px;
  font-size: 16px;
  color: var(--lab-text);
}
.cls {
  display: inline-block;
  margin-right: 12px;
}
.legend {
  display: flex;
  gap: 16px;
  margin: 12px 0 20px;
  flex-wrap: wrap;
}
.chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.chip i {
  width: 12px;
  height: 12px;
  display: inline-block;
}
.stage {
  background: #0f1318;
  border: 1px solid var(--lab-line);
  padding: 12px;
  overflow: auto;
}
.stage img {
  max-width: 100%;
  display: block;
}
.alpha-label,
.alpha-val {
  color: var(--lab-muted);
  font-size: 13px;
}
.cam-note,
.cam-empty {
  color: var(--lab-muted);
  font-size: 13px;
  margin: 0 0 12px;
}
.cam-empty {
  margin: 24px 8px;
}
.jet {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--lab-muted);
  font-size: 12px;
}
.jet i {
  width: 72px;
  height: 8px;
  border-radius: 4px;
  background: linear-gradient(90deg, #0000aa, #00ffff, #00ff00, #ffff00, #ff0000);
}
.toolbar,
.pager,
.downloads {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
  margin: 12px 0;
}
.mb {
  margin-bottom: 16px;
}
</style>

<template>
  <div>
    <header class="head">
      <p class="eyebrow">公开演示</p>
      <h1>演示任务</h1>
      <p class="disclaimer">{{ task?.disclaimer || "公开演示 / 预备样例 / 不代表测试集性能" }}</p>
      <p>
        状态 <strong>{{ task ? taskStatusLabel(task.status) : "读取中" }}</strong>
        · 样例 {{ task?.n ?? 0 }} 张
        · 只出可视化，不计算精度
      </p>
    </header>

    <el-alert v-if="loadError" :title="loadError" type="error" show-icon class="mb" />
    <el-alert v-if="task?.error_summary" :title="task.error_summary" type="warning" show-icon class="mb" />
    <el-alert
      v-if="pending"
      title="正在对预备样例做内置模型推理，完成后显示拼图。"
      type="info"
      show-icon
      class="mb"
    />

    <div class="legend">
      <span v-for="item in task?.legend ?? []" :key="item.id" class="chip">
        <i :style="{ background: item.color }"></i>{{ item.name }}
      </span>
    </div>

    <el-radio-group v-model="view" class="mb">
      <el-radio-button label="mask">彩色掩码拼图</el-radio-button>
      <el-radio-button label="overlay">叠加拼图</el-radio-button>
    </el-radio-group>

    <div v-if="currentSample" class="stage">
      <div class="toolbar">
        <span>{{ currentSample.sample_key }}</span>
      </div>
      <img v-if="montageUrl" :src="montageUrl" :alt="currentSample.sample_key" />
    </div>

    <div class="pager">
      <el-button :disabled="index <= 0" @click="index -= 1">上一张</el-button>
      <span>{{ previewSamples.length ? `${index + 1} / ${previewSamples.length}` : "暂无拼图" }}</span>
      <el-button :disabled="index >= previewSamples.length - 1" @click="index += 1">下一张</el-button>
    </div>

    <div class="downloads">
      <el-button v-if="originUrl" link type="primary" @click="openLayer(originUrl, `${currentSample?.sample_key}_origin.png`)">原图</el-button>
      <el-button v-if="maskUrl" link type="primary" @click="openLayer(maskUrl, `${currentSample?.sample_key}__mask.png`)">本张掩码拼图</el-button>
      <el-button v-if="overlayUrl" link type="primary" @click="openLayer(overlayUrl, `${currentSample?.sample_key}__overlay.png`)">本张叠加拼图</el-button>
      <el-button type="primary" :disabled="!bundleReady" @click="downloadBundle">下载图层包</el-button>
      <router-link class="back" to="/demo">再选样例</router-link>
    </div>

    <section class="models">
      <h3>模型</h3>
      <ul>
        <li v-for="model in task?.models ?? []" :key="model.model_version_id">
          {{ model.name }} · {{ taskStatusLabel(model.status) }}
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
import { formatError, http } from "../../api/http";
import { downloadAuthFile, taskStatusLabel } from "../../api/labels";

type Artifact = { kind: string; sample_key: string | null; url: string };
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
  models: Array<{ model_version_id: string; name: string; status: string; fail_stage?: string; fail_message?: string }>;
  bundle_ready?: boolean;
};

const route = useRoute();
const taskId = computed(() => String(route.params.taskId));
const task = ref<Task | null>(null);
const loadError = ref("");
const index = ref(0);
const view = ref<"mask" | "overlay">("mask");
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

function sampleUrl(kind: string, needle?: string) {
  const key = currentSample.value?.sample_key;
  if (!key || !task.value) return undefined;
  return task.value.artifacts.find((item) => {
    if (item.sample_key !== key) return false;
    if (item.kind !== kind) return false;
    if (needle && !item.url.includes(needle)) return false;
    return true;
  })?.url;
}

const maskUrl = computed(() => sampleUrl("montage", "__mask"));
const overlayUrl = computed(() => sampleUrl("montage", "__overlay"));
const originUrl = computed(() => sampleUrl("origin"));
const montageUrl = computed(() => (view.value === "overlay" ? overlayUrl.value : maskUrl.value));
const bundleReady = computed(
  () => task.value?.bundle_ready === true || ["success", "partial_success"].includes(task.value?.status ?? ""),
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
.eyebrow {
  color: var(--lab-accent-2);
  letter-spacing: 0.16em;
  font-size: 12px;
}
.head p,
.models,
.meta {
  color: var(--lab-muted);
}
.disclaimer {
  border-left: 3px solid var(--lab-accent-2);
  padding-left: 12px;
  color: var(--lab-accent-2) !important;
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
.toolbar,
.pager,
.downloads {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
  margin: 12px 0;
}
.back {
  color: var(--lab-muted);
  text-decoration: none;
}
.back:hover {
  color: var(--lab-text);
}
.mb {
  margin-bottom: 16px;
}
</style>

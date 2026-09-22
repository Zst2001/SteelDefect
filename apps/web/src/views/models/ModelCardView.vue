<template>
  <div v-if="model">
    <header class="head">
      <p class="eyebrow">模型卡</p>
      <h1>{{ model.name }}</h1>
      <p>{{ modelStatusLabel(model.status) }} · {{ model.source === "builtin" ? "内置" : "学生导入" }}</p>
    </header>

    <el-alert
      v-if="model.requires_cuda"
      title="当前环境为 CPU，该模型标明需要 CUDA，不可运行。不会静默改用随机权重。"
      type="warning"
      show-icon
      class="mb"
    />
    <el-alert
      v-if="model.status === 'cannot_start'"
      :title="`不能启动 · ${failStageLabel(model.fail_stage)} · ${model.fail_message ?? ''}`"
      type="error"
      show-icon
      class="mb"
    />

    <dl class="facts">
      <div><dt>任务类型</dt><dd>{{ model.task_type }}</dd></div>
      <div><dt>输入尺寸</dt><dd>{{ model.input_size?.[0] }} × {{ model.input_size?.[1] }}</dd></div>
      <div><dt>通道 / 类别</dt><dd>{{ model.in_channels }} / {{ model.num_classes }}</dd></div>
      <div><dt>预处理</dt><dd>{{ model.preprocess?.name ?? model.preprocess_id }}（{{ model.preprocess?.width }}×{{ model.preprocess?.height }}）</dd></div>
      <div><dt>参数量</dt><dd>{{ formatParamCount(model.perf?.param_count ?? model.param_count) }}</dd></div>
      <div><dt>权重体积</dt><dd>{{ formatBytes(model.perf?.weight_bytes) }}</dd></div>
      <div><dt>本机前向</dt><dd>{{ latencyText }}</dd></div>
      <div><dt>本机 FPS</dt><dd>{{ fpsText }}</dd></div>
      <div><dt>权重哈希</dt><dd class="mono">{{ model.weight_sha256 ?? "—" }}</dd></div>
      <div><dt>指标来源</dt><dd>{{ model.metrics_source }}</dd></div>
    </dl>

    <h3>类别映射</h3>
    <ul>
      <li v-for="(name, id) in model.class_map" :key="id">{{ id }} · {{ name }}</li>
    </ul>

    <h3>可用可视化</h3>
    <p class="muted">原图、彩色掩码、叠加、边界、拼图。无论文出图工作台。</p>

    <h3 v-if="model.source === 'student'">检查工单</h3>
    <ol v-if="model.source === 'student' && model.admit_report?.stages?.length" class="stages">
      <li v-for="step in model.admit_report.stages" :key="step.stage">
        {{ failStageLabel(step.stage) }} · {{ step.ok ? "通过" : "失败" }} · {{ step.message }}
      </li>
    </ol>

    <section v-if="model.status === 'checking'" class="adapt">
      <h3>模型适配助手</h3>
      <p class="muted">正在隔离复检。通过后本版本留在你的模型中心；失败会留下新的阶段原文。助手不保证可运行。</p>
    </section>

    <section v-else-if="showAdapt" class="adapt">
      <h3>模型适配助手</h3>
      <template v-if="!adapt">
        <p v-if="adaptError" class="llm">诊断暂不可用：{{ adaptError }}。请刷新本页重试。</p>
        <p v-else class="llm">模型助手思考中…正在读取失败阶段并起草修改意见。</p>
        <p class="muted">{{ failStageLabel(model.fail_stage) }} · {{ model.fail_message || "等待诊断" }}</p>
      </template>
      <template v-else>
        <p class="muted">
          {{ failStageLabel(adapt.fail_stage) }} · {{ (adapt.kind_labels || []).join(" / ") || "诊断" }}
        </p>
        <p v-if="adapt.preview_note" class="preview">{{ adapt.preview_note }}</p>
        <p v-if="drafting" class="llm">模型助手思考中…规则诊断已就绪，正在补写修改意见。</p>
        <p v-else-if="adapt.llm_status === 'ok'" class="llm">说明由 {{ adapt.llm_model }} 起草，检查结果以隔离复检为准。</p>
        <p v-else-if="adapt.llm_status === 'error'" class="llm">大模型说明暂不可用，以下为规则诊断。请确认 .env 中的百炼密钥与模型名后重启 API。检查结果仍以复检为准。</p>
        <p v-else-if="adapt.llm_status === 'skipped'" class="llm">未调用大模型，以下为规则诊断。填入百炼密钥并重启 API 后刷新本页可生成说明。</p>
        <ul class="points">
          <li v-for="(point, index) in adapt.points" :key="index">{{ point }}</li>
        </ul>
        <pre v-if="adapt.diff" class="diff">{{ adapt.diff }}</pre>
        <p class="consent">{{ adapt.consent_hint }}</p>
        <div class="adapt-actions">
          <el-button type="primary" :disabled="!adapt.can_apply" :loading="busy" @click="applyAdapt(true)">
            按方案追加并复检
          </el-button>
          <el-button :disabled="busy" @click="applyAdapt(false)">不改代码只留意见</el-button>
        </div>
        <p v-if="!adapt.can_apply" class="muted">{{ adapt.apply_blocked_reason }}</p>
      </template>
    </section>

    <section class="adapt">
      <h3>参数量与本机耗时</h3>
      <p class="muted">{{ model.perf?.disclaimer }}</p>
      <dl class="facts compact">
        <div><dt>测量状态</dt><dd>{{ perfStatusLabel(model.perf?.status) }}</dd></div>
        <div><dt>协议</dt><dd>CPU · dummy · {{ model.perf?.input_h }}×{{ model.perf?.input_w }} · batch {{ model.perf?.batch }} · 预热 {{ model.perf?.warmup_runs }} / 计时 {{ model.perf?.timed_runs }}</dd></div>
        <div v-if="model.perf?.env"><dt>环境</dt><dd>{{ envText }}</dd></div>
        <div v-if="model.perf?.measured_at"><dt>测量时间</dt><dd>{{ model.perf.measured_at }}</dd></div>
      </dl>
      <el-alert
        v-if="model.perf?.status === 'failed'"
        :title="model.perf.fail_message || '测量失败'"
        type="error"
        show-icon
        class="mb"
      />
      <div class="adapt-actions">
        <el-button
          type="primary"
          :disabled="!canMeasure"
          :loading="measuring"
          @click="runMeasure"
        >
          {{ measureButtonText }}
        </el-button>
      </div>
      <p v-if="!model.runnable_here" class="muted">只有检查通过且当前环境可运行的模型才能测量。</p>
    </section>

    <div class="actions">
      <el-button type="primary" :disabled="!model.runnable_here" @click="goCompare">加入缺陷分割</el-button>
      <el-button v-if="model.log_available" @click="downloadLog">下载检查日志</el-button>
      <router-link to="/models">返回列表</router-link>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { formatError, http } from "../../api/http";
import { downloadAuthFile, failStageLabel, formatBytes, formatFps, formatLatencyMs, formatParamCount, modelStatusLabel } from "../../api/labels";
import { ElMessage, ElMessageBox } from "element-plus";

type Perf = {
  status: string;
  can_measure: boolean;
  param_count: number | null;
  weight_bytes: number | null;
  latency_ms_per_image: number | null;
  fps_per_image: number | null;
  flops: number | null;
  warmup_runs: number;
  timed_runs: number;
  batch: number;
  input_h: number;
  input_w: number;
  input_kind: string;
  device: string;
  env: Record<string, string> | null;
  fail_message: string | null;
  measured_at: string | null;
  disclaimer: string;
};

type Card = {
  id: string;
  name: string;
  source: string;
  status: string;
  fail_stage: string | null;
  fail_message: string | null;
  task_type: string;
  num_classes: number;
  in_channels: number;
  input_size: number[];
  class_map: Record<string, string>;
  preprocess_id: string;
  preprocess: { name: string; height: number; width: number } | null;
  requires_cuda: boolean;
  runnable_here: boolean;
  weight_sha256: string | null;
  param_count: number | null;
  flops: string;
  metrics_source: string;
  log_available?: boolean;
  admit_report?: { stages?: Array<{ stage: string; ok: boolean; message: string }> } | null;
  perf?: Perf | null;
};

type Adapt = {
  fail_stage: string | null;
  kind_labels: string[];
  can_apply: boolean;
  apply_blocked_reason: string | null;
  points: string[];
  preview_note: string | null;
  diff: string;
  llm_status: string;
  llm_model: string | null;
  consent_hint: string;
};

const route = useRoute();
const router = useRouter();
const model = ref<Card | null>(null);
const adapt = ref<Adapt | null>(null);
const busy = ref(false);
const measuring = ref(false);
const drafting = ref(false);
const adaptError = ref("");

const showAdapt = computed(
  () => model.value?.source === "student" && model.value?.status === "cannot_start",
);
const canMeasure = computed(() => Boolean(model.value?.perf?.can_measure) && !measuring.value);
const latencyText = computed(() => {
  const perf = model.value?.perf;
  const ms = formatLatencyMs(perf?.latency_ms_per_image);
  if (ms === "未测量" || !perf) return ms;
  return `${ms}（${perf.device} · dummy ${perf.input_h}×${perf.input_w}）`;
});
const fpsText = computed(() => {
  const perf = model.value?.perf;
  const fps = formatFps(perf?.fps_per_image);
  if (fps === "未测量" || !perf) return fps;
  return `${fps}（${perf.device} · dummy ${perf.input_h}×${perf.input_w}）`;
});
const envText = computed(() => {
  const env = model.value?.perf?.env;
  if (!env) return "—";
  return [env.platform, env.torch ? `torch ${env.torch}` : "", env.python ? `Python ${env.python}` : ""]
    .filter(Boolean)
    .join(" · ");
});
const measureButtonText = computed(() => {
  const status = model.value?.perf?.status;
  if (status === "queued" || status === "measuring") return "测量中";
  if (status === "success") return "重新测量";
  if (status === "failed") return "重试测量";
  return "测量参数量与耗时";
});

function perfStatusLabel(status: string | undefined): string {
  const map: Record<string, string> = {
    unmeasured: "未测量",
    queued: "排队中",
    measuring: "测量中",
    success: "已完成",
    failed: "失败",
  };
  return map[status ?? ""] ?? status ?? "未测量";
}

watch(
  () => String(route.params.id ?? ""),
  async (id) => {
    if (!id) return;
    measuring.value = false;
    adapt.value = null;
    drafting.value = false;
    adaptError.value = "";
    await refreshCard(id);
    if (model.value?.perf?.status === "queued" || model.value?.perf?.status === "measuring") {
      measuring.value = true;
      await pollUntilMeasured(id);
      if (String(route.params.id ?? "") === id) {
        measuring.value = false;
      }
    }
  },
  { immediate: true },
);

async function refreshCard(id = String(route.params.id ?? "")) {
  if (!id) return;
  try {
    const { data } = await http.get(`/models/${id}`);
    if (String(route.params.id ?? "") !== id) return;
    model.value = data;
    if (data.status === "cannot_start" && data.source === "student") {
      await loadAdapt();
    } else {
      adapt.value = null;
    }
  } catch (error) {
    ElMessage.error(formatError(error));
  }
}

async function loadAdapt() {
  const id = String(route.params.id ?? "");
  if (!id) return;
  // Two phases so the panel never blanks out while the LLM drafts: rules first, then copy.
  adaptError.value = "";
  try {
    const { data } = await http.get(`/models/${id}/adapt`, { params: { llm: false } });
    if (String(route.params.id ?? "") !== id) return;
    adapt.value = data;
  } catch (error) {
    if (String(route.params.id ?? "") !== id) return;
    adapt.value = null;
    adaptError.value = formatError(error);
    return;
  }
  drafting.value = true;
  try {
    const { data } = await http.get(`/models/${id}/adapt`, { params: { llm: true } });
    if (String(route.params.id ?? "") !== id) return;
    adapt.value = data;
  } catch {
    // Keep the rule-only diagnosis already on screen.
  } finally {
    if (String(route.params.id ?? "") === id) drafting.value = false;
  }
}

function goCompare() {
  if (model.value?.source === "student") {
    void router.push({ path: "/compare/new", query: { student: model.value.id } });
    return;
  }
  void router.push({ path: "/compare/new", query: { baseline: model.value?.id } });
}

async function downloadLog() {
  if (!model.value) return;
  try {
    await downloadAuthFile(`/models/${model.value.id}/admit-log`, `${model.value.id}_admit.log`);
  } catch (error) {
    ElMessage.error(formatError(error));
  }
}

async function applyAdapt(consent: boolean) {
  if (!model.value) return;
  try {
    if (consent) {
      await ElMessageBox.confirm(
        "只改适配层（不改原网络、不放宽权重加载），将重跑隔离检查；通过后本版本留在你的模型中心。检查结果以复检为准。",
        "按方案追加并复检",
        { type: "warning", confirmButtonText: "按方案复检", cancelButtonText: "取消" },
      );
    }
    busy.value = true;
    await http.post(`/models/${model.value.id}/adapt`, { consent });
    if (!consent) {
      ElMessage.success("已留下意见，源码未改");
      await loadAdapt();
      return;
    }
    ElMessage.success("已写入适配层，正在复检");
    await pollUntilSettled();
  } catch (error) {
    if (error === "cancel") return;
    ElMessage.error(formatError(error));
  } finally {
    busy.value = false;
  }
}

async function pollUntilSettled() {
  for (let i = 0; i < 120; i += 1) {
    const { data } = await http.get(`/models/${route.params.id}`);
    model.value = data;
    if (data.status !== "checking") break;
    await new Promise((resolve) => setTimeout(resolve, 5000));
  }
  if (model.value?.status === "cannot_start") {
    await loadAdapt();
    return;
  }
  adapt.value = null;
}

async function runMeasure() {
  if (!model.value) return;
  try {
    measuring.value = true;
    const { data } = await http.post(`/models/${model.value.id}/perf`);
    model.value = data;
    await pollUntilMeasured(String(route.params.id ?? ""));
    if (model.value?.perf?.status === "success") {
      ElMessage.success("测量完成");
    } else if (model.value?.perf?.status === "failed") {
      ElMessage.error(model.value.perf.fail_message || "测量失败");
    }
  } catch (error) {
    ElMessage.error(formatError(error));
  } finally {
    measuring.value = false;
  }
}

async function pollUntilMeasured(versionId: string) {
  for (let i = 0; i < 120; i += 1) {
    if (String(route.params.id ?? "") !== versionId) return;
    const { data } = await http.get(`/models/${versionId}`);
    if (String(route.params.id ?? "") !== versionId) return;
    model.value = data;
    const status = data.perf?.status;
    if (status !== "queued" && status !== "measuring") break;
    await new Promise((resolve) => setTimeout(resolve, 3000));
  }
}
</script>

<style scoped>
.eyebrow {
  color: var(--lab-accent-2);
  letter-spacing: 0.16em;
  font-size: 12px;
}
.facts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 12px 24px;
  background: var(--lab-panel);
  border: 1px solid var(--lab-line);
  padding: 20px;
}
.compact {
  margin: 12px 0 0;
}
dt {
  color: var(--lab-muted);
  font-size: 12px;
}
dd {
  margin: 4px 0 0;
}
.mono {
  word-break: break-all;
  font-family: "IBM Plex Sans", sans-serif;
  font-size: 13px;
}
.muted,
ul,
.stages,
.points {
  color: var(--lab-muted);
  line-height: 1.7;
}
.mb {
  margin: 12px 0;
}
.actions,
.adapt-actions {
  display: flex;
  gap: 16px;
  align-items: center;
  margin-top: 24px;
}
.adapt {
  margin-top: 32px;
  padding: 20px;
  background: var(--lab-panel);
  border: 1px solid var(--lab-line);
}
.adapt h3 {
  margin-top: 0;
}
.preview {
  color: var(--lab-accent-2);
  line-height: 1.6;
}
.llm,
.consent {
  color: var(--lab-muted);
  font-size: 13px;
  line-height: 1.6;
}
.diff {
  overflow: auto;
  padding: 12px 16px;
  background: #12171c;
  border: 1px solid var(--lab-line);
  color: #ece7dc;
  font-size: 12px;
  line-height: 1.55;
  white-space: pre-wrap;
}
</style>

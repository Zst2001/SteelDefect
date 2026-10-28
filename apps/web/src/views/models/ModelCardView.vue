<template>
  <div class="model-detail">
    <header class="head">
      <p class="eyebrow">模型卡</p>
      <h1>{{ model?.name ?? "模型详情" }}</h1>
      <p v-if="model" class="model-meta"><span>{{ modelStatusLabel(model.status) }}</span>{{ model.source === "builtin" ? "内置模型" : "学生导入" }} · CPU 部署</p>
    </header>

    <section v-if="loading" class="load-state" role="status" aria-live="polite">
      正在读取模型详情…
    </section>
    <section v-else-if="loadError" class="load-state error-state" role="alert">
      <div><strong>模型详情暂不可用</strong><p>{{ loadError }}</p><p v-if="model">下方保留上次读取的信息，重新加载后可继续操作。</p></div>
      <el-button @click="reloadCard">重新加载</el-button>
    </section>

    <template v-if="model">
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
      <div><dt>预处理</dt><dd>{{ model.preprocess?.name ?? model.preprocess_id }}<template v-if="model.preprocess">（{{ model.preprocess.width }}×{{ model.preprocess.height }}）</template></dd></div>
      <div><dt>参数量</dt><dd>{{ formatParamCount(model.perf?.param_count ?? model.param_count) }}</dd></div>
      <div><dt>权重体积</dt><dd>{{ formatBytes(model.perf?.weight_bytes) }}</dd></div>
      <div><dt>本机前向</dt><dd>{{ latencyText }}</dd></div>
      <div><dt>本机 FPS</dt><dd>{{ fpsText }}</dd></div>
      <div><dt>权重哈希</dt><dd class="mono">{{ model.weight_sha256 ?? "—" }}</dd></div>
      <div><dt>指标来源</dt><dd>{{ model.metrics_source }}</dd></div>
    </dl>

    <section class="adapt model-definition">
      <div>
        <h3>类别映射</h3>
        <ul class="class-map">
          <li v-for="(name, id) in model.class_map" :key="id"><span>{{ id }}</span>{{ name }}</li>
        </ul>
      </div>

      <div>
        <h3>可用可视化</h3>
        <p class="muted">原图、彩色掩码、叠加、边界、拼图。</p>
      </div>
    </section>

    <section v-if="model.source === 'student'" class="adapt">
    <h3>检查工单</h3>
    <ol v-if="model.admit_report?.stages?.length" class="stages">
      <li v-for="step in model.admit_report.stages" :key="step.stage">
        {{ failStageLabel(step.stage) }} · {{ step.ok ? "通过" : "失败" }} · {{ step.message }}
      </li>
    </ol>
    <p v-else class="muted">暂无检查阶段记录。</p>
    </section>

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
        <p v-else-if="adapt.llm_status === 'error'" class="llm">补充说明暂不可用，以下为规则诊断。检查结果仍以隔离复检为准。</p>
        <p v-else-if="adapt.llm_status === 'skipped'" class="llm">当前提供规则诊断，检查结果以隔离复检为准。</p>
        <ul class="points">
          <li v-for="(point, index) in adapt.points" :key="index">{{ point }}</li>
        </ul>
        <pre v-if="adapt.diff" class="diff">{{ adapt.diff }}</pre>
        <p class="consent">{{ adapt.consent_hint }}</p>
        <div class="adapt-actions">
          <el-button type="primary" :disabled="!adapt.can_apply || !canAct || busy" :loading="busy" @click="applyAdapt(true)">
            按方案追加并复检
          </el-button>
          <el-button :disabled="busy || !canAct" @click="applyAdapt(false)">不改代码只留意见</el-button>
        </div>
        <p v-if="!adapt.can_apply" class="muted">{{ adapt.apply_blocked_reason }}</p>
      </template>
    </section>

    <section class="adapt">
      <h3>参数量与本机耗时</h3>
      <p class="muted">{{ model.perf?.disclaimer }}</p>
      <dl class="facts compact">
        <div><dt>测量状态</dt><dd>{{ perfStatusLabel(model.perf?.status) }}</dd></div>
        <div><dt>协议</dt><dd v-if="model.perf">{{ model.perf.device }} · {{ model.perf.input_kind }} · {{ model.perf.input_h }}×{{ model.perf.input_w }} · batch {{ model.perf.batch }} · 预热 {{ model.perf.warmup_runs }} / 计时 {{ model.perf.timed_runs }}</dd><dd v-else>尚无测量记录</dd></div>
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
      <el-button type="primary" :disabled="!model.runnable_here || !canAct" @click="goCompare">加入缺陷分割</el-button>
      <el-button v-if="model.log_available" :loading="downloading" :disabled="!canAct" @click="downloadLog">下载检查日志</el-button>
    </div>
    </template>
    <router-link class="back-link" to="/models">返回模型列表</router-link>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
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
const loading = ref(false);
const loadError = ref("");
const downloading = ref(false);
let generation = 0;
let disposed = false;
let adaptRequest = 0;
let cancelWait: (() => void) | undefined;
type RequestContext = { id: string; generation: number };

function current(context: RequestContext): boolean {
  return !disposed && context.generation === generation && context.id === String(route.params.id ?? "");
}

function contextNow(): RequestContext {
  return { id: String(route.params.id ?? ""), generation };
}

const canAct = computed(() => !loading.value && !loadError.value);

const showAdapt = computed(
  () => model.value?.source === "student" && model.value?.status === "cannot_start",
);
const canMeasure = computed(() => canAct.value && Boolean(model.value?.runnable_here && model.value?.perf?.can_measure)
  && !measuring.value && !busy.value && model.value?.status !== "checking"
  && !["queued", "measuring"].includes(model.value?.perf?.status ?? ""));
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

function hasPendingWork(card: Card | null): boolean {
  return card?.status === "checking" || ["queued", "measuring"].includes(card?.perf?.status ?? "");
}

function waitForPoll(context: RequestContext, ms: number): Promise<boolean> {
  if (!current(context)) return Promise.resolve(false);
  return new Promise((resolve) => {
    const finish = (ready: boolean) => {
      clearTimeout(timer);
      if (cancelWait === cancel) cancelWait = undefined;
      resolve(ready && current(context));
    };
    const cancel = () => finish(false);
    const timer = setTimeout(() => finish(true), ms);
    cancelWait = cancel;
  });
}

async function readCard(context: RequestContext): Promise<boolean> {
  try {
    const { data } = await http.get(`/models/${context.id}`);
    if (!current(context)) return false;
    model.value = data;
    loadError.value = "";
    return true;
  } catch (error) {
    if (current(context)) loadError.value = formatError(error);
    return false;
  }
}

async function pollUntilIdle(context: RequestContext) {
  for (let i = 0; i < 120 && current(context) && hasPendingWork(model.value); i += 1) {
    const delay = model.value?.status === "checking" ? 5000 : 3000;
    if (!await waitForPoll(context, delay) || !await readCard(context)) return;
  }
  if (!current(context)) return;
  if (hasPendingWork(model.value)) {
    loadError.value = "状态刷新已暂停，请重新加载查看最新结果。";
    return;
  }
  if (showAdapt.value) await loadAdapt(context);
  else adapt.value = null;
}

async function openCard(id: string, clear = true) {
  generation += 1;
  cancelWait?.();
  const context = contextNow();
  if (!id || !current(context)) return;
  if (clear) model.value = null;
  busy.value = false;
  measuring.value = false;
  downloading.value = false;
  drafting.value = false;
  adapt.value = null;
  adaptError.value = "";
  loadError.value = "";
  loading.value = true;
  if (!await readCard(context)) {
    if (current(context)) loading.value = false;
    return;
  }
  if (!current(context)) return;
  loading.value = false;
  measuring.value = ["queued", "measuring"].includes(model.value?.perf?.status ?? "");
  if (hasPendingWork(model.value)) await pollUntilIdle(context);
  else if (showAdapt.value) await loadAdapt(context);
  if (current(context)) measuring.value = false;
}

function reloadCard() {
  if (loading.value) return;
  void openCard(String(route.params.id ?? ""), false);
}

watch(() => String(route.params.id ?? ""), (id) => { void openCard(id); }, { immediate: true });
onBeforeUnmount(() => {
  disposed = true;
  generation += 1;
  cancelWait?.();
});

async function loadAdapt(context: RequestContext) {
  if (!current(context)) return;
  const request = ++adaptRequest;
  const isLatest = () => current(context) && request === adaptRequest;
  // Two phases keep rule diagnostics visible while the existing explanation is drafted.
  adaptError.value = "";
  try {
    const { data } = await http.get(`/models/${context.id}/adapt`, { params: { llm: false } });
    if (!isLatest()) return;
    adapt.value = data;
  } catch (error) {
    if (!isLatest()) return;
    adapt.value = null;
    adaptError.value = formatError(error);
    return;
  }
  drafting.value = true;
  try {
    const { data } = await http.get(`/models/${context.id}/adapt`, { params: { llm: true } });
    if (isLatest()) adapt.value = data;
  } catch {
    // Keep the rule-only diagnosis already on screen.
  } finally {
    if (isLatest()) drafting.value = false;
  }
}

function goCompare() {
  if (!canAct.value || !model.value?.runnable_here) return;
  if (model.value.source === "student") {
    void router.push({ path: "/compare/new", query: { student: model.value.id } });
    return;
  }
  void router.push({ path: "/compare/new", query: { baseline: model.value.id } });
}

async function downloadLog() {
  if (!model.value || !canAct.value || downloading.value) return;
  const context = contextNow();
  const id = model.value.id;
  downloading.value = true;
  try {
    await downloadAuthFile(`/models/${id}/admit-log`, `${id}_admit.log`);
  } catch (error) {
    if (current(context)) ElMessage.error(formatError(error));
  } finally {
    if (current(context)) downloading.value = false;
  }
}

async function applyAdapt(consent: boolean) {
  if (!model.value || !showAdapt.value || !canAct.value || busy.value || (consent && !adapt.value?.can_apply)) return;
  const context = contextNow();
  const id = model.value.id;
  // Lock before the confirmation dialog so another click cannot create a second submission.
  busy.value = true;
  try {
    if (consent) {
      await ElMessageBox.confirm(
        "只改适配层（不改原网络、不放宽权重加载），将重跑隔离检查；通过后本版本留在你的模型中心。检查结果以复检为准。",
        "按方案追加并复检",
        { type: "warning", confirmButtonText: "按方案复检", cancelButtonText: "取消" },
      );
    }
    if (!current(context)) return;
    adaptRequest += 1;
    drafting.value = false;
    await http.post(`/models/${id}/adapt`, { consent });
    if (!current(context)) return;
    if (!consent) {
      ElMessage.success("已留下意见，源码未改");
      await loadAdapt(context);
      return;
    }
    ElMessage.success("已写入适配层，正在复检");
    if (await readCard(context)) await pollUntilIdle(context);
  } catch (error) {
    if (error === "cancel" || error === "close" || !current(context)) return;
    ElMessage.error(formatError(error));
  } finally {
    if (current(context)) busy.value = false;
  }
}

async function runMeasure() {
  if (!model.value || !canMeasure.value) return;
  const context = contextNow();
  const id = model.value.id;
  measuring.value = true;
  try {
    const { data } = await http.post(`/models/${id}/perf`);
    if (!current(context)) return;
    model.value = data;
    await pollUntilIdle(context);
    if (!current(context) || loadError.value) return;
    if (model.value?.perf?.status === "success") {
      ElMessage.success("测量完成");
    } else if (model.value?.perf?.status === "failed") {
      ElMessage.error(model.value.perf.fail_message || "测量失败");
    }
  } catch (error) {
    if (current(context)) ElMessage.error(formatError(error));
  } finally {
    if (current(context)) measuring.value = false;
  }
}
</script>

<style scoped>
.eyebrow {
  color: var(--lab-accent-2);
  letter-spacing: 0.16em;
  font-size: 12px;
}
.model-detail { max-width: 1500px; }
.head h1 { overflow-wrap: anywhere; }
.model-meta { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; color: var(--lab-muted); }
.model-meta span { padding: 3px 10px; border: 1px solid #d2e0f3; border-radius: 6px; color: #24548c; background: #edf4ff; font-size: 14px; }
.load-state { display: flex; align-items: center; justify-content: space-between; gap: 18px; margin: 20px 0; padding: 22px; background: var(--lab-panel); border: 1px solid var(--lab-line); border-radius: 12px; color: var(--lab-muted); }
.load-state strong { color: var(--lab-text); }
.load-state p { margin: 8px 0 0; line-height: 1.65; overflow-wrap: anywhere; }
.error-state { border-color: #ead9cf; background: #fffaf7; }
.facts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 260px), 1fr));
  gap: 20px 28px;
  background: var(--lab-panel);
  border: 1px solid var(--lab-line);
  border-radius: 12px;
  padding: 24px;
}
.facts > div { min-width: 0; }
.compact {
  margin: 18px 0 0;
  padding: 18px;
  background: #f7f9fd;
}
dt {
  color: var(--lab-muted);
  font-size: 14px;
}
dd {
  margin: 7px 0 0;
  line-height: 1.65;
  overflow-wrap: anywhere;
  font-variant-numeric: tabular-nums;
}
.mono {
  word-break: break-all;
  font-family: var(--lab-font-mono);
  font-size: 14px;
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
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  margin-top: 20px;
}
.actions :deep(.el-button + .el-button), .adapt-actions :deep(.el-button + .el-button) { margin-left: 0; }
.adapt {
  margin-top: 20px;
  padding: 24px;
  background: var(--lab-panel);
  border: 1px solid var(--lab-line);
  border-radius: 12px;
}
.adapt h3 {
  margin-top: 0;
}
.model-definition { display: grid; grid-template-columns: 1fr 1fr; gap: 28px; }
.model-definition > div { min-width: 0; }
.model-definition p { margin-bottom: 0; }
.class-map { display: flex; flex-wrap: wrap; gap: 10px; list-style: none; padding: 0; margin: 0; }
.class-map li { display: flex; align-items: center; gap: 9px; border: 1px solid #dce5f0; border-radius: 7px; padding: 6px 12px; color: #344e6d; font-size: 15px; }
.class-map li span { color: #235991; font-family: var(--lab-font-mono); font-size: 14px; }
.stages { padding-left: 22px; margin-bottom: 0; overflow-wrap: anywhere; }
.stages li + li { margin-top: 10px; }
.preview {
  color: var(--lab-accent-2);
  line-height: 1.6;
}
.llm,
.consent {
  color: var(--lab-muted);
  font-size: 15px;
  line-height: 1.6;
}
.diff {
  overflow: auto;
  padding: 12px 16px;
  background: var(--lab-well);
  border: 1px solid var(--lab-line);
  color: var(--lab-text);
  border-radius: 8px;
  font-size: 14px;
  line-height: 1.55;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.back-link { display: inline-block; margin-top: 22px; color: var(--lab-fiducial); font-size: 15px; }
@media (max-width: 760px) {
  .model-definition { grid-template-columns: minmax(0, 1fr); gap: 22px; }
  .facts, .adapt { padding: 20px; }
  .load-state { align-items: flex-start; flex-direction: column; }
}
@media (max-width: 480px) {
  .facts, .adapt { padding: 17px; }
  .compact { padding: 14px; }
  .actions, .adapt-actions { align-items: stretch; flex-direction: column; }
}
</style>

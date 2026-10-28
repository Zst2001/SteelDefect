<template>
  <div class="perf-page">
    <header class="head">
      <p class="eyebrow">模型中心</p>
      <h1>模型测评</h1>
      <p>测量已检查通过的学生模型参数量与本机前向，选择内置 baseline 作为对照。</p>
    </header>

    <div class="protocol-note"><el-icon><InfoFilled /></el-icon><div><strong>本机 CPU · dummy 输入 · 版本声明尺寸</strong><p>FPS = 1000 / ms/图，不是论文 GPU FPS，也不是测试集指标。任务由实验室 worker 串行执行，网站进程不 import 学生源码。</p></div></div>

    <div v-if="listError" class="load-state error-state" role="alert"><el-icon><WarningFilled /></el-icon><div><strong>{{ loaded ? '测参档案更新失败' : '模型目录暂不可用' }}</strong><p>{{ listError }}{{ loaded ? ' 当前保留上次加载的档案，请重新加载后查看最新状态。' : '' }}</p></div><el-button :loading="loading" @click="retryList">重新加载</el-button></div>
    <div v-else-if="loading && !loaded" class="load-state" role="status"><el-icon><Box /></el-icon><div><strong>正在读取模型与测参档案</strong><p>正在获取可访问的模型版本。</p></div></div>
    <template v-if="loaded">
    <div class="selection-grid">
      <section class="block selection-panel">
        <div class="block-head"><div><h2><span class="section-icon"><el-icon><Box /></el-icon></span>我的导入 / 课题组共享</h2><p>一次最多选择 3 个学生模型</p></div><span class="selection-count">{{ selectedStudents.length }} / 3</span></div>
        <div v-if="!students.length" class="empty-state"><span class="empty-icon"><el-icon><Box /></el-icon></span><h3>暂无可运行的学生模型</h3><p>请先<router-link to="/models/import">导入 .py + .pth</router-link>并通过隔离检查。</p></div>
        <el-checkbox-group v-else v-model="selectedStudents" class="model-options">
          <el-checkbox v-for="model in students" :key="model.id" :label="model.id" :disabled="!model.runnable_here" class="model-option">
            <span class="option-name">{{ model.name }}</span>
            <span class="meta">{{ model.source === "student" && model.owner_id !== meId ? "共享" : "我的" }} · {{ modelStatusLabel(model.status) }}</span>
            <span class="option-stats">{{ formatParamCount(model.param_count) }} · {{ formatFps(model.fps_per_image) }}</span>
          </el-checkbox>
        </el-checkbox-group>
      </section>

      <section class="block selection-panel">
        <div class="block-head"><div><h2><span class="section-icon"><el-icon><Box /></el-icon></span>内置对照</h2><p>选择本机可运行的内置模型，数量不限</p></div><el-button link type="primary" @click="toggleAllBuiltins">{{ allBuiltinsSelected ? "取消全选" : "全选" }}</el-button></div>
        <el-checkbox-group v-model="selectedBuiltins" class="model-options">
          <el-checkbox v-for="model in builtins" :key="model.id" :label="model.id" :disabled="!model.runnable_here" class="model-option">
            <span class="option-name">{{ model.name }}</span>
            <span class="meta">{{ model.slug }}</span>
            <span class="option-stats">{{ formatFps(model.fps_per_image) }}</span>
          </el-checkbox>
        </el-checkbox-group>
      </section>
    </div>

    <div class="toolbar">
      <div class="selection-summary"><strong>已选 {{ selectedIds.length }} 个模型</strong><span>学生模型 {{ selectedStudents.length }} 个 · 内置对照 {{ selectedBuiltins.length }} 个</span></div>
      <div class="toolbar-actions"><router-link to="/models">返回模型库</router-link><el-button type="primary" :loading="busy" :disabled="!canMeasure" @click="runSelected"><el-icon><DataAnalysis /></el-icon>测量所选</el-button></div>
    </div>
    <p v-if="error" class="err" role="alert">{{ error }}</p>

    <section class="block results-panel">
      <div class="block-head"><div><h2><span class="section-icon"><el-icon><DataAnalysis /></el-icon></span>测量结果</h2><p>展示当前所选模型的测参档案，运行状态以实际返回为准</p></div></div>
      <el-table v-if="tableRows.length" :data="tableRows" size="small" class="table">
        <el-table-column label="模型" min-width="160"><template #default="{ row }"><router-link class="model-link" :to="`/models/${row.id}`">{{ row.name }}</router-link></template></el-table-column>
        <el-table-column label="来源" width="90"><template #default="{ row }">{{ row.source === "builtin" ? "内置" : "学生" }}</template></el-table-column>
        <el-table-column label="参数量" width="110"><template #default="{ row }">{{ formatParamCount(row.param_count) }}</template></el-table-column>
        <el-table-column label="本机前向" width="130"><template #default="{ row }">{{ formatLatencyMs(row.perf?.latency_ms_per_image) }}</template></el-table-column>
        <el-table-column label="本机 FPS" width="120"><template #default="{ row }">{{ formatFps(row.fps_per_image) }}</template></el-table-column>
        <el-table-column label="尺寸" width="110"><template #default="{ row }">{{ sizeText(row) }}</template></el-table-column>
        <el-table-column label="设备" width="80"><template #default="{ row }">{{ row.perf?.device ?? "cpu" }}</template></el-table-column>
        <el-table-column label="状态" width="100"><template #default="{ row }"><span class="perf-status">{{ perfStatusLabel(row.perf?.status) }}</span></template></el-table-column>
        <el-table-column label="测量时间" min-width="180"><template #default="{ row }">{{ row.perf?.measured_at ?? "—" }}</template></el-table-column>
      </el-table>
      <div v-else class="empty-state result-empty"><span class="empty-icon"><el-icon><DataAnalysis /></el-icon></span><h3>选择模型，查看测参档案</h3><p>勾选后显示所选模型的已有结果；点击“测量所选”可提交新的本机测量。</p></div>
    </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { Box, DataAnalysis, InfoFilled, WarningFilled } from "@element-plus/icons-vue";
import { formatError, http } from "../../api/http";
import { formatFps, formatLatencyMs, formatParamCount, modelStatusLabel, perfStatusLabel } from "../../api/labels";

type Perf = {
  status?: string;
  can_measure?: boolean;
  latency_ms_per_image?: number | null;
  device?: string;
  measured_at?: string | null;
  fail_message?: string | null;
  input_h?: number;
  input_w?: number;
};

type Card = {
  id: string;
  name: string;
  slug: string;
  source: string;
  status: string;
  owner_id?: string | null;
  requires_cuda: boolean;
  runnable_here: boolean;
  param_count?: number | null;
  fps_per_image?: number | null;
  input_size?: number[];
  perf?: Perf | null;
};

const STUDENT_LIMIT = 3;

const meId = ref<string | null>(null);
const builtins = ref<Card[]>([]);
const students = ref<Card[]>([]);
const selectedStudents = ref<string[]>([]);
const selectedBuiltins = ref<string[]>([]);
const busy = ref(false);
const error = ref("");
const listError = ref("");
const loading = ref(true);
const loaded = ref(false);
let disposed = false;
let polling = false;
let pollTimer: number | null = null;

const selectedIds = computed(() => [...selectedStudents.value, ...selectedBuiltins.value]);
const canMeasure = computed(() => selectedIds.value.length >= 1 && !busy.value && !loading.value && !listError.value);
const runnableBuiltinIds = computed(() => builtins.value.filter((row) => row.runnable_here).map((row) => row.id));
const allBuiltinsSelected = computed(
  () => runnableBuiltinIds.value.length > 0 && runnableBuiltinIds.value.every((id) => selectedBuiltins.value.includes(id)),
);

const tableRows = computed(() => {
  const wanted = new Set(selectedIds.value);
  return [...students.value, ...builtins.value].filter((row) => wanted.has(row.id));
});

onMounted(async () => {
  try {
    const me = await http.get("/auth/me");
    meId.value = me.data.id ?? null;
  } catch {
    meId.value = null;
  }
  if (!disposed) await loadList();
});

onUnmounted(() => { disposed = true; stopPoll(); });

watch(selectedStudents, (ids) => {
  if (ids.length > STUDENT_LIMIT) {
    selectedStudents.value = ids.slice(0, STUDENT_LIMIT);
    ElMessage.warning(`学生模型一次最多 ${STUDENT_LIMIT} 个`);
  }
});

function toggleAllBuiltins() {
  if (allBuiltinsSelected.value) {
    selectedBuiltins.value = [];
    return;
  }
  selectedBuiltins.value = [...runnableBuiltinIds.value];
}

function sizeText(row: Card): string {
  const h = row.perf?.input_h ?? row.input_size?.[0];
  const w = row.perf?.input_w ?? row.input_size?.[1];
  if (!h || !w) return "—";
  return `${h}×${w}`;
}

async function loadList(): Promise<boolean> {
  loading.value = true;
  listError.value = "";
  try {
    const { data } = await http.get("/models");
    if (disposed) return false;
    builtins.value = (data.builtins ?? []) as Card[];
    const mine = (data.mine ?? []) as Card[];
    const shared = (data.shared ?? []) as Card[];
    students.value = [...mine, ...shared];
    loaded.value = true;
    return true;
  } catch (err) {
    if (!disposed) listError.value = formatError(err);
    return false;
  } finally {
    loading.value = false;
  }
}

async function retryList() {
  if (loading.value) return;
  if (await loadList()) {
    const watching = tableRows.value;
    if (anyInFlight(watching)) startPoll();
  }
}

function startPoll() {
  stopPoll();
  if (!disposed) pollTimer = window.setInterval(() => { void pollUntilIdle(); }, 3000);
}

function stopPoll() {
  if (pollTimer != null) {
    window.clearInterval(pollTimer);
    pollTimer = null;
  }
}

function anyInFlight(rows: Card[]): boolean {
  return rows.some((row) => row.perf?.status === "queued" || row.perf?.status === "measuring");
}

async function runSelected() {
  if (!canMeasure.value) return;
  error.value = "";
  if (selectedStudents.value.length > STUDENT_LIMIT) {
    ElMessage.warning(`学生模型一次最多 ${STUDENT_LIMIT} 个`);
    return;
  }
  const ids = selectedIds.value;
  if (!ids.length) return;
  const lookup = new Map([...students.value, ...builtins.value].map((row) => [row.id, row]));
  const blocked = ids.filter((id) => !lookup.get(id)?.runnable_here);
  if (blocked.length) {
    error.value = "只能测量检查通过且当前环境可运行的模型。";
    return;
  }
  busy.value = true;
  try {
    for (const id of ids) {
      await http.post(`/models/${id}/perf`);
    }
    ElMessage.success("已入队，正在测量");
    if (await loadList()) {
      startPoll();
      await pollUntilIdle();
    }
  } catch (err) {
    error.value = formatError(err);
  } finally {
    busy.value = false;
  }
}

async function pollUntilIdle() {
  if (polling || disposed) return;
  polling = true;
  try {
    if (!await loadList()) {
      stopPoll();
      return;
    }
    if (!anyInFlight(tableRows.value)) stopPoll();
  } finally {
    polling = false;
  }
}
</script>

<style scoped>
.perf-page { min-width: 0; }
.eyebrow { color: var(--lab-accent-2); letter-spacing: .14em; font-size: 14px; margin: 0 0 9px; }
.head h1 { margin: 0 0 10px; }
.head > p:last-child { color: var(--lab-muted); font-size: 16px; line-height: 1.8; margin: 0; }
.protocol-note { display: flex; align-items: flex-start; gap: 11px; margin: 23px 0; padding: 16px 18px; border: 1px solid #dce8f7; border-radius: 9px; background: #f0f6ff; color: #617e9f; }
.protocol-note > .el-icon { flex-shrink: 0; margin-top: 2px; color: #5689cf; font-size: 20px; }
.protocol-note strong { display: block; color: #456e9e; font-size: 16px; font-weight: 500; }
.protocol-note p { font-size: 15px; line-height: 1.8; margin: 6px 0 0; }
.selection-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 20px; }
.block { min-width: 0; border: 1px solid #e0e8f3; border-radius: 12px; background: #fff; }
.selection-panel { padding: 22px; }
.block-head { display: flex; justify-content: space-between; align-items: center; gap: 15px; margin-bottom: 20px; }
.block-head h2 { display: flex; align-items: center; gap: 9px; color: #2b4462; font-size: 19px; margin: 0; line-height: 1.5; }
.block-head p { color: #5c7089; font-size: 14px; line-height: 1.7; margin: 8px 0 0; }
.section-icon { display: inline-flex; align-items: center; justify-content: center; flex-shrink: 0; width: 29px; height: 29px; border-radius: 7px; color: #4f82cc; background: #edf4ff; font-size: 20px; }
.selection-count { flex-shrink: 0; padding: 5px 8px; color: #7893b7; background: #f0f5fb; border-radius: 5px; font-size: 14px; }
.model-options { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.model-option { display: flex; align-items: flex-start; width: 100%; min-width: 0; height: auto; margin: 0; padding: 15px 13px; border: 1px solid #e4ebf4; border-radius: 8px; background: #fcfdff; white-space: normal; box-sizing: border-box; }
.model-option:hover:not(.is-disabled), .model-option:focus-within { border-color: #93b5e4; }
.model-option.is-checked { border-color: #3979df; background: #f0f5ff; }
.model-option.is-disabled { border-color: #e9edf3; background: #f7f8fa; }
.model-option :deep(.el-checkbox__input) { margin-top: 4px; }
.model-option :deep(.el-checkbox__label) { display: flex; flex-direction: column; min-width: 0; width: 100%; padding-left: 9px; overflow-wrap: anywhere; }
.option-name { color: #385475; font-size: 17px; font-weight: 500; line-height: 1.6; }
.meta { display: block; color: #5c7089; font-size: 14px; line-height: 1.7; margin-top: 4px; }
.option-stats { color: #5c7089; font-size: 14px; line-height: 1.7; margin-top: 6px; }
.model-option.is-disabled .option-name, .model-option.is-disabled .meta, .model-option.is-disabled .option-stats { color: #a0acbc; }
.toolbar { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 18px; padding: 20px 23px; margin: 18px 0 24px; border: 1px solid #e0e8f3; border-radius: 10px; background: #fff; }
.selection-summary { display: flex; flex-direction: column; gap: 6px; }
.selection-summary strong { color: #486482; font-size: 16px; font-weight: 500; }
.selection-summary span { color: #5c7089; font-size: 14px; }
.toolbar-actions { display: flex; align-items: center; flex-wrap: wrap; gap: 20px; }
.toolbar-actions a { color: #6b86a9; font-size: 16px; text-decoration: none; }
.toolbar-actions .el-button { min-height: 38px; padding: 0 18px; font-size: 16px; }
.toolbar-actions .el-icon { margin-right: 7px; }
.err { padding: 12px 15px; margin: -6px 0 20px; border-radius: 8px; color: var(--lab-danger); background: #fff3f1; font-size: 16px; line-height: 1.7; }
.results-panel { overflow: hidden; }
.results-panel > .block-head { padding: 22px 24px; margin: 0; }
.table { width: 100%; }
.table :deep(th.el-table__cell) { height: 44px; color: #758aa6; background: #f4f7fc; font-size: 14px; font-weight: 500; border-top: 1px solid #eaf0f7; }
.table :deep(td.el-table__cell) { padding: 16px 0; color: #5f7797; font-size: 15px; }
.table :deep(.cell) { padding-left: 18px; padding-right: 12px; }
.model-link { color: #4578bc; font-size: 16px; text-decoration: none; }
.perf-status { display: inline-block; padding: 3px 7px; border-radius: 5px; background: #f1f5fa; color: #6c84a3; font-size: 14px; }
.empty-state { display: flex; align-items: center; flex-direction: column; justify-content: center; min-height: 180px; padding: 22px 12px; text-align: center; }
.empty-icon { display: inline-flex; align-items: center; justify-content: center; width: 48px; height: 48px; border-radius: 12px; color: #a0b6d3; background: #f1f6fc; font-size: 28px; margin-bottom: 14px; }
.empty-state h3 { margin: 0 0 8px; color: #5d7697; font-size: 17px; font-weight: 500; }
.empty-state p { margin: 0; color: #5c7089; font-size: 16px; line-height: 1.8; }
.empty-state a { margin: 0 5px; color: #5486c8; text-decoration: none; }
.result-empty { padding: 30px 20px 38px; }
a:focus-visible { outline: 2px solid #3979ef; outline-offset: 4px; }
@media (max-width: 1250px) { .model-options { grid-template-columns: minmax(0, 1fr); } }
@media (max-width: 850px) { .selection-grid { grid-template-columns: minmax(0, 1fr); } .model-options { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 560px) { .selection-panel { padding: 18px; } .model-options { grid-template-columns: minmax(0, 1fr); } .block-head { align-items: flex-start; gap: 10px; } .block-head h2 { font-size: 18px; } .toolbar { align-items: flex-start; padding: 18px; } .toolbar-actions { width: 100%; justify-content: space-between; gap: 12px; } .results-panel > .block-head { padding: 18px; } .protocol-note { padding: 14px; } }

.load-state { display: flex; align-items: center; gap: 14px; padding: 24px; margin: 20px 0 28px; border: 1px solid #dce5f1; border-radius: 12px; background: #fff; color: #4f627b; }
.load-state > .el-icon { flex: none; font-size: 24px; color: #3f72bd; }
.load-state > div { flex: 1; min-width: 0; }
.load-state strong { color: #263f5d; font-size: 16px; font-weight: 600; }
.load-state p { margin: 6px 0 0; line-height: 1.7; font-size: 14px; overflow-wrap: anywhere; }
.load-state.error-state { background: #fffaf7; border-color: #ead9cf; }
.load-state.error-state > .el-icon { color: #9b6243; }
.load-state .el-button { flex: none; }
@media (max-width: 560px) { .load-state { flex-wrap: wrap; padding: 19px; }.load-state .el-button { margin-left: 38px; } }
</style>

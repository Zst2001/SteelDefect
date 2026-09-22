<template>
  <div>
    <header class="head">
      <p class="eyebrow">模型中心</p>
      <h1>模型测评</h1>
      <p>
        对学生已导入且检查通过的模型测量参数量与本机前向。内置 baseline 可全选作对照。协议为本机 CPU、dummy
        输入、版本声明尺寸；FPS = 1000 / ms/图，不是论文 GPU FPS，也不是测试集指标。
      </p>
    </header>

    <p class="muted">一次最多勾选 3 个学生模型；内置对照不限数量，可全选。测量入队后由实验室 worker 串行执行，网站进程不 import 学生源码。</p>

    <section class="block">
      <h2>我的导入 / 课题组共享</h2>
      <p v-if="!students.length" class="empty">
        还没有可运行的学生模型。请先
        <router-link to="/models/import">导入 .py + .pth</router-link>
        并通过隔离检查。
      </p>
      <el-checkbox-group v-else v-model="selectedStudents">
        <el-checkbox
          v-for="model in students"
          :key="model.id"
          :label="model.id"
          :disabled="!model.runnable_here"
        >
          {{ model.name }}
          <span class="meta">
            {{ model.source === "student" && model.owner_id !== meId ? "共享" : "我的" }}
            · {{ modelStatusLabel(model.status) }}
            · {{ formatParamCount(model.param_count) }}
            · {{ formatFps(model.fps_per_image) }}
          </span>
        </el-checkbox>
      </el-checkbox-group>
    </section>

    <section class="block">
      <div class="block-head">
        <h2>内置对照</h2>
        <el-button link type="primary" @click="toggleAllBuiltins">{{ allBuiltinsSelected ? "取消全选" : "全选" }}</el-button>
      </div>
      <el-checkbox-group v-model="selectedBuiltins">
        <el-checkbox
          v-for="model in builtins"
          :key="model.id"
          :label="model.id"
          :disabled="!model.runnable_here"
        >
          {{ model.name }}
          <span class="meta">{{ model.slug }} · {{ formatFps(model.fps_per_image) }}</span>
        </el-checkbox>
      </el-checkbox-group>
    </section>

    <div class="toolbar">
      <el-button type="primary" :loading="busy" :disabled="!canMeasure" @click="runSelected">
        测量所选
      </el-button>
      <router-link to="/models">返回模型库</router-link>
    </div>
    <p v-if="error" class="err">{{ error }}</p>

    <section class="block">
      <h2>测量结果</h2>
      <el-table v-if="tableRows.length" :data="tableRows" size="small" class="table">
        <el-table-column label="模型" min-width="160">
          <template #default="{ row }">
            <router-link :to="`/models/${row.id}`">{{ row.name }}</router-link>
          </template>
        </el-table-column>
        <el-table-column label="来源" width="90">
          <template #default="{ row }">{{ row.source === "builtin" ? "内置" : "学生" }}</template>
        </el-table-column>
        <el-table-column label="参数量" width="110">
          <template #default="{ row }">{{ formatParamCount(row.param_count) }}</template>
        </el-table-column>
        <el-table-column label="本机前向" width="130">
          <template #default="{ row }">{{ formatLatencyMs(row.perf?.latency_ms_per_image) }}</template>
        </el-table-column>
        <el-table-column label="本机 FPS" width="120">
          <template #default="{ row }">{{ formatFps(row.fps_per_image) }}</template>
        </el-table-column>
        <el-table-column label="尺寸" width="110">
          <template #default="{ row }">{{ sizeText(row) }}</template>
        </el-table-column>
        <el-table-column label="设备" width="80">
          <template #default="{ row }">{{ row.perf?.device ?? "cpu" }}</template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">{{ perfStatusLabel(row.perf?.status) }}</template>
        </el-table-column>
        <el-table-column label="测量时间" min-width="160">
          <template #default="{ row }">{{ row.perf?.measured_at ?? "—" }}</template>
        </el-table-column>
      </el-table>
      <p v-else class="empty">勾选模型并测量后，结果会出现在这里。已有档案的模型刷新后也会列入表中。</p>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { ElMessage } from "element-plus";
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
let pollTimer: number | null = null;

const selectedIds = computed(() => [...selectedStudents.value, ...selectedBuiltins.value]);
const canMeasure = computed(() => selectedIds.value.length >= 1 && !busy.value);
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
  await loadList();
});

onUnmounted(stopPoll);

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

async function loadList() {
  const { data } = await http.get("/models");
  builtins.value = (data.builtins ?? []) as Card[];
  const mine = (data.mine ?? []) as Card[];
  const shared = (data.shared ?? []) as Card[];
  students.value = [...mine, ...shared];
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
    await loadList();
    stopPoll();
    pollTimer = window.setInterval(() => {
      void pollUntilIdle();
    }, 3000);
    await pollUntilIdle();
  } catch (err) {
    error.value = formatError(err);
  } finally {
    busy.value = false;
  }
}

async function pollUntilIdle() {
  await loadList();
  const watching = [...students.value, ...builtins.value].filter((row) => selectedIds.value.includes(row.id));
  if (!anyInFlight(watching)) {
    stopPoll();
  }
}
</script>

<style scoped>
.eyebrow {
  color: var(--lab-accent-2);
  letter-spacing: 0.16em;
  font-size: 12px;
}
.head p,
.muted,
.empty,
.meta {
  color: var(--lab-muted);
  line-height: 1.7;
}
.block {
  margin: 28px 0;
}
.block h2 {
  margin-bottom: 12px;
}
.block-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}
.block-head h2 {
  margin: 0;
}
.toolbar {
  display: flex;
  gap: 16px;
  align-items: center;
}
.err {
  color: #c45c4a;
  margin-top: 12px;
}
.meta {
  margin-left: 8px;
  font-size: 13px;
}
.table {
  width: 100%;
}
:deep(.el-checkbox) {
  display: flex;
  align-items: center;
  margin: 0 0 10px;
  height: auto;
  white-space: normal;
}
</style>

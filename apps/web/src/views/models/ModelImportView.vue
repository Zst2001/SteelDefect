<template>
  <div>
    <header class="head">
      <p class="eyebrow">模型中心</p>
      <h1>导入模型</h1>
      <p>只接受单个 .py 与对应 .pth。网站进程不会 import 你的源码；检查在隔离容器中进行。失败即不能启动，没有导师审批环节。</p>
    </header>

    <div class="layout">
      <form class="panel" @submit.prevent="submit">
        <el-form label-position="top">
          <el-form-item label="模型名">
            <el-input v-model="name" maxlength="80" placeholder="例如 残差UNet-实验3" />
          </el-form-item>
          <el-form-item label="入口符号">
            <el-input v-model="entry" placeholder="build_model 或类名" />
          </el-form-item>
          <div class="row">
            <el-form-item label="类别数">
              <el-input-number v-model="numClasses" :min="2" :max="32" />
            </el-form-item>
            <el-form-item label="输入通道">
              <el-input-number v-model="inChannels" :min="1" :max="3" />
            </el-form-item>
          </div>
          <el-form-item>
            <el-checkbox v-model="requiresCuda">必须 CUDA（当前 CPU 环境将直接不能启动）</el-checkbox>
          </el-form-item>
          <el-form-item label="模型源码 .py">
            <input type="file" accept=".py" @change="onPy" />
            <p class="file">{{ pyFile?.name ?? "未选择" }}</p>
          </el-form-item>
          <el-form-item label="权重 .pth">
            <input type="file" accept=".pth,.pt" @change="onPth" />
            <p class="file">{{ pthFile?.name ?? "未选择" }}</p>
          </el-form-item>
        </el-form>
        <p class="locked">预处理锁定为 neu_200（200×200 CLAHE/椒盐），与内置 baseline 对齐。</p>
        <el-button type="primary" native-type="submit" :loading="submitting" :disabled="!canSubmit">开始检查</el-button>
        <p v-if="error" class="err">{{ error }}</p>
      </form>

      <aside class="ticket">
        <p class="ticket-kicker">检查工单</p>
        <ol>
          <li v-for="step in steps" :key="step.stage" :class="{ ok: step.ok === true, bad: step.ok === false, wait: step.ok == null }">
            <span class="stamp">{{ failStageLabel(step.stage) }}</span>
            <span>{{ step.message }}</span>
          </li>
        </ol>
        <p v-if="result" class="status">
          当前状态 <strong>{{ modelStatusLabel(result.status) }}</strong>
          <template v-if="result.fail_stage"> · {{ failStageLabel(result.fail_stage) }}</template>
        </p>
        <router-link v-if="result" :to="`/models/${result.id}`">打开模型卡</router-link>
      </aside>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onUnmounted, ref } from "vue";
import { formatError, http } from "../../api/http";
import { failStageLabel, modelStatusLabel } from "../../api/labels";

type Stage = { stage: string; ok: boolean | null; message: string };
type Card = {
  id: string;
  status: string;
  fail_stage: string | null;
  fail_message: string | null;
  admit_report?: { stages?: Stage[]; message?: string } | null;
};

const name = ref("");
const entry = ref("build_model");
const numClasses = ref(4);
const inChannels = ref(3);
const requiresCuda = ref(false);
const pyFile = ref<File | null>(null);
const pthFile = ref<File | null>(null);
const submitting = ref(false);
const error = ref("");
const result = ref<Card | null>(null);
const steps = ref<Stage[]>([
  { stage: "file", ok: null, message: "类型、大小、哈希" },
  { stage: "static", ok: null, message: "阻断网络 / 子进程 / 动态执行" },
  { stage: "import", ok: null, message: "隔离 import" },
  { stage: "build", ok: null, message: "build_model / 类实例化" },
  { stage: "load", ok: null, message: "strict 加载权重" },
  { stage: "forward", ok: null, message: "dummy 前向 B×C×H×W" },
]);
let timer: number | undefined;

const canSubmit = computed(() => name.value.trim().length > 0 && pyFile.value && pthFile.value);

function onPy(event: Event) {
  const input = event.target as HTMLInputElement;
  pyFile.value = input.files?.[0] ?? null;
}

function onPth(event: Event) {
  const input = event.target as HTMLInputElement;
  pthFile.value = input.files?.[0] ?? null;
}

function applyReport(card: Card) {
  result.value = card;
  const reported = card.admit_report?.stages ?? [];
  if (reported.length) {
    steps.value = reported;
  } else if (card.fail_stage) {
    steps.value = steps.value.map((step) =>
      step.stage === card.fail_stage ? { ...step, ok: false, message: card.fail_message || step.message } : step,
    );
  }
}

async function refresh(id: string) {
  const { data } = await http.get(`/models/${id}`);
  applyReport(data);
  if (!["uploaded", "checking"].includes(data.status) && timer) {
    window.clearInterval(timer);
    timer = undefined;
  }
}

async function submit() {
  if (!pyFile.value || !pthFile.value) return;
  submitting.value = true;
  error.value = "";
  try {
    const form = new FormData();
    form.append("name", name.value.trim());
    form.append("entry_symbol", entry.value.trim() || "build_model");
    form.append("num_classes", String(numClasses.value));
    form.append("in_channels", String(inChannels.value));
    form.append("requires_cuda", requiresCuda.value ? "true" : "false");
    form.append("py_file", pyFile.value);
    form.append("pth_file", pthFile.value);
    const { data } = await http.post("/models/import", form);
    applyReport(data);
    if (["uploaded", "checking"].includes(data.status)) {
      timer = window.setInterval(() => void refresh(data.id), 2000);
    }
  } catch (err) {
    error.value = formatError(err);
  } finally {
    submitting.value = false;
  }
}

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
.file,
.locked,
.status {
  color: var(--lab-muted);
  line-height: 1.6;
}
.layout {
  display: grid;
  grid-template-columns: minmax(280px, 1.1fr) minmax(260px, 0.9fr);
  gap: 24px;
  margin-top: 24px;
}
.panel,
.ticket {
  background: var(--lab-panel);
  border: 1px solid var(--lab-line);
  padding: 20px;
}
.row {
  display: flex;
  gap: 16px;
}
.err {
  color: var(--lab-danger);
  margin-top: 12px;
}
.ticket-kicker {
  color: var(--lab-accent-2);
  letter-spacing: 0.14em;
  font-size: 12px;
  margin: 0 0 12px;
}
ol {
  list-style: none;
  margin: 0;
  padding: 0;
  border-left: 1px solid var(--lab-line);
}
li {
  display: grid;
  grid-template-columns: 92px 1fr;
  gap: 12px;
  padding: 10px 0 10px 16px;
  color: var(--lab-muted);
  position: relative;
}
li::before {
  content: "";
  position: absolute;
  left: -4px;
  top: 16px;
  width: 7px;
  height: 7px;
  background: var(--lab-line);
}
li.ok::before {
  background: var(--neu-patch);
}
li.bad::before {
  background: var(--lab-danger);
}
.stamp {
  color: var(--lab-text);
  font-size: 13px;
}
@media (max-width: 860px) {
  .layout {
    grid-template-columns: 1fr;
  }
}
</style>

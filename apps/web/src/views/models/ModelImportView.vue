<template>
  <div class="import-page">
    <header class="head">
      <p class="eyebrow">模型中心</p>
      <h1>导入学生模型</h1>
      <p>上传模型源码与对应权重，在隔离环境中检查。通过后即可用于钢铁缺陷分割对照。</p>
    </header>

    <div class="layout">
      <form class="panel" @submit.prevent="submit">
        <div class="section-head">
          <span class="section-icon"><el-icon><UploadFilled /></el-icon></span>
          <div><h2>模型与文件</h2><p>选择文件，然后填写模型声明</p></div>
        </div>
        <div class="file-grid">
          <label class="file-drop" :class="{ selected: pyFile }">
            <input type="file" accept=".py" aria-label="模型源码 .py" @change="onPy" />
            <span class="file-icon"><el-icon><Document /></el-icon></span>
            <strong>源码文件 <span>.py</span></strong>
            <span class="file-name">{{ pyFile?.name || "点击选择模型源码" }}</span>
            <small>{{ pyFile ? formatFileSize(pyFile.size) : "单个 Python 文件" }}</small>
            <span class="file-action">{{ pyFile ? "重新选择" : "选择文件" }}</span>
          </label>
          <label class="file-drop" :class="{ selected: pthFile }">
            <input type="file" accept=".pth,.pt" aria-label="模型权重 .pth" @change="onPth" />
            <span class="file-icon weights"><el-icon><Box /></el-icon></span>
            <strong>权重文件 <span>.pth</span></strong>
            <span class="file-name">{{ pthFile?.name || "点击选择对应权重" }}</span>
            <small>{{ pthFile ? formatFileSize(pthFile.size) : "须与模型结构匹配" }}</small>
            <span class="file-action">{{ pthFile ? "重新选择" : "选择文件" }}</span>
          </label>
        </div>
        <div class="declaration-title"><span>模型声明</span><small>与源码中的定义保持一致</small></div>
        <el-form label-position="top">
          <el-form-item label="模型名">
            <el-input v-model="name" maxlength="80" placeholder="例如 残差UNet-实验3" />
          </el-form-item>
          <el-form-item label="入口符号">
            <el-input v-model="entry" placeholder="build_model 或类名" />
          </el-form-item>
          <div class="row">
            <el-form-item label="类别数（含背景）">
              <el-input-number v-model="numClasses" :min="2" :max="32" />
            </el-form-item>
            <el-form-item label="输入通道">
              <el-select v-model="inChannels" aria-label="输入通道"><el-option :value="1" label="1 · 灰度" /><el-option :value="3" label="3 · RGB" /></el-select>
            </el-form-item>
          </div>
          <el-form-item class="cuda-declaration">
            <el-checkbox v-model="requiresCuda">必须 CUDA（当前 CPU 环境将直接不能启动）</el-checkbox>
          </el-form-item>
        </el-form>
        <div class="locked"><el-icon><Lock /></el-icon><div><strong>固定预处理 · neu_200</strong><span>200×200 · CLAHE / 椒盐，与内置 baseline 对齐</span></div></div>
        <div class="form-actions">
          <el-button type="primary" native-type="submit" :loading="submitting" :disabled="!canSubmit"><el-icon><CircleCheck /></el-icon>开始检查</el-button>
          <router-link to="/models">查看模型库 <span>→</span></router-link>
        </div>
        <p v-if="error" class="err">{{ error }}</p>
      </form>

      <aside class="check-column">
        <section class="ticket">
          <div class="section-head">
            <span class="section-icon check"><el-icon><Checked /></el-icon></span>
            <div><h2>检查进度</h2><p>模型可运行性检查</p></div>
            <span class="state-badge">{{ result ? modelStatusLabel(result.status) : "等待上传" }}</span>
          </div>
          <ol class="check-timeline">
            <li v-for="(step, index) in steps" :key="step.stage" :class="{ ok: step.ok === true, bad: step.ok === false, wait: step.ok == null }">
              <span class="stamp">{{ step.ok === true ? "✓" : step.ok === false ? "×" : String(index + 1).padStart(2, '0') }}</span>
              <div><strong>{{ failStageLabel(step.stage) }}</strong><p>{{ step.message }}</p></div>
              <small>{{ step.ok === true ? "通过" : step.ok === false ? "失败" : "待检查" }}</small>
            </li>
          </ol>
          <div class="output-spec"><el-icon><Connection /></el-icon><div><strong>前向输出要求</strong><code>B × C × H × W logits</code><span>输出通道数须与声明类别数一致</span></div></div>
          <p v-if="result?.fail_stage" class="err">失败阶段：{{ failStageLabel(result.fail_stage) }}</p>
          <router-link v-if="result" class="model-link" :to="`/models/${result.id}`">打开模型卡查看检查详情 →</router-link>
        </section>
        <section class="check-note">
          <el-icon><InfoFilled /></el-icon>
          <div><h3>每一项检查都有明确结果</h3><p>源码仅在隔离容器内执行；权重严格加载。检查失败即不能启动，不使用随机权重兜底，也无需导师审批。</p></div>
        </section>
      </aside>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onUnmounted, ref } from "vue";
import { Box, Checked, CircleCheck, Connection, Document, InfoFilled, Lock, UploadFilled } from "@element-plus/icons-vue";
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

function formatFileSize(bytes: number) {
  return bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${(bytes / 1024).toFixed(1)} KB`;
}

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
.eyebrow { margin: 0 0 8px; color: var(--lab-accent-2); font-size: 14px; letter-spacing: .16em; }
.head h1 { margin: 0 0 10px; }
.head > p:last-child { margin: 0; color: var(--lab-muted); line-height: 1.7; }
.layout { display: grid; grid-template-columns: minmax(0, 1.12fr) minmax(0, .88fr); gap: 24px; margin-top: 24px; align-items: start; }
.panel, .ticket { background: var(--lab-panel); border: 1px solid var(--lab-line); border-radius: 14px; box-shadow: 0 4px 20px #24456b06; padding: 24px; min-width: 0; }
.section-head { display: flex; align-items: center; gap: 12px; padding-bottom: 20px; }
.section-head h2 { font-size: 20px; margin: 0 0 5px; }
.section-head p { font-size: 15px; color: var(--lab-muted); margin: 0; }
.section-icon { display: grid; place-items: center; flex: none; width: 39px; height: 39px; border-radius: 10px; background: #edf4ff; color: #286bea; font-size: 24px; }
.section-icon.check { color: #1e927b; background: #eaf8f3; }
.file-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; margin-bottom: 26px; }
.file-drop { position: relative; display: flex; align-items: center; flex-direction: column; min-width: 0; padding: 22px 14px 18px; border: 1px dashed #b8ccea; border-radius: 10px; background: #f8fbff; cursor: pointer; text-align: center; }
.file-drop:hover, .file-drop:focus-within, .file-drop.selected { background: #f0f6ff; border-color: #3979ef; }
.file-drop:focus-within { outline: 2px solid #3979ef; outline-offset: 3px; }
.file-drop input { position: absolute; inset: 0; opacity: 0; width: 100%; height: 100%; cursor: pointer; }
.file-icon { display: grid; place-items: center; width: 46px; height: 50px; font-size: 31px; color: #3b78d6; background: #e7f0ff; border-radius: 10px; margin-bottom: 13px; }
.file-icon.weights { color: #7971c5; background: #eeedfd; }
.file-drop strong { color: var(--lab-text); font-size: 16px; }
.file-drop strong span { color: var(--lab-muted); font-weight: 400; margin-left: 3px; }
.file-name { margin: 10px 0 5px; color: var(--lab-muted); font-size: 15px; overflow-wrap: anywhere; max-width: 100%; }
.file-drop small { color: #8290a5; font-size: 14px; }
.file-action { color: #286bea; border: 1px solid #cdddf6; background: #fff; border-radius: 6px; font-size: 15px; padding: 5px 16px; margin-top: 16px; }
.declaration-title { display: flex; justify-content: space-between; gap: 12px; font-size: 16px; font-weight: 600; border-bottom: 1px solid var(--lab-line); padding-bottom: 13px; margin-bottom: 18px; }
.declaration-title small { font-size: 14px; font-weight: 400; color: var(--lab-muted); }
.row { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; }
.row .el-select, .row .el-input-number { width: 100%; }
.panel :deep(.el-form-item__label) { font-size: 15px; font-weight: 600; }
.panel :deep(.el-form-item) { margin-bottom: 19px; }
.cuda-declaration :deep(.el-checkbox) { white-space: normal; height: auto; }
.cuda-declaration :deep(.el-checkbox__label) { font-size: 15px; line-height: 1.6; }
.locked { display: flex; gap: 9px; align-items: center; border: 1px solid var(--lab-line); background: #f6f8fb; padding: 11px 13px; border-radius: 7px; color: var(--lab-muted); font-size: 15px; }
.locked strong, .locked span { display: block; }
.locked strong { font-weight: 500; color: #52647d; margin-bottom: 4px; }
.locked span { font-size: 14px; }
.form-actions { display: flex; align-items: center; gap: 20px; padding-top: 24px; }
.form-actions .el-button { min-height: 38px; padding: 0 23px; }
.form-actions .el-icon { margin-right: 7px; }
.form-actions a, .model-link { font-size: 15px; color: var(--lab-accent-2); text-decoration: none; }
.form-actions a span { padding-left: 6px; }
.state-badge { margin-left: auto; white-space: nowrap; font-size: 14px; color: #71839b; background: #f3f6fb; border: 1px solid #e5ebf4; border-radius: 5px; padding: 5px 8px; }
.check-timeline { padding: 0; margin: 4px 0 20px; list-style: none; }
.check-timeline li { display: flex; align-items: start; gap: 13px; position: relative; padding: 0 0 24px; }
.check-timeline li:last-child { padding-bottom: 0; }
.check-timeline li:not(:last-child)::after { content: ''; position: absolute; top: 32px; bottom: 4px; left: 14px; width: 1px; background: #e4eaf3; }
.stamp { flex: none; display: grid; place-items: center; width: 30px; height: 30px; border-radius: 50%; background: #f3f6fa; border: 1px solid #e1e8f0; color: #8897ab; font: 14px var(--lab-font-mono); }
.check-timeline strong { display: block; margin: 3px 0 6px; font-size: 16px; font-weight: 600; }
.check-timeline p { color: var(--lab-muted); line-height: 1.55; font-size: 14px; margin: 0; overflow-wrap: anywhere; }
.check-timeline small { margin: 6px 0 0 auto; flex: none; color: #93a0b1; font-size: 14px; }
.check-timeline .ok .stamp { color: #199a76; background: #e7f8f0; border-color: #bde9d7; }
.check-timeline .ok small { color: #199a76; }
.check-timeline .bad .stamp { color: var(--lab-danger); background: #fff1f1; border-color: #f4cccc; }
.check-timeline .bad small { color: var(--lab-danger); }
.output-spec { display: flex; gap: 10px; border: 1px solid #dce8fa; border-radius: 8px; background: #f2f7ff; padding: 14px; color: #3974c7; }
.output-spec strong, .output-spec code, .output-spec span { display: block; }
.output-spec strong { font-size: 15px; font-weight: 500; }
.output-spec code { font: 16px var(--lab-font-mono); padding: 8px 0 6px; color: #285791; }
.output-spec span { font-size: 14px; color: #7688a1; }
.model-link { display: inline-block; margin-top: 17px; }
.check-note { display: flex; gap: 12px; padding: 20px 5px; color: #7c91ad; }
.check-note > .el-icon { margin-top: 2px; flex: none; font-size: 19px; }
.check-note h3 { margin: 0 0 7px; font-size: 15px; font-weight: 600; color: #5a6d86; }
.check-note p { margin: 0; font-size: 15px; line-height: 1.8; }
.err { color: var(--lab-danger); font-size: 16px; line-height: 1.6; }
@media (max-width: 1050px) { .layout { grid-template-columns: 1fr; } }
@media (max-width: 520px) { .panel, .ticket { padding: 18px; } .file-grid, .row { grid-template-columns: 1fr; } .declaration-title { flex-direction: column; gap: 5px; } .section-head { gap: 8px; } .section-head h2 { font-size: 18px; } }
</style>

<template>
  <div class="chat-page">
    <section class="stage">
      <header class="topbar">
        <div>
          <p class="eyebrow">实验台</p>
          <h1>科研助手 <span>Research assistant</span></h1>
          <p class="top-subtitle">围绕实验结果、研究资料与模型版本展开讨论</p>
        </div>
        <div class="top-actions">
          <button type="button" class="ghost new-chat" @click="newConversation()"><el-icon><Plus /></el-icon>新对话</button>
          <button type="button" class="ghost" :class="{ on: listOpen }" @click="listOpen = !listOpen"><el-icon><ChatLineSquare /></el-icon>对话列表</button>
        </div>
      </header>

      <div class="assistant-workspace">
        <div class="conversation-column">
          <div class="conversation-toolbar">
          <div class="pills" role="tablist" aria-label="专科选择器">
            <button type="button" class="pill" :class="{ on: specialty === 'academic' }" @click="switchSpecialty('academic')"><el-icon><Reading /></el-icon>学术</button>
            <button type="button" class="pill" :class="{ on: specialty === 'segment' }" @click="switchSpecialty('segment')"><el-icon><Picture /></el-icon>分割</button>
            <button type="button" class="pill" :class="{ on: specialty === 'model' }" @click="switchSpecialty('model')"><el-icon><Box /></el-icon>模型</button>
          </div>
          <span class="conversation-mode">{{ llmReady ? "工具证据 + 对话说明" : "工具证据模式" }}</span>
          </div>
      <div ref="threadEl" class="thread">
        <p v-if="loadError" class="err">{{ loadError }}</p>
        <div v-if="!turns.length && !busy" class="hero">
          <span class="welcome-icon"><el-icon><ChatDotRound /></el-icon></span>
          <p class="welcome-label">STEEL LAB · {{ specialtyLabel(specialty) }}专科</p>
          <h2>从一条专科问题开始</h2>
          <p class="muted">{{ heroHint }}</p>
          <ul class="suggest">
            <li v-for="item in suggestions" :key="item"><button type="button" @click="draft = item"><el-icon><ChatLineSquare /></el-icon><span>{{ item }}</span><span class="suggest-arrow">↗</span></button></li>
          </ul>
          <p class="welcome-note"><el-icon><InfoFilled /></el-icon>测量事实与文字建议分别呈现，精度数字以任务证据为准</p>
        </div>

        <div v-else class="feed">
          <p v-if="!turns.length && busy" class="muted">正在处理…</p>
          <article v-for="turn in turns" :key="turn.id" class="bubble" :class="turn.role">
            <span class="message-avatar" :class="turn.role"><el-icon><User v-if="turn.role === 'user'" /><ChatDotRound v-else /></el-icon></span>
            <div v-if="turn.role === 'user'" class="bubble-inner user">
              <p class="copy">{{ turn.content }}</p>
            </div>
            <div v-else class="bubble-inner assistant">
              <p class="message-author">Steel_lab <span>{{ specialtyLabel(specialty) }}助手</span></p>
              <p v-if="turn.streaming && !turn.writing" class="muted">正在生成…</p>
              <p v-if="turn.writing" class="copy" :class="{ streaming: turn.streaming }">{{ turn.writing }}</p>
              <p v-else-if="!turn.streaming && turn.llm_status === 'skipped' && turn.evidence_pack && !turn.evidence_pack.clarify" class="muted">
                未配置大模型，以下为证据包 / 检索命中 / 测参档案。对比与演示主流程不受影响。
              </p>
              <p v-else-if="!turn.streaming && turn.llm_status === 'error'" class="muted">{{ writingFail }}</p>

              <section v-if="kbPack(turn)" class="card evidence-card">
                <h3><el-icon><Reading /></el-icon>{{ kbPack(turn)?.hit ? "命中语料" : "未命中" }}</h3>
                <p v-if="kbPack(turn)?.via && kbPack(turn)?.hit" class="muted">
                  来源通道：{{ kbPack(turn)?.via === "milvus" ? "实验室知识库" : kbPack(turn)?.via === "session" ? "本会话已命中语料" : kbPack(turn)?.via === "local-fallback" ? "本站审定条目（向量库不可用）" : "本站审定条目" }}
                </p>
                <ul v-if="kbPack(turn)?.hits?.length" class="judgements">
                  <li v-for="(hit, index) in kbPack(turn)?.hits" :key="index">
                    <span class="grade">{{ hit.source }}</span>
                    <strong>{{ hit.title }}</strong>
                    <p class="muted">{{ hit.excerpt }}</p>
                  </li>
                </ul>
              </section>

              <section v-if="taskPack(turn)" class="card evidence-card">
                <p class="eyebrow">证据包 · 测量事实 / 规则判断</p>
                <h3><el-icon><DocumentChecked /></el-icon>{{ taskPack(turn)?.task?.type_label }} · {{ taskPack(turn)?.task?.id }}</h3>
                <dl class="facts">
                  <div><dt>状态</dt><dd>{{ taskStatusLabel(taskPack(turn)?.task?.status) }}</dd></div>
                  <div><dt>有 GT</dt><dd>{{ taskPack(turn)?.task?.has_gt ? "是" : "否" }}</dd></div>
                  <div><dt>样本量 n</dt><dd>{{ taskPack(turn)?.task?.n ?? "—" }}</dd></div>
                  <div>
                    <dt>预处理</dt>
                    <dd>
                      {{ taskPack(turn)?.task?.preprocess?.name }}
                      {{ taskPack(turn)?.task?.preprocess?.width }}×{{ taskPack(turn)?.task?.preprocess?.height }}
                    </dd>
                  </div>
                </dl>
                <ul class="judgements">
                  <li v-for="(item, index) in taskPack(turn)?.judgements ?? []" :key="index">
                    <span class="grade" :class="item.grade">{{ gradeLabel(item.grade) }}</span>
                    {{ item.text }}
                  </li>
                </ul>
                <p v-if="taskPack(turn)?.task?.open_path">
                  <router-link :to="taskPack(turn)?.task?.open_path || '/'">打开任务页</router-link>
                </p>
                <div v-if="taskPack(turn)?.metrics?.available" class="metrics">
                  <p class="muted">{{ taskPack(turn)?.metrics?.disclaimer }}</p>
                  <el-table :data="taskPack(turn)?.metrics?.models ?? []" size="small">
                    <el-table-column prop="name" label="模型" min-width="140" />
                    <el-table-column label="mIoU" width="110">
                      <template #default="{ row }">{{ formatScore(row.mIoU) }}</template>
                    </el-table-column>
                    <el-table-column label="mDice" width="110">
                      <template #default="{ row }">{{ formatScore(row.mDice) }}</template>
                    </el-table-column>
                  </el-table>
                </div>
                <p v-else-if="taskPack(turn)?.task" class="muted">无配对 GT 或指标不可用，证据包不含精度数字。</p>
                <ul v-if="taskPack(turn)?.visualizations?.length" class="viz">
                  <li v-for="(item, index) in taskPack(turn)?.visualizations ?? []" :key="index">
                    {{ item.kind }}
                    <template v-if="item.sample_key"> · {{ item.sample_key }}</template>
                    <el-button v-if="item.url" link type="primary" @click="openViz(item.url)">打开</el-button>
                  </li>
                </ul>
              </section>

              <section v-if="perfPack(turn)" class="card evidence-card">
                <h3><el-icon><DataAnalysis /></el-icon>测参档案</h3>
                <p class="muted">{{ perfPack(turn)?.disclaimer || fpsDisclaimer }}</p>
                <dl class="facts">
                  <div><dt>模型</dt><dd>{{ perfPack(turn)?.version?.name }}</dd></div>
                  <div><dt>状态</dt><dd>{{ perfPack(turn)?.perf?.status }}</dd></div>
                  <div><dt>参数量</dt><dd>{{ formatParamCount(perfPack(turn)?.perf?.param_count) }}</dd></div>
                  <div><dt>本机 ms/图</dt><dd>{{ formatLatencyMs(perfPack(turn)?.perf?.latency_ms_per_image) }}</dd></div>
                  <div><dt>本机 FPS</dt><dd>{{ formatFps(perfPack(turn)?.perf?.fps_per_image) }}</dd></div>
                  <div><dt>FLOPs</dt><dd>{{ perfPack(turn)?.perf?.flops == null ? "未测量" : perfPack(turn)?.perf?.flops }}</dd></div>
                </dl>
                <p v-if="perfPack(turn)?.version?.open_path">
                  <router-link :to="perfPack(turn)?.version?.open_path || '/'">打开模型卡</router-link>
                </p>
              </section>

              <section v-if="turn.evidence_pack?.needs_confirm" class="card confirm">
                <h3>待确认</h3>
                <p class="muted">{{ confirmSummary(turn) }}</p>
                <el-button type="primary" size="small" :loading="busy" @click="confirmTurn(turn)">确认执行</el-button>
              </section>
            </div>
          </article>
        </div>
      </div>

      <footer class="dock">
        <div class="capsule">
          <div class="chips" role="tablist" aria-label="专科选择器">
            <button type="button" class="chip" :class="{ on: specialty === 'academic' }" @click="switchSpecialty('academic')">学术</button>
            <button type="button" class="chip" :class="{ on: specialty === 'segment' }" @click="switchSpecialty('segment')">分割</button>
            <button type="button" class="chip" :class="{ on: specialty === 'model' }" @click="switchSpecialty('model')">模型</button>
          </div>

          <div v-if="specialty === 'segment'" class="attach">
            <el-select v-model="selectedId" filterable clearable placeholder="钉住一条对比或评测" class="pick">
              <el-option v-for="item in tasks" :key="item.id" :label="taskLabel(item)" :value="item.id" />
            </el-select>
            <details class="more">
              <summary>分割代跑</summary>
              <p class="muted">上传用户图，确认后封装快速对比。不跑演示、不新建正式评测。</p>
              <el-upload drag multiple :auto-upload="false" :limit="50" accept=".png,.jpg,.jpeg,.tif,.tiff" :on-change="onChange" :on-remove="onRemove">
                <div class="up">将 JPG 原图拖到此处</div>
              </el-upload>
              <p class="count">已选 {{ fileList.length }} 张原图</p>
              <el-upload drag multiple :auto-upload="false" :limit="50" accept=".png,.jpg,.jpeg,.tif,.tiff,.bmp" :on-change="onMaskChange" :on-remove="onMaskRemove">
                <div class="up">配对掩码（可选）</div>
              </el-upload>
              <el-checkbox-group v-model="selectedBaselines" class="picks">
                <el-checkbox v-for="model in builtins" :key="model.id" :label="model.id">
                  {{ model.name }} <span class="meta">{{ model.slug }}</span>
                </el-checkbox>
              </el-checkbox-group>
              <el-radio-group v-model="studentId" class="picks">
                <el-radio label="">不使用学生模型</el-radio>
                <el-radio v-for="model in students" :key="model.id" :label="model.id">{{ model.name }}</el-radio>
              </el-radio-group>
              <el-button type="primary" :loading="busy" :disabled="!canInfer" @click="queueInfer()">确认并预览代跑</el-button>
            </details>
          </div>

          <div v-if="specialty === 'model'" class="attach">
            <el-select v-model="modelVersionId" filterable clearable placeholder="钉住一个模型版本" class="pick">
              <el-option v-for="item in allModels" :key="item.id" :label="modelLabel(item)" :value="item.id" />
            </el-select>
            <el-button :disabled="!modelVersionId" :loading="busy" @click="measurePerf()">测参</el-button>
            <el-button :disabled="!modelVersionId" :loading="busy" @click="adviseCode()">源码建议</el-button>
            <router-link class="jump" to="/models/perf">去模型测评</router-link>
            <el-input v-model="codeSnippet" type="textarea" :rows="2" maxlength="8000" show-word-limit placeholder="可选：粘贴源码片段（不写盘，API 不 import）" />
          </div>

          <div class="input-row">
            <el-input
              v-model="draft"
              type="textarea"
              :autosize="{ minRows: 2, maxRows: 6 }"
              maxlength="2000"
              :placeholder="placeholder"
              @keydown.enter.exact.prevent="sendText()"
            />
            <button type="button" class="send" :disabled="!canSend" @click="sendText()"><el-icon><Promotion /></el-icon>发送</button>
          </div>
          <p class="composer-hint">Enter 发送 · Shift + Enter 换行<span>代跑与测参需确认后执行</span></p>
        </div>
      </footer>
        </div>
        <aside class="context-rail">
          <section class="context-card">
            <h2><el-icon><Connection /></el-icon>本次上下文</h2>
            <p class="context-caption">{{ specialtyLabel(specialty) }}专科 · 手动选择</p>
            <template v-if="specialty === 'segment' && selectedTask">
              <div class="context-object"><span class="context-object-icon"><el-icon><Picture /></el-icon></span><div><strong>{{ selectedTask.type_label }}</strong><span>#{{ selectedTask.id.slice(0, 8) }}</span></div></div>
              <dl class="context-facts">
                <div><dt>任务状态</dt><dd>{{ taskStatusLabel(selectedTask.status) }}</dd></div>
                <div><dt>样本数量</dt><dd>{{ selectedTask.n ?? "未提供" }}</dd></div>
                <div><dt>配对 GT</dt><dd>{{ selectedTask.has_gt ? "有" : "无" }}</dd></div>
                <div><dt>精度证据</dt><dd>{{ selectedTask.has_gt ? "以任务证据包为准" : "不可用" }}</dd></div>
              </dl>
              <router-link class="context-link" :to="taskPath(selectedTask.type, selectedTask.id)">打开任务页 <span>↗</span></router-link>
            </template>
            <template v-else-if="specialty === 'model' && selectedModel">
              <div class="context-object"><span class="context-object-icon"><el-icon><Box /></el-icon></span><div><strong>{{ selectedModel.name }}</strong><span>#{{ selectedModel.id.slice(0, 8) }}</span></div></div>
              <dl class="context-facts">
                <div><dt>模型来源</dt><dd>{{ selectedModel.source === 'builtin' ? '内置模型' : '学生模型' }}</dd></div>
                <div><dt>模型状态</dt><dd>{{ modelStatusLabel(selectedModel.status) }}</dd></div>
              </dl>
              <router-link class="context-link" :to="`/models/${selectedModel.id}`">打开模型卡 <span>↗</span></router-link>
            </template>
            <div v-else class="context-empty"><el-icon><Reading v-if="specialty === 'academic'" /><Connection v-else /></el-icon><strong>{{ specialty === 'academic' ? '从研究问题开始' : specialty === 'model' ? '尚未选择模型' : '尚未绑定任务' }}</strong><p>{{ specialty === 'academic' ? '检索命中的语料会展示在对话中，请结合原始来源核对引用。' : specialty === 'model' ? '在输入区选择模型版本，围绕测参或源码展开讨论。' : '在输入区选择已有对比或评测，查看真实任务上下文。' }}</p></div>
          </section>
          <section class="context-card evidence-guide">
            <h2><el-icon><DocumentChecked /></el-icon>如何阅读回答</h2>
            <div><span class="guide-mark measurement"></span><p><strong>测量事实</strong><span>任务结果与工具返回的数据</span></p></div>
            <div><span class="guide-mark rule"></span><p><strong>规则判断</strong><span>对照平台协议给出的判断</span></p></div>
            <div><span class="guide-mark speculation"></span><p><strong>推测与建议</strong><span>需进一步实验验证的方向</span></p></div>
          </section>
          <p class="context-footnote"><el-icon><InfoFilled /></el-icon>模型适配请从对应模型卡进入，科研助手不会修改或执行粘贴的源码。</p>
        </aside>
      </div>
    </section>

    <button v-if="listOpen" type="button" class="scrim" aria-label="关闭对话列表" @click="listOpen = false" />
    <aside class="drawer" :class="{ open: listOpen }">
      <div class="drawer-head">
        <h2>对话列表</h2>
        <button type="button" class="ghost" @click="listOpen = false">收起</button>
      </div>
      <ul class="session-list">
        <li
          v-for="item in sessionList"
          :key="item.id"
          :class="{ on: item.id === currentId }"
          @click="openSession(item.id)"
        >
          <span class="spec">{{ specialtyLabel(item.specialty) }}</span>
          <span class="title">{{ item.title || "新对话" }}</span>
        </li>
      </ul>
      <p v-if="!sessionList.length" class="rail-empty">还没有对话。发送第一条消息后会出现在这里。</p>
    </aside>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { ElMessage } from "element-plus";
import { Box, ChatDotRound, ChatLineSquare, Connection, DataAnalysis, DocumentChecked, InfoFilled, Picture, Plus, Promotion, Reading, User } from "@element-plus/icons-vue";
import type { UploadFile } from "element-plus";
import { formatError, http } from "../api/http";
import {
  formatFps,
  formatLatencyMs,
  formatParamCount,
  openAuthFile,
  modelStatusLabel,
  taskPath,
  taskStatusLabel,
} from "../api/labels";

type SessionCard = {
  id: string;
  specialty: string;
  title?: string;
  updated_at?: string;
  working?: { task_id?: string; version_id?: string };
};

type Analyzable = {
  id: string;
  type: string;
  type_label: string;
  status: string;
  has_gt: boolean;
  n?: number;
  created_at?: string;
  creator_username?: string | null;
};

type Turn = {
  id: string;
  role: string;
  content?: string | null;
  writing?: string | null;
  tool_name?: string;
  llm_status?: string;
  task_id?: string | null;
  evidence_pack?: Record<string, any> | null;
  streaming?: boolean;
};

type ModelCard = {
  id: string;
  name: string;
  slug: string;
  source: string;
  status: string;
  requires_cuda?: boolean;
  runnable_here?: boolean;
};

const writingFail =
  "大模型说明暂不可用（超时、接口失败或密钥无效）。证据包 / 检索命中 / 测参档案仍有效，对比与演示主流程不受影响。请检查 .env 的 LLM_API_KEY 或 DASHSCOPE_API_KEY 后重启 API。";
const fpsDisclaimer =
  "本机 CPU、batch=1、dummy 随机输入的前向。FPS = 1000 / ms/图。不是 CUDA 论文测速，也不是测试集指标。";

const route = useRoute();
const threadEl = ref<HTMLElement | null>(null);
const specialty = ref("segment");
const currentId = ref("");
const sessionList = ref<SessionCard[]>([]);
const turns = ref<Turn[]>([]);
const draft = ref("");
const llmReady = ref(false);
const busy = ref(false);
const loadError = ref("");
const listOpen = ref(false);

const tasks = ref<Analyzable[]>([]);
const selectedId = ref("");
const fileList = ref<File[]>([]);
const maskList = ref<File[]>([]);
const builtins = ref<ModelCard[]>([]);
const students = ref<ModelCard[]>([]);
const selectedBaselines = ref<string[]>([]);
const studentId = ref("");

const modelVersionId = ref("");
const allModels = ref<ModelCard[]>([]);
const codeSnippet = ref("");
const selectedTask = computed(() => tasks.value.find((item) => item.id === selectedId.value));
const selectedModel = computed(() => allModels.value.find((item) => item.id === modelVersionId.value));

const canInfer = computed(
  () =>
    fileList.value.length >= 1 &&
    fileList.value.length <= 50 &&
    selectedBaselines.value.length >= 1 &&
    selectedBaselines.value.length <= 3,
);

const canSend = computed(() => Boolean(draft.value.trim()) && !busy.value);

const placeholder = computed(() => {
  if (specialty.value === "academic") return "发消息… 例如 NEU-20 能写成论文测试集吗？";
  if (specialty.value === "model") return "发消息… 对着已选版本追问源码建议，或点测参。";
  return "发消息… 对着已选任务追问弱类、协议或下一步。";
});

const heroHint = computed(() => {
  if (!llmReady.value) return "未配置大模型密钥时，证据 / 命中 / 测参档案仍会进气泡。不自动判断意图，换专科后第一条消息会开新线程。";
  return "数字以工具卡片为准。同一会话可追问；换专科后第一条消息会开新线程。本站不做训练。";
});

const suggestions = computed(() => {
  if (specialty.value === "academic") {
    return ["NEU-20 能写成论文测试集吗？", "课题组学习路线怎么安排？", "本机 FPS 能写进论文吗？"];
  }
  if (specialty.value === "model") {
    return ["请给出源码建议（不写盘）", "查看测参档案", "导入失败后该去哪改代码？"];
  }
  return ["请分析本次结果的弱类", "无 GT 时能谈精度吗？", "协议和预处理是否一致？"];
});

function specialtyLabel(name: string) {
  if (name === "academic") return "学术";
  if (name === "model") return "模型";
  return "分割";
}

function taskLabel(item: Analyzable) {
  const when = item.created_at ? item.created_at.replace("T", " ").slice(0, 16) : "";
  const who = item.creator_username ? ` · ${item.creator_username}` : "";
  return `${item.type_label} · ${item.status} · n=${item.n ?? "?"} · ${when}${who}`;
}

function modelLabel(item: ModelCard) {
  return `${item.name} · ${item.source} · ${item.status}`;
}

function gradeLabel(grade: string) {
  if (grade === "measurement") return "测量事实";
  if (grade === "rule") return "规则判断";
  if (grade === "speculation") return "推测";
  return grade;
}

function formatScore(value: number | undefined) {
  if (typeof value !== "number" || Number.isNaN(value)) return "—";
  return value.toFixed(4);
}

function kbPack(turn: Turn) {
  const pack = turn.evidence_pack;
  if (!pack || (!pack.hits && pack.hit == null && !pack.refused)) return null;
  if (pack.task || pack.perf) return null;
  return pack;
}

function taskPack(turn: Turn) {
  const pack = turn.evidence_pack;
  if (!pack?.task) return null;
  return pack;
}

function perfPack(turn: Turn) {
  const pack = turn.evidence_pack;
  if (!pack?.perf || pack.needs_confirm) return null;
  return pack;
}

function confirmSummary(turn: Turn) {
  const preview = turn.evidence_pack?.preview || {};
  if (turn.tool_name === "infer.run") {
    return `将入队快速对比：${preview.n ?? "?"} 张图，${preview.has_gt ? "有 GT（本批参考指标）" : "无 GT（只可视化）"}。不跑演示、不新建正式评测。`;
  }
  if (turn.tool_name === "perf.measure") {
    const protocol = preview.protocol || {};
    return `将按实验室协议测参：CPU · dummy · ${protocol.input ?? ""} · batch ${protocol.batch ?? 1}。${fpsDisclaimer}`;
  }
  return "请确认后才会执行。";
}

async function reloadSessions() {
  const { data } = await http.get("/assistant/sessions");
  sessionList.value = data.items ?? [];
  llmReady.value = Boolean(data.llm_ready);
}

async function reloadTasks() {
  const { data } = await http.get("/assistant/tasks");
  tasks.value = data.items ?? [];
  llmReady.value = Boolean(data.llm_ready);
}

function applySession(data: { id: string; specialty: string; turns?: Turn[]; working?: SessionCard["working"]; llm_ready?: boolean }) {
  currentId.value = data.id;
  specialty.value = data.specialty;
  turns.value = data.turns ?? [];
  if (data.working?.task_id) selectedId.value = data.working.task_id;
  if (data.working?.version_id) modelVersionId.value = data.working.version_id;
  if (data.llm_ready != null) llmReady.value = data.llm_ready;
}

function resetCanvas() {
  currentId.value = "";
  turns.value = [];
  draft.value = "";
  loadError.value = "";
}

async function openSession(id: string) {
  loadError.value = "";
  const { data } = await http.get(`/assistant/sessions/${id}`);
  applySession(data);
}

async function createSession(name: string) {
  const { data } = await http.post("/assistant/sessions", { specialty: name });
  applySession(data);
  return data.id as string;
}

async function ensureSession() {
  if (currentId.value) return currentId.value;
  return createSession(specialty.value);
}

function newConversation() {
  resetCanvas();
  selectedId.value = "";
  modelVersionId.value = "";
  codeSnippet.value = "";
}

function switchSpecialty(name: string) {
  if (specialty.value === name) return;
  if (turns.value.length) resetCanvas();
  selectedId.value = "";
  modelVersionId.value = "";
  codeSnippet.value = "";
  specialty.value = name;
}

function wantsStream(body: Record<string, unknown>) {
  if (body.confirm || body.enqueue) return false;
  if (body.tool === "infer.run" || body.tool === "perf.measure") return false;
  return true;
}

function parseSseChunk(buffer: string) {
  const frames: Record<string, any>[] = [];
  let rest = buffer;
  while (true) {
    const split = rest.indexOf("\n\n");
    if (split < 0) break;
    const raw = rest.slice(0, split);
    rest = rest.slice(split + 2);
    for (const line of raw.split("\n")) {
      if (!line.startsWith("data:")) continue;
      const payload = line.slice(5).trim();
      if (!payload) continue;
      try {
        frames.push(JSON.parse(payload));
      } catch {
        /* ignore partial JSON */
      }
    }
  }
  return { frames, rest };
}

async function sendPayloadJson(body: Record<string, unknown>) {
  const sessionId = await ensureSession();
  const { data } = await http.post(`/assistant/sessions/${sessionId}/messages`, body);
  applySession(data);
  await reloadSessions();
  if (data.working?.task_id) await reloadTasks();
}

async function sendPayloadStream(body: Record<string, unknown>) {
  const sessionId = await ensureSession();
  const userText = String(body.content || body.question || "").trim();
  const tempUserId = `tmp-user-${Date.now()}`;
  const tempAsstId = `tmp-asst-${Date.now()}`;
  if (userText) {
    turns.value = [
      ...turns.value,
      { id: tempUserId, role: "user", content: userText },
      { id: tempAsstId, role: "assistant", writing: "", streaming: true, llm_status: "ok" },
    ];
  } else {
    turns.value = [
      ...turns.value,
      { id: tempAsstId, role: "assistant", writing: "", streaming: true, llm_status: "ok" },
    ];
  }
  const response = await fetch(`/api/assistant/sessions/${sessionId}/messages/stream`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(body),
  });
  if (!response.ok || !response.body) {
    throw new Error(await response.text() || `HTTP ${response.status}`);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let writing = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parsed = parseSseChunk(buffer);
    buffer = parsed.rest;
    for (const event of parsed.frames) {
      if (event.type === "delta" && event.text) {
        writing += event.text;
        const index = turns.value.findIndex((item) => item.id === tempAsstId);
        if (index >= 0) {
          const next = [...turns.value];
          next[index] = { ...next[index], writing, streaming: true };
          turns.value = next;
        }
      } else if (event.type === "error") {
        throw new Error([event.stage, event.code, event.message].filter(Boolean).join(" / "));
      } else if (event.type === "done" && event.session) {
        applySession(event.session);
        await reloadSessions();
        if (event.session.working?.task_id) await reloadTasks();
        return;
      }
    }
  }
  if (writing) {
    const index = turns.value.findIndex((item) => item.id === tempAsstId);
    if (index >= 0) {
      const next = [...turns.value];
      next[index] = { ...next[index], writing, streaming: false, llm_status: "error" };
      turns.value = next;
    }
  }
}

async function sendPayload(body: Record<string, unknown>) {
  busy.value = true;
  loadError.value = "";
  try {
    if (wantsStream(body)) await sendPayloadStream(body);
    else await sendPayloadJson(body);
  } catch (error) {
    loadError.value = formatError(error);
    const last = turns.value[turns.value.length - 1];
    if (last?.streaming) {
      const next = [...turns.value];
      next[next.length - 1] = { ...last, streaming: false, llm_status: last.writing ? "ok" : "error" };
      turns.value = next;
    }
  } finally {
    busy.value = false;
  }
}

async function sendText() {
  const text = draft.value.trim();
  if (!text) return;
  draft.value = "";
  const body: Record<string, unknown> = { content: text };
  if (specialty.value === "segment" && selectedId.value) body.task_id = selectedId.value;
  if (specialty.value === "model" && modelVersionId.value) body.version_id = modelVersionId.value;
  if (specialty.value === "model" && codeSnippet.value.trim()) body.snippet = codeSnippet.value.trim();
  await sendPayload(body);
}

async function measurePerf() {
  if (!modelVersionId.value) return;
  await sendPayload({
    content: draft.value.trim() || "查看测参档案",
    tool: "perf.measure",
    version_id: modelVersionId.value,
  });
  draft.value = "";
}

async function adviseCode() {
  if (!modelVersionId.value) return;
  await sendPayload({
    content: draft.value.trim() || "请给出源码建议（不写盘）",
    tool: "code.advise",
    version_id: modelVersionId.value,
    snippet: codeSnippet.value.trim() || null,
  });
  draft.value = "";
}

async function queueInfer() {
  if (!canInfer.value) return;
  busy.value = true;
  loadError.value = "";
  try {
    const form = new FormData();
    for (const file of fileList.value) form.append("files", file);
    const uploaded = await http.post("/uploads/images", form);
    if (maskList.value.length) {
      const masks = new FormData();
      masks.append("batch_id", uploaded.data.batch_id);
      for (const file of maskList.value) masks.append("files", file);
      await http.post("/uploads/masks", masks);
    }
    const sessionId = await ensureSession();
    const { data } = await http.post(`/assistant/sessions/${sessionId}/messages`, {
      content: "请求分割代跑（封装快速对比）",
      tool: "infer.run",
      batch_id: uploaded.data.batch_id,
      baseline_version_ids: selectedBaselines.value,
      student_version_id: studentId.value || null,
      confirm: false,
    });
    applySession(data);
    await reloadSessions();
  } catch (error) {
    loadError.value = formatError(error);
  } finally {
    busy.value = false;
  }
}

async function confirmTurn(turn: Turn) {
  const preview = turn.evidence_pack?.preview || {};
  if (turn.tool_name === "infer.run") {
    await sendPayload({
      content: "确认入队快速对比",
      tool: "infer.run",
      batch_id: preview.batch_id,
      baseline_version_ids: (preview.baselines || []).map((item: { id: string }) => item.id),
      student_version_id: preview.student?.id || null,
      confirm: true,
    });
    return;
  }
  if (turn.tool_name === "perf.measure") {
    await sendPayload({
      content: "确认入队测参",
      tool: "perf.measure",
      version_id: preview.version?.id || modelVersionId.value,
      enqueue: true,
      confirm: true,
    });
  }
}

function onChange(_file: UploadFile, files: UploadFile[]) {
  fileList.value = files.map((item) => item.raw).filter((item): item is File => Boolean(item));
}
function onRemove(_file: UploadFile, files: UploadFile[]) {
  fileList.value = files.map((item) => item.raw).filter((item): item is File => Boolean(item));
}
function onMaskChange(_file: UploadFile, files: UploadFile[]) {
  maskList.value = files.map((item) => item.raw).filter((item): item is File => Boolean(item));
}
function onMaskRemove(_file: UploadFile, files: UploadFile[]) {
  maskList.value = files.map((item) => item.raw).filter((item): item is File => Boolean(item));
}

async function openViz(url: string) {
  try {
    await openAuthFile(url);
  } catch (error) {
    ElMessage.error(formatError(error));
  }
}

watch(turns, async () => {
  await nextTick();
  if (threadEl.value) threadEl.value.scrollTop = threadEl.value.scrollHeight;
});

onMounted(async () => {
  try {
    await reloadSessions();
    await reloadTasks();
    const { data } = await http.get("/models");
    const grouped = (data.builtins as ModelCard[] | undefined) ?? [];
    builtins.value = grouped.filter(
      (item) => item.source === "builtin" && item.status === "runnable" && item.runnable_here !== false && !item.requires_cuda,
    );
    selectedBaselines.value = builtins.value.slice(0, 3).map((item) => item.id);
    const mine = (data.mine as ModelCard[] | undefined) ?? [];
    const shared = (data.shared as ModelCard[] | undefined) ?? [];
    students.value = [...mine, ...shared].filter(
      (item) => item.source === "student" && item.status === "runnable" && item.runnable_here !== false && !item.requires_cuda,
    );
    allModels.value = [...builtins.value, ...students.value, ...mine, ...shared].filter(
      (item, index, rows) => rows.findIndex((row) => row.id === item.id) === index,
    );
    const fromQuery = String(route.query.taskId || "");
    if (fromQuery && tasks.value.some((item) => item.id === fromQuery)) {
      selectedId.value = fromQuery;
      specialty.value = "segment";
      await sendPayload({ content: "请分析本次结果", task_id: fromQuery });
      return;
    }
    const wanted = String(route.query.tab || route.query.specialty || "");
    if (wanted === "academic" || wanted === "model" || wanted === "segment") {
      specialty.value = wanted;
    }
  } catch (error) {
    loadError.value = formatError(error);
  }
});
</script>

<style scoped>
.chat-page { position: relative; height: 100%; color: var(--lab-text); overflow: hidden; background: var(--lab-canvas); }
.stage { display: flex; flex-direction: column; height: 100%; min-width: 0; }
.topbar { display: flex; justify-content: space-between; align-items: center; flex: none; padding: 24px 28px 0; gap: 16px; }
.eyebrow { margin: 0 0 7px; color: var(--lab-accent-2); font-size: 14px; letter-spacing: .16em; }
.topbar h1 { margin: 0; font-size: 27px; letter-spacing: -.025em; }
.topbar h1 span { font-size: 15px; font-weight: 400; color: #91a1b8; margin-left: 9px; letter-spacing: 0; }
.top-subtitle { margin: 8px 0 0; font-size: 15px; color: var(--lab-muted); }
.top-actions { display: flex; flex-wrap: wrap; gap: 8px; }
.ghost { display: inline-flex; align-items: center; gap: 6px; background: #fff; color: #687c98; border: 1px solid #dce5f1; border-radius: 6px; padding: 8px 12px; font: inherit; font-size: 15px; cursor: pointer; }
.ghost.on, .ghost:hover { color: var(--lab-accent-2); border-color: #9dbdee; }
.ghost.new-chat { background: #edf4ff; color: #3676d9; border-color: #d4e4fc; }
.assistant-workspace { display: grid; grid-template-columns: minmax(0, 1fr) 268px; flex: 1; min-height: 0; gap: 20px; padding: 22px 28px 24px; }
.conversation-column { display: flex; flex-direction: column; min-width: 0; min-height: 0; border: 1px solid var(--lab-line); border-radius: 13px; background: #fff; box-shadow: 0 4px 20px #24456b05; overflow: hidden; }
.conversation-toolbar { display: flex; justify-content: space-between; align-items: center; flex: none; border-bottom: 1px solid #e8eef6; padding: 12px 18px; gap: 10px; }
.pills { display: flex; gap: 5px; padding: 3px; border-radius: 8px; background: #f2f6fc; }
.pill { display: flex; align-items: center; gap: 6px; border: 1px solid transparent; border-radius: 6px; background: transparent; color: #8a9bb1; padding: 7px 14px; font: inherit; font-size: 15px; cursor: pointer; }
.pill.on { color: #3976cf; background: #fff; border-color: #e0e8f4; box-shadow: 0 2px 4px #395b8a08; }
.conversation-mode { font-size: 14px; color: #657a96; white-space: nowrap; }
.thread { flex: 1; min-height: 0; overflow: auto; padding: 24px; background: linear-gradient(180deg, #fff, #fcfdff); }
.hero { display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 100%; box-sizing: border-box; padding: 22px 0 15px; text-align: center; }
.welcome-icon { display: grid; place-items: center; width: 61px; height: 61px; border-radius: 19px; background: #ebf3ff; border: 1px solid #dfebfc; color: #4b84da; font-size: 31px; box-shadow: 0 5px 12px #6c9ed414; margin-bottom: 16px; }
.welcome-label { font-size: 14px; font-weight: 600; letter-spacing: .12em; color: #83a0c4; margin: 0 0 8px; }
.hero h2 { margin: 0; font-size: 26px; font-weight: 600; letter-spacing: -.02em; }
.hero > .muted { max-width: 480px; margin: 12px 0 19px; font-size: 15px; line-height: 1.9; }
.suggest { list-style: none; margin: 0; padding: 0; display: grid; gap: 9px; width: min(480px, 100%); }
.suggest li { border: 1px solid #e3eaf4; background: #fff; border-radius: 8px; overflow: hidden; }
.suggest li:hover { border-color: #a2c1ee; background: #f8fbff; }
.suggest button { display: flex; align-items: center; gap: 10px; width: 100%; text-align: left; padding: 13px 15px; font: inherit; font-size: 15px; color: #667e9c; border: 0; background: transparent; cursor: pointer; }
.suggest button > .el-icon { color: #a2b8d5; font-size: 18px; }
.suggest-arrow { margin-left: auto; color: #a4b6cf; }
.welcome-note { display: flex; align-items: center; gap: 6px; margin: 19px 0 0; color: #657a96; font-size: 14px; line-height: 1.6; }
.feed { width: min(880px, 100%); margin: 0 auto; display: flex; flex-direction: column; gap: 25px; padding: 2px 0 16px; }
.bubble { display: flex; align-items: start; gap: 10px; min-width: 0; }
.bubble.user { flex-direction: row-reverse; align-self: flex-end; max-width: 88%; }
.bubble.assistant { align-self: stretch; }
.message-avatar { display: grid; place-items: center; flex: none; width: 31px; height: 31px; border: 1px solid #dce9fa; border-radius: 10px; background: #e9f2ff; color: #4c82cb; font-size: 20px; }
.message-avatar.user { background: #eff3f9; color: #7b91af; border-color: #e4eaf3; }
.bubble-inner { min-width: 0; overflow-wrap: anywhere; }
.bubble-inner.user { padding: 11px 15px; background: #edf4ff; border: 1px solid #dfebfc; border-radius: 12px 3px 12px 12px; color: #415f86; }
.bubble-inner.assistant { flex: 1; padding-top: 6px; }
.message-author { margin: 0 0 12px; font-size: 15px; font-weight: 600; color: #415d80; }
.message-author span { font-size: 14px; font-weight: 400; color: #657a96; margin-left: 7px; }
.copy { white-space: pre-wrap; line-height: 1.85; margin: 0; font-size: 16px; color: #4c617d; }
.copy.streaming::after { content: ''; display: inline-block; width: 6px; height: 1em; margin-left: 3px; background: var(--lab-accent-2); vertical-align: text-bottom; animation: caret 1s step-end infinite; }
@keyframes caret { 50% { opacity: 0; } }
.card { margin-top: 14px; padding: 17px; border: 1px solid #dce7f5; border-radius: 9px; background: #fff; }
.card h3 { display: flex; align-items: center; gap: 7px; margin: 0 0 11px; font-size: 16px; color: #4c729e; line-height: 1.6; }
.card h3 .el-icon { color: #6a93cc; flex: none; }
.card .eyebrow { font-size: 14px; margin-bottom: 7px; color: #657a96; }
.card a { color: #5485c7; font-size: 15px; text-decoration: none; }
.facts { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 15px; margin: 15px 0; padding: 14px; border-radius: 6px; background: #f7f9fd; }
.facts dt { color: #657a96; font-size: 14px; }
.facts dd { margin: 5px 0 0; color: #536e90; font-size: 15px; line-height: 1.6; }
.judgements, .viz { padding: 0; margin: 12px 0 0; list-style: none; font-size: 15px; line-height: 1.8; }
.judgements li { padding: 9px 0; border-bottom: 1px solid #eef2f8; color: #6c809b; }
.judgements li:last-child { border: 0; }
.judgements strong { font-size: 15px; color: #516b8c; }
.grade { display: inline-block; padding: 1px 6px; margin-right: 7px; border-radius: 4px; color: #6187b3; background: #edf4fc; font-size: 14px; }
.grade.measurement { color: #438c82; background: #eaf7f3; }
.grade.rule { color: #5b83ba; background: #ecf3fe; }
.grade.speculation { color: #a68b55; background: #fbf4e8; }
.card.confirm { border-color: #eadbbe; background: #fffdf7; }
.muted, .count, .meta, .rail-empty { color: var(--lab-muted); font-size: 15px; line-height: 1.75; }
.err { color: var(--lab-danger); font-size: 15px; line-height: 1.7; }
.dock { flex: none; padding: 0 18px 16px; max-height: 55%; overflow: auto; background: #fff; }
.capsule { border: 1px solid #dbe6f5; border-radius: 10px; background: #fff; padding: 10px 12px 8px; box-shadow: 0 3px 12px #37669f08; }
.chips { display: flex; gap: 5px; margin-bottom: 8px; }
.chip { background: transparent; color: #99a8bd; border: 1px solid transparent; border-radius: 5px; padding: 4px 10px; cursor: pointer; font: inherit; font-size: 14px; }
.chip.on { color: #5285cc; border-color: #d4e4fa; background: #f2f7ff; }
.attach { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 8px; }
.pick { min-width: 0; flex: 1; }
.more { width: 100%; color: #8096b3; font-size: 14px; }
.more summary { cursor: pointer; padding: 5px 0; }
.up { padding: 12px; color: var(--lab-muted); }
.picks { display: flex; flex-direction: column; gap: 6px; margin: 8px 0; align-items: start; }
.jump { color: var(--lab-accent-2); font-size: 14px; }
.input-row { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 10px; align-items: end; }
.send { display: flex; align-items: center; gap: 6px; background: #3377e8; color: #fff; border: 0; border-radius: 7px; padding: 9px 14px; font: inherit; font-size: 15px; cursor: pointer; min-height: 36px; }
.send:disabled { opacity: .45; cursor: not-allowed; }
.capsule :deep(.el-textarea__inner) { background: transparent; box-shadow: none; padding: 5px 2px; font-size: 15px; }
.composer-hint { display: flex; justify-content: space-between; gap: 10px; margin: 10px 0 0; font-size: 14px; color: #657a96; }
.context-rail { display: flex; flex-direction: column; gap: 17px; min-height: 0; overflow: auto; }
.context-card { background: #fff; border: 1px solid var(--lab-line); border-radius: 12px; padding: 19px; }
.context-card h2 { display: flex; align-items: center; gap: 8px; color: #4f6787; font-size: 16px; font-weight: 600; margin: 0; }
.context-card h2 .el-icon { color: #79a0d0; font-size: 18px; }
.context-caption { margin: 9px 0 18px; font-size: 14px; color: #657a96; }
.context-object { display: flex; align-items: center; gap: 10px; padding: 13px 10px; border: 1px solid #e6edf6; border-radius: 7px; background: #f9fbfe; }
.context-object-icon { color: #6e97ce; font-size: 25px; }
.context-object strong { display: block; font-size: 15px; color: #607c9f; overflow-wrap: anywhere; }
.context-object div > span { display: block; margin-top: 5px; font: 14px var(--lab-font-mono); color: #a2b0c3; }
.context-facts { margin: 18px 0; }
.context-facts > div { display: flex; justify-content: space-between; gap: 15px; margin-bottom: 14px; }
.context-facts dt { color: #657a96; font-size: 14px; }
.context-facts dd { margin: 0; font-size: 14px; color: #6f89ab; text-align: right; }
.context-link { display: flex; justify-content: space-between; padding: 10px 0 0; border-top: 1px solid #eaf0f7; color: #5b8acc; font-size: 14px; text-decoration: none; }
.context-empty { text-align: center; padding: 10px 0 4px; }
.context-empty > .el-icon { display: flex; margin: 0 auto 13px; font-size: 30px; color: #b2c6e1; }
.context-empty strong { display: block; font-size: 15px; font-weight: 500; color: #7c92af; }
.context-empty p { color: #657a96; font-size: 14px; line-height: 1.9; margin-bottom: 0; }
.evidence-guide > div { display: flex; align-items: start; gap: 9px; margin-top: 19px; }
.guide-mark { flex: none; width: 7px; height: 7px; margin-top: 4px; border-radius: 50%; }
.guide-mark.measurement { background: #83bdad; }
.guide-mark.rule { background: #82a7db; }
.guide-mark.speculation { background: #d5bc81; }
.evidence-guide p { margin: 0; }
.evidence-guide strong { display: block; font-size: 14px; font-weight: 500; color: #7a8fa9; }
.evidence-guide p span { display: block; margin-top: 6px; color: #657a96; font-size: 14px; line-height: 1.6; }
.context-footnote { display: flex; align-items: start; gap: 7px; font-size: 14px; line-height: 1.9; color: #657a96; margin: 0 4px; }
.context-footnote .el-icon { flex: none; margin-top: 3px; }
.scrim { position: absolute; inset: 0; border: 0; background: #11294645; z-index: 2; }
.drawer { position: absolute; top: 0; right: 0; width: min(320px, 86vw); height: 100%; background: #fff; border-left: 1px solid var(--lab-line); transform: translateX(100%); transition: transform .2s ease; z-index: 3; display: flex; flex-direction: column; }
.drawer.open { transform: translateX(0); }
.drawer-head { display: flex; justify-content: space-between; align-items: center; padding: 20px 16px 14px; border-bottom: 1px solid #edf1f7; }
.drawer-head h2 { margin: 0; font-size: 18px; }
.session-list { list-style: none; margin: 0; padding: 12px; overflow: auto; flex: 1; }
.session-list li { padding: 13px; border: 1px solid #e5ecf6; border-radius: 8px; cursor: pointer; margin-bottom: 8px; background: #fbfcff; }
.session-list li.on { border-color: #a8c7f3; background: #f1f6fe; }
.spec { display: block; color: #7d9fc9; font-size: 14px; }
.title { display: block; margin-top: 6px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #637d9f; font-size: 15px; }
.rail-empty { padding: 0 16px 16px; }
button:focus-visible, a:focus-visible, summary:focus-visible { outline: 2px solid #3979ef; outline-offset: 3px; }
@media (max-width: 1180px) { .assistant-workspace { grid-template-columns: minmax(0, 1fr) 225px; gap: 14px; padding-left: 20px; padding-right: 20px; } .context-card { padding: 16px; } .conversation-mode { display: none; } }
@media (max-width: 1000px) { .assistant-workspace { grid-template-columns: minmax(0, 1fr); } .context-rail { display: none; } }
@media (max-width: 600px) { .topbar { padding: 16px 14px 0; align-items: start; } .topbar h1 { font-size: 23px; } .topbar h1 span, .top-subtitle { display: none; } .top-actions { gap: 5px; } .ghost { font-size: 14px; padding: 7px; } .ghost .el-icon { display: none; } .assistant-workspace { padding: 14px 10px 12px; } .conversation-toolbar { padding: 9px 12px; } .thread { padding: 16px 12px; } .hero { padding-top: 15px; } .hero h2 { font-size: 23px; } .welcome-note { font-size: 14px; } .dock { padding: 0 10px 10px; } .bubble.user { max-width: 98%; } .message-avatar { width: 25px; height: 25px; font-size: 17px; } .card { padding: 12px; } .composer-hint span { display: none; } }
@media (prefers-reduced-motion: reduce) { .copy.streaming::after { animation: none; } .drawer { transition: none; } }
</style>

<template>
  <div class="chat-page">
    <section class="stage">
      <header class="topbar">
        <div>
          <p class="eyebrow">实验台</p>
          <h1>科研助手</h1>
        </div>
        <div class="top-actions">
          <button type="button" class="ghost" @click="newConversation()">新对话</button>
          <button type="button" class="ghost" :class="{ on: listOpen }" @click="listOpen = !listOpen">对话列表</button>
        </div>
      </header>

      <div ref="threadEl" class="thread">
        <p v-if="loadError" class="err">{{ loadError }}</p>
        <div v-if="!turns.length && !busy" class="hero">
          <h2>从一条专科问题开始</h2>
          <div class="pills" role="tablist" aria-label="专科选择器">
            <button type="button" class="pill" :class="{ on: specialty === 'academic' }" @click="switchSpecialty('academic')">学术</button>
            <button type="button" class="pill" :class="{ on: specialty === 'segment' }" @click="switchSpecialty('segment')">分割</button>
            <button type="button" class="pill" :class="{ on: specialty === 'model' }" @click="switchSpecialty('model')">模型</button>
          </div>
          <p class="muted">{{ heroHint }}</p>
          <ul class="suggest">
            <li v-for="item in suggestions" :key="item" @click="draft = item">{{ item }}</li>
          </ul>
        </div>

        <div v-else class="feed">
          <p v-if="!turns.length && busy" class="muted">正在处理…</p>
          <article v-for="turn in turns" :key="turn.id" class="bubble" :class="turn.role">
            <div v-if="turn.role === 'user'" class="bubble-inner user">
              <p class="copy">{{ turn.content }}</p>
            </div>
            <div v-else class="bubble-inner assistant">
              <p v-if="turn.streaming && !turn.writing" class="muted">正在生成…</p>
              <p v-if="turn.writing" class="copy" :class="{ streaming: turn.streaming }">{{ turn.writing }}</p>
              <p v-else-if="!turn.streaming && turn.llm_status === 'skipped' && turn.evidence_pack && !turn.evidence_pack.clarify" class="muted">
                未配置大模型，以下为证据包 / 检索命中 / 测参档案。对比与演示主流程不受影响。
              </p>
              <p v-else-if="!turn.streaming && turn.llm_status === 'error'" class="muted">{{ writingFail }}</p>

              <section v-if="kbPack(turn)" class="card">
                <h3>{{ kbPack(turn)?.hit ? "命中语料" : "未命中" }}</h3>
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

              <section v-if="taskPack(turn)" class="card">
                <p class="eyebrow">证据包 · 测量事实 / 规则判断</p>
                <h3>{{ taskPack(turn)?.task?.type_label }} · {{ taskPack(turn)?.task?.id }}</h3>
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
                    <span class="grade">{{ gradeLabel(item.grade) }}</span>
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

              <section v-if="perfPack(turn)" class="card">
                <h3>测参档案</h3>
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
            <button type="button" class="send" :disabled="!canSend" @click="sendText()">发送</button>
          </div>
        </div>
      </footer>
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
import type { UploadFile } from "element-plus";
import { formatError, http } from "../api/http";
import {
  formatFps,
  formatLatencyMs,
  formatParamCount,
  openAuthFile,
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
.chat-page {
  position: relative;
  height: 100vh;
  background: var(--lab-canvas);
  color: var(--lab-text);
  overflow: hidden;
}
.stage {
  height: 100%;
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.topbar {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: 18px 28px 8px;
}
.topbar h1 {
  margin: 4px 0 0;
  font-size: 22px;
}
.eyebrow {
  color: var(--lab-fiducial);
  font-family: var(--lab-font-mono);
  letter-spacing: 0.16em;
  font-size: 11px;
  margin: 0;
}
.top-actions {
  display: flex;
  gap: 8px;
}
.ghost {
  background: transparent;
  color: var(--lab-muted);
  border: 1px solid var(--lab-line);
  border-radius: 999px;
  padding: 7px 14px;
  font: inherit;
}
.ghost.on,
.ghost:hover {
  color: var(--lab-fiducial);
  border-color: var(--lab-fiducial);
}
.thread {
  flex: 1;
  overflow: auto;
  padding: 8px 24px 16px;
}
.hero {
  min-height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  gap: 16px;
  padding-bottom: 24px;
}
.hero h2 {
  margin: 0;
  font-size: 32px;
  font-weight: 650;
  letter-spacing: 0.02em;
}
.pills {
  display: flex;
  gap: 8px;
  padding: 4px;
  border-radius: 999px;
  background: var(--lab-well);
  border: 1px solid var(--lab-line);
}
.pill {
  border: 0;
  background: transparent;
  color: var(--lab-muted);
  border-radius: 999px;
  padding: 8px 18px;
  font: inherit;
}
.pill.on {
  background: var(--lab-panel);
  color: var(--lab-text);
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--lab-fiducial) 45%, transparent);
}
.suggest {
  list-style: none;
  margin: 8px 0 0;
  padding: 0;
  display: grid;
  gap: 8px;
  width: min(560px, 100%);
}
.suggest li {
  border: 1px solid var(--lab-line);
  border-radius: 999px;
  padding: 10px 16px;
  color: var(--lab-muted);
  cursor: pointer;
  text-align: left;
  background: color-mix(in srgb, var(--lab-panel) 70%, transparent);
}
.suggest li:hover {
  border-color: var(--lab-fiducial);
  color: var(--lab-text);
}
.feed {
  width: min(760px, 100%);
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding-bottom: 12px;
}
.bubble.user {
  align-self: flex-end;
  max-width: 78%;
}
.bubble.assistant {
  align-self: stretch;
}
.bubble-inner {
  padding: 12px 16px;
  border: 1px solid var(--lab-line);
  background: var(--lab-panel);
  border-radius: 16px;
}
.bubble-inner.user {
  background: color-mix(in srgb, var(--lab-fiducial) 16%, var(--lab-panel));
  border-color: color-mix(in srgb, var(--lab-fiducial) 45%, var(--lab-line));
  border-radius: 16px 16px 4px 16px;
}
.copy {
  white-space: pre-wrap;
  line-height: 1.75;
  margin: 0;
}
.copy.streaming::after {
  content: "";
  display: inline-block;
  width: 7px;
  height: 1em;
  margin-left: 3px;
  background: var(--lab-fiducial);
  vertical-align: text-bottom;
  animation: caret 1s step-end infinite;
}
@keyframes caret {
  50% {
    opacity: 0;
  }
}
@media (prefers-reduced-motion: reduce) {
  .copy.streaming::after {
    animation: none;
  }
}
.card {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--lab-line);
}
.card h3 {
  margin: 0 0 8px;
}
.facts {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 10px 16px;
}
.facts dt {
  color: var(--lab-muted);
  font-size: 12px;
}
.facts dd {
  margin: 4px 0 0;
  font-family: var(--lab-font-mono);
}
.judgements,
.viz {
  line-height: 1.7;
}
.grade {
  color: var(--lab-fiducial);
  font-family: var(--lab-font-mono);
  font-size: 12px;
  margin-right: 8px;
}
.muted,
.err,
.count,
.meta,
.rail-empty {
  color: var(--lab-muted);
  line-height: 1.7;
}
.err {
  color: var(--lab-danger);
}
.dock {
  padding: 0 24px 22px;
  display: flex;
  justify-content: center;
}
.capsule {
  width: min(760px, 100%);
  border: 1px solid var(--lab-line);
  border-radius: 22px;
  background: var(--lab-panel);
  padding: 12px 14px 10px;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.22);
}
.chips {
  display: flex;
  gap: 6px;
  margin-bottom: 8px;
}
.chip {
  background: transparent;
  color: var(--lab-muted);
  border: 1px solid transparent;
  border-radius: 999px;
  padding: 5px 12px;
  cursor: pointer;
  font: inherit;
}
.chip.on {
  color: var(--lab-fiducial);
  border-color: var(--lab-fiducial);
}
.attach {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
}
.pick {
  min-width: 240px;
  flex: 1;
}
.more {
  width: 100%;
  color: var(--lab-muted);
}
.up {
  padding: 12px;
  color: var(--lab-muted);
}
.picks {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin: 8px 0;
}
.jump {
  color: var(--lab-fiducial);
}
.input-row {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 10px;
  align-items: end;
}
.send {
  background: var(--lab-accent);
  color: #fff;
  border: 0;
  border-radius: 999px;
  padding: 8px 16px;
  font: inherit;
  min-height: 36px;
}
.send:disabled {
  opacity: 0.45;
}
.capsule :deep(.el-textarea__inner) {
  background: transparent;
  box-shadow: none;
  border-radius: 0;
  padding: 4px 2px;
}
.scrim {
  position: absolute;
  inset: 0;
  border: 0;
  background: rgba(5, 7, 10, 0.45);
  z-index: 2;
}
.drawer {
  position: absolute;
  top: 0;
  right: 0;
  width: min(300px, 86vw);
  height: 100%;
  background: var(--lab-rail);
  border-left: 1px solid var(--lab-line);
  transform: translateX(100%);
  transition: transform 0.2s ease;
  z-index: 3;
  display: flex;
  flex-direction: column;
}
.drawer.open {
  transform: translateX(0);
}
.drawer-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 18px 16px 10px;
}
.drawer-head h2 {
  margin: 0;
  font-size: 16px;
}
.session-list {
  list-style: none;
  margin: 0;
  padding: 8px;
  overflow: auto;
  flex: 1;
}
.session-list li {
  padding: 10px 12px;
  border: 1px solid transparent;
  border-radius: 10px;
  cursor: pointer;
  margin-bottom: 6px;
  background: var(--lab-panel);
}
.session-list li.on {
  border-color: var(--lab-fiducial);
}
.spec {
  display: block;
  color: var(--lab-fiducial);
  font-family: var(--lab-font-mono);
  font-size: 11px;
}
.title {
  display: block;
  margin-top: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.rail-empty {
  padding: 0 16px 16px;
  font-size: 13px;
}

@media (prefers-reduced-motion: reduce) {
  .drawer {
    transition: none;
  }
}
</style>

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
      <div><dt>参数量</dt><dd>{{ model.param_count ?? "未测量" }}</dd></div>
      <div><dt>FLOPs</dt><dd>{{ model.flops }}</dd></div>
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

    <div class="actions">
      <el-button type="primary" :disabled="!model.runnable_here" @click="goCompare">加入快速对比</el-button>
      <el-button v-if="model.log_available" @click="downloadLog">下载检查日志</el-button>
      <router-link to="/models">返回列表</router-link>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { formatError, http } from "../../api/http";
import { downloadAuthFile, failStageLabel, modelStatusLabel } from "../../api/labels";
import { ElMessage } from "element-plus";

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
};

const route = useRoute();
const router = useRouter();
const model = ref<Card | null>(null);

onMounted(async () => {
  try {
    const { data } = await http.get(`/models/${route.params.id}`);
    model.value = data;
  } catch (error) {
    ElMessage.error(formatError(error));
  }
});

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
.stages {
  color: var(--lab-muted);
  line-height: 1.7;
}
.mb {
  margin: 12px 0;
}
.actions {
  display: flex;
  gap: 16px;
  align-items: center;
  margin-top: 24px;
}
</style>

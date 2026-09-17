<template>
  <div>
    <header class="head">
      <p class="eyebrow">主功能</p>
      <h1>新建正式评测</h1>
      <p>
        仅开放预置固定测试集 <strong>NEU-20</strong>（20 张，全部有 GT）。指标对全量 20 张计算，与训练脚本同一套 4 类 mIoU；这不是论文完整 test split。拼图按文件名排序抽取前 8 张。无掩码数据不能进入正式评测。
      </p>
    </header>

    <h2>数据版本</h2>
    <p v-if="!evalSets.length" class="meta">当前没有可评测的固定测试集。请确认已种子导入 NEU-20。</p>
    <el-radio-group v-else v-model="versionId">
      <el-radio v-for="item in evalSets" :key="item.version_id" :label="item.version_id">
        {{ item.name }}
        <span class="meta">{{ item.sample_count }} 张 · 固定测试集 · 学生不可下载 GT</span>
      </el-radio>
    </el-radio-group>

    <h2>内置 baseline（1–3 个）</h2>
    <el-checkbox-group v-model="selected">
      <el-checkbox v-for="model in builtins" :key="model.id" :label="model.id">
        {{ model.name }}
        <span class="meta">{{ model.slug }} · {{ model.requires_cuda ? "需要 CUDA" : "CPU" }}</span>
      </el-checkbox>
    </el-checkbox-group>

    <h2>学生模型（可选 1 个）</h2>
    <p v-if="!students.length" class="meta">没有可运行的学生模型。导入并通过检查后会出现在这里。</p>
    <el-radio-group v-else v-model="studentId">
      <el-radio label="">不使用学生模型</el-radio>
      <el-radio v-for="model in students" :key="model.id" :label="model.id">
        {{ model.name }}
        <span class="meta">{{ modelStatusLabel(model.status) }} · {{ model.runnable_here ? "可运行" : "当前不可运行" }}</span>
      </el-radio>
    </el-radio-group>

    <div class="actions">
      <el-button type="primary" :loading="submitting" :disabled="!canSubmit" @click="submit">开始正式评测</el-button>
    </div>
    <p v-if="error" class="err">{{ error }}</p>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { formatError, http } from "../../api/http";
import { modelStatusLabel } from "../../api/labels";

type ModelCard = {
  id: string;
  name: string;
  slug: string;
  source: string;
  status: string;
  requires_cuda: boolean;
  runnable_here?: boolean;
};
type EvalSet = {
  dataset_id: string;
  name: string;
  version_id: string;
  sample_count: number;
};

const router = useRouter();
const route = useRoute();
const builtins = ref<ModelCard[]>([]);
const students = ref<ModelCard[]>([]);
const evalSets = ref<EvalSet[]>([]);
const versionId = ref("");
const selected = ref<string[]>([]);
const studentId = ref("");
const submitting = ref(false);
const error = ref("");

const canSubmit = computed(
  () =>
    Boolean(versionId.value) &&
    selected.value.length >= 1 &&
    selected.value.length <= 3,
);

onMounted(async () => {
  const [modelsRes, datasetsRes] = await Promise.all([http.get("/models"), http.get("/datasets")]);
  const grouped = (modelsRes.data.builtins as ModelCard[] | undefined) ?? (modelsRes.data.items as ModelCard[] | undefined) ?? [];
  builtins.value = grouped.filter(
    (item) => item.source === "builtin" && item.status === "runnable" && item.runnable_here !== false && !item.requires_cuda,
  );
  const mine = (modelsRes.data.mine as ModelCard[] | undefined) ?? [];
  const shared = (modelsRes.data.shared as ModelCard[] | undefined) ?? [];
  students.value = [...mine, ...shared].filter(
    (item) => item.source === "student" && item.status === "runnable" && item.runnable_here !== false && !item.requires_cuda,
  );
  const wanted = typeof route.query.baseline === "string" ? route.query.baseline : "";
  if (wanted && builtins.value.some((item) => item.id === wanted)) {
    selected.value = [wanted];
  } else {
    selected.value = builtins.value.slice(0, 3).map((item) => item.id);
  }
  const wantedStudent = typeof route.query.student === "string" ? route.query.student : "";
  if (wantedStudent && students.value.some((item) => item.id === wantedStudent)) {
    studentId.value = wantedStudent;
  }

  const sets: EvalSet[] = [];
  for (const dataset of datasetsRes.data.items ?? []) {
    for (const version of dataset.versions ?? []) {
      if (!version.eval_ready) continue;
      sets.push({
        dataset_id: dataset.id,
        name: dataset.name,
        version_id: version.id,
        sample_count: version.sample_count ?? 0,
      });
    }
  }
  evalSets.value = sets;
  versionId.value = sets[0]?.version_id ?? "";
});

async function submit() {
  submitting.value = true;
  error.value = "";
  try {
    const created = await http.post("/tasks/eval", {
      dataset_version_id: versionId.value,
      baseline_version_ids: selected.value,
      student_version_id: studentId.value || null,
    });
    await router.push(`/eval/${created.data.id}`);
  } catch (err) {
    error.value = formatError(err);
  } finally {
    submitting.value = false;
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
.meta {
  color: var(--lab-muted);
  line-height: 1.6;
}
.actions {
  margin-top: 24px;
}
.err {
  color: var(--lab-danger);
}
:deep(.el-checkbox),
:deep(.el-radio) {
  display: flex;
  margin: 8px 0;
}
</style>

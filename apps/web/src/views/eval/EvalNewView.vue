<template>
  <div class="eval-page">
    <header class="head">
      <p class="eyebrow">FIXED PROTOCOL / 正式评测</p>
      <h1>新建正式评测</h1>
      <p>在 NEU-20 固定测试集上评估模型，保留统一协议下的可追溯结果。</p>
    </header>
    <div class="eval-notice"><el-icon><InfoFilled /></el-icon><p>仅开放 <strong>NEU-20</strong>（20 张，全部有 GT）。指标对全量 20 张计算，与训练脚本同一套 4 类 mIoU；这不是论文完整 test split。无掩码数据不能进入正式评测。</p></div>

    <div class="wb-workflow">
      <div class="wb-stack">
        <section class="wb-panel">
          <div class="wb-panel-heading"><div class="section-title"><span class="wb-section-icon"><el-icon><Collection /></el-icon></span><div><h2>01 / 固定测试集</h2><p>统一数据版本，保持结果可比</p></div></div><span class="fixed-badge"><el-icon><Lock /></el-icon> 固定协议</span></div>
          <div v-if="!evalSets.length" class="dataset-empty"><el-icon><FolderOpened /></el-icon><p>当前没有可评测的固定测试集。请确认已种子导入 NEU-20。</p></div>
          <el-radio-group v-else v-model="versionId" class="dataset-choices" :disabled="submitting">
            <el-radio v-for="item in evalSets" :key="item.version_id" :label="item.version_id">
              <span class="dataset-mark"><el-icon><Picture /></el-icon></span>
              <span class="dataset-name"><strong>{{ item.name }}</strong><small>{{ item.sample_count }} 张 · 固定测试集 · 学生不可下载 GT</small></span>
              <span class="dataset-ready">GT 配对完整</span>
            </el-radio>
          </el-radio-group>
          <div class="protocol-details"><span><el-icon><CircleCheckFilled /></el-icon> 全量 20 张计分</span><span><el-icon><Picture /></el-icon> 前 8 张结果拼图</span><span><el-icon><Lock /></el-icon> GT 不提供下载</span></div>
        </section>

        <section class="wb-panel">
          <div class="wb-panel-heading"><div class="section-title"><span class="wb-section-icon"><el-icon><Cpu /></el-icon></span><div><h2>02 / 选择评测模型</h2><p>在同一份固定测试集上运行</p></div></div><span class="selection-count">已选 {{ selected.length }} 个内置模型</span></div>
          <div class="model-section-title"><h3>内置 baseline <small>至少 1 个，可全选</small></h3><div class="pick-all"><el-button link type="primary" :disabled="submitting" @click="selectAll">全选</el-button><span>·</span><el-button link :disabled="submitting" @click="selected = []">清空</el-button></div></div>
          <el-checkbox-group v-model="selected" class="wb-model-choices builtin-grid" :disabled="submitting">
            <el-checkbox v-for="model in builtins" :key="model.id" :label="model.id"><strong>{{ model.name }}</strong><span class="meta">{{ model.slug }}</span><span class="model-runtime"><el-icon><Cpu /></el-icon> {{ model.requires_cuda ? '需要 CUDA' : 'CPU 可运行' }}</span></el-checkbox>
          </el-checkbox-group>
          <p v-if="!builtins.length" class="model-empty">暂无可运行的内置模型。</p>
          <div class="student-section">
            <h3>学生模型 <small>可选 1 个</small></h3>
            <div v-if="!students.length" class="student-empty"><el-icon><Box /></el-icon><div><strong>没有可运行的学生模型</strong><p>导入并通过检查后会出现在这里。</p></div><router-link to="/models/import">导入模型 <el-icon><ArrowRight /></el-icon></router-link></div>
            <el-radio-group v-else v-model="studentId" class="wb-model-choices student-grid" :disabled="submitting">
              <el-radio label="">不使用学生模型</el-radio>
              <el-radio v-for="model in students" :key="model.id" :label="model.id"><strong>{{ model.name }}</strong><span class="meta">{{ modelStatusLabel(model.status) }} · {{ model.runnable_here ? '可运行' : '当前不可运行' }}</span></el-radio>
            </el-radio-group>
          </div>
        </section>
      </div>

      <aside class="wb-panel wb-summary eval-summary">
        <div class="section-title"><span class="wb-section-icon"><el-icon><DocumentChecked /></el-icon></span><div><h2>NEU-20 固定协议</h2><p>正式评测配置</p></div></div>
        <div class="protocol-cover"><span>FIXED TEST SET</span><strong>NEU-20</strong><p><b>20</b> 张固定图像 · 全部配对 GT</p></div>
        <dl><div><dt>计分范围</dt><dd>全量 20 张</dd></div><div><dt>结果预览</dt><dd>前 8 张</dd></div><div><dt>内置模型</dt><dd>{{ selected.length }} 个</dd></div><div><dt>学生模型</dt><dd>{{ studentId ? '已选择 1 个' : '未选择' }}</dd></div></dl>
        <div class="eval-boundary"><el-icon><InfoFilled /></el-icon><p>固定测试集 GT 不提供给学生下载。本次结果不等同于论文完整 test split。</p></div>
        <el-button type="primary" :loading="submitting" :disabled="!canSubmit" @click="submit"><el-icon><VideoPlay /></el-icon><span>开始正式评测</span></el-button>
        <p v-if="!canSubmit" class="selection-hint">请选择固定数据版本和至少 1 个内置模型。</p>
        <p v-if="error" class="err" role="alert">{{ error }}</p>
        <div class="summary-foot"><el-icon><Cpu /></el-icon> CPU 推理 · 网站不训练</div>
      </aside>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ArrowRight, Box, CircleCheckFilled, Collection, Cpu, DocumentChecked, FolderOpened, InfoFilled, Lock, Picture, VideoPlay } from "@element-plus/icons-vue";
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
  () => Boolean(versionId.value) && selected.value.length >= 1 && selected.value.length <= builtins.value.length,
);

function selectAll() {
  selected.value = builtins.value.map((item) => item.id);
}

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
    selected.value = builtins.value.map((item) => item.id);
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
  color: var(--lab-fiducial);
  font-size: 14px;
  letter-spacing: .14em;
}
.head p {
  color: var(--lab-muted);
}
.eval-notice {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 13px 16px;
  border: 1px solid #dce8f8;
  border-radius: 8px;
  background: #edf4ff;
  margin-bottom: 22px;
}
.eval-notice > .el-icon {
  flex-shrink: 0;
  margin-top: 2px;
  color: #5a8dce;
  font-size: 19px;
}
.eval-notice p {
  margin: 0;
  color: #55749a;
  font-size: 14px;
  line-height: 1.8;
}
.section-title {
  display: flex;
  align-items: center;
  gap: 11px;
  min-width: 0;
}
.section-title h2 {
  font-size: 18px;
  margin: 0;
}
.section-title p {
  font-size: 14px;
  color: var(--lab-muted);
  margin: 5px 0 0;
}
.fixed-badge {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 5px 8px;
  background: #f1f5fa;
  border-radius: 4px;
  color: #7e90a8;
  font-size: 14px;
  white-space: nowrap;
}
.dataset-choices {
  display: grid;
  width: 100%;
  gap: 10px;
}
.dataset-choices :deep(.el-radio) {
  display: flex;
  margin: 0;
  width: 100%;
  height: auto;
  border: 1px solid #dce6f3;
  border-radius: 9px;
  padding: 17px;
  background: #f9fbfe;
  box-sizing: border-box;
}
.dataset-choices :deep(.el-radio.is-checked) {
  border-color: #8bb5f6;
  background: #f3f7ff;
}
.dataset-choices :deep(.el-radio__label) {
  display: flex;
  align-items: center;
  width: 100%;
  min-width: 0;
  gap: 13px;
  padding-left: 13px;
}
.dataset-mark {
  display: grid;
  place-items: center;
  width: 43px;
  height: 43px;
  border-radius: 9px;
  background: #e5eeff;
  color: #6695db;
  font-size: 25px;
  flex-shrink: 0;
}
.dataset-name {
  min-width: 0;
}
.dataset-name strong {
  color: var(--lab-text);
  display: block;
  font-size: 17px;
}
.dataset-name small {
  color: var(--lab-muted);
  display: block;
  font-size: 14px;
  margin-top: 4px;
}
.dataset-ready {
  margin-left: auto;
  white-space: nowrap;
  font-size: 14px;
  color: #269578;
  background: #e7f6ee;
  padding: 4px 7px;
  border-radius: 4px;
}
.protocol-details {
  display: flex;
  flex-wrap: wrap;
  gap: 12px 24px;
  margin-top: 15px;
  color: #7f90a7;
  font-size: 14px;
}
.protocol-details span {
  display: flex;
  align-items: center;
  gap: 5px;
}
.protocol-details .el-icon {
  color: #88a5ca;
}
.dataset-empty {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 80px;
  border: 1px dashed #d9e4f1;
  border-radius: 8px;
  padding: 20px;
  color: #90a6c5;
  background: #f8faff;
}
.dataset-empty > .el-icon {
  font-size: 30px;
  flex-shrink: 0;
}
.dataset-empty p {
  color: var(--lab-muted);
  font-size: 15px;
  line-height: 1.8;
}
.selection-count {
  color: #6a84a8;
  background: #f0f5fc;
  border-radius: 5px;
  padding: 5px 8px;
  font-size: 14px;
  white-space: nowrap;
}
.model-section-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin: 4px 0 12px;
}
.model-section-title h3, .student-section h3 {
  margin: 0;
  font-size: 15px;
}
.model-section-title h3 small, .student-section h3 small {
  color: var(--lab-muted);
  font-weight: 400;
  font-size: 14px;
  margin-left: 6px;
}
.pick-all {
  display: flex;
  align-items: center;
  gap: 5px;
  color: #c7d3e2;
}
.pick-all .el-button {
  font-size: 14px;
  padding: 0 4px;
}
.pick-all .el-button + .el-button {
  margin-left: 0;
}
.builtin-grid {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}
.wb-model-choices :deep(.el-checkbox), .wb-model-choices :deep(.el-radio) {
  align-items: flex-start;
  min-width: 0;
  padding: 13px 12px;
}
.wb-model-choices :deep(.el-checkbox__input), .wb-model-choices :deep(.el-radio__input) {
  margin-top: 3px;
}
.wb-model-choices :deep(.el-checkbox__label), .wb-model-choices :deep(.el-radio__label) {
  min-width: 0;
  padding-left: 9px;
}
.wb-model-choices strong {
  display: block;
  font-size: 15px;
  color: var(--lab-text);
  overflow-wrap: anywhere;
}
.wb-model-choices .meta {
  font-size: 14px;
  color: var(--lab-muted);
  overflow-wrap: anywhere;
}
.model-runtime {
  display: flex;
  align-items: center;
  gap: 5px;
  margin-top: 7px;
  font-size: 14px;
  color: #7892af;
}
.model-empty {
  color: var(--lab-muted);
  font-size: 15px;
}
.student-section {
  margin-top: 22px;
  padding-top: 20px;
  border-top: 1px solid #eaf0f7;
}
.student-section h3 {
  margin-bottom: 13px;
}
.student-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}
.student-empty {
  display: flex;
  align-items: center;
  gap: 13px;
  background: #f7f9fd;
  border: 1px dashed #dce5ef;
  border-radius: 8px;
  padding: 18px;
}
.student-empty > .el-icon {
  font-size: 29px;
  color: #90a9cb;
}
.student-empty strong {
  font-weight: 500;
  font-size: 15px;
}
.student-empty p {
  font-size: 14px;
  color: var(--lab-muted);
  margin: 5px 0 0;
}
.student-empty a {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-left: auto;
  font-size: 14px;
  color: var(--lab-fiducial);
  text-decoration: none;
  white-space: nowrap;
}
.protocol-cover {
  display: flex;
  flex-direction: column;
  background: linear-gradient(135deg, #edf4ff, #e6effe);
  border: 1px solid #dce8fb;
  padding: 18px;
  border-radius: 9px;
  margin-top: 20px;
  color: #2b5d9f;
}
.protocol-cover > span {
  font-size: 14px;
  letter-spacing: .15em;
  color: #7e9ac0;
}
.protocol-cover > strong {
  font-size: 29px;
  letter-spacing: -.025em;
  margin-top: 7px;
}
.protocol-cover p {
  font-size: 14px;
  margin: 6px 0 0;
  color: #6889b2;
}
.protocol-cover b {
  font-weight: 600;
}
.wb-summary dl {
  margin: 12px 0 18px;
}
.wb-summary dd {
  font-size: 16px;
}
.eval-boundary {
  display: flex;
  gap: 7px;
  align-items: flex-start;
  padding: 11px;
  border-radius: 6px;
  background: #f3f6fb;
  color: #94a5bc;
}
.eval-boundary > .el-icon {
  flex-shrink: 0;
  margin-top: 3px;
}
.eval-boundary p {
  margin: 0;
  font-size: 14px;
  line-height: 1.8;
}
.eval-summary > .el-button {
  min-height: 44px;
  display: flex;
  gap: 7px;
  margin-top: 18px;
}
.summary-foot {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  color: #8999af;
  font-size: 14px;
  margin-top: 14px;
}
.wb-summary .selection-hint {
  font-size: 14px;
  text-align: center;
}
.wb-summary .err {
  color: var(--lab-danger);
  overflow-wrap: anywhere;
}
@media (max-width: 1250px) {
  .builtin-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .dataset-ready {
    display: none;
  }
}
@media (max-width: 600px) {
  .section-title h2 {
    font-size: 16px;
  }
  .section-title p {
    font-size: 14px;
  }
  .selection-count {
    display: none;
  }
  .dataset-mark {
    display: none;
  }
  .student-grid {
    grid-template-columns: minmax(0, 1fr);
  }
  .student-empty {
    flex-wrap: wrap;
  }
  .student-empty a {
    margin-left: 40px;
  }
}
</style>

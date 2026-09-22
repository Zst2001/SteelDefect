<template>
  <div>
    <header class="head">
      <p class="eyebrow">模型中心</p>
      <h1>性能散点图</h1>
      <p>
        先填写对比模型个数，再依次录入每个模型的横纵坐标与可选参数量。圆点大小代表参数量；未填参数量时使用固定直径（默认 5 mm，可改）。主模型固定红色，其余颜色按名称散列。本图由手填数值生成，不读取网站测量结果。
      </p>
    </header>

    <el-steps :active="step" finish-status="success" align-center class="steps">
      <el-step title="模型个数" />
      <el-step title="坐标轴" />
      <el-step title="逐个录入" />
      <el-step title="预览导出" />
    </el-steps>

    <section v-if="step === 0" class="block">
      <h2>对比模型总个数</h2>
      <el-form label-width="140px" class="form">
        <el-form-item label="模型个数">
          <el-input-number v-model="count" :min="1" :max="20" />
        </el-form-item>
      </el-form>
      <p class="muted">最少 1 个，最多 20 个。下一步会按这个数量逐个填写三维参数。</p>
    </section>

    <section v-else-if="step === 1" class="block">
      <h2>坐标轴与圆点</h2>
      <el-form label-width="140px" class="form">
        <el-form-item label="图标题">
          <el-input v-model="title" maxlength="160" />
        </el-form-item>
        <el-form-item label="横坐标含义">
          <el-input v-model="xlabel" maxlength="64" placeholder="例如 FPS、Params (M)" />
        </el-form-item>
        <el-form-item label="纵坐标含义">
          <el-input v-model="ylabel" maxlength="64" placeholder="例如 mIoU (%)、F1" />
        </el-form-item>
        <el-form-item label="缺省圆点直径">
          <el-input-number v-model="defaultMarkerMm" :min="1" :max="30" :step="0.5" />
          <span class="unit">mm</span>
        </el-form-item>
      </el-form>
      <p class="muted">某个模型未填参数量时，圆点使用这里的固定直径。有参数量时，圆点大小按组内参数量相对缩放。</p>
    </section>

    <section v-else-if="step === 2" class="block">
      <div class="block-head">
        <h2>模型 {{ cursor + 1 }} / {{ rows.length }}</h2>
        <el-tag v-if="rows[cursor]?.isMain" type="danger" effect="dark">主模型 · 红色</el-tag>
      </div>
      <el-form v-if="rows[cursor]" label-width="140px" class="form">
        <el-form-item label="名称" required>
          <el-input v-model="rows[cursor].name" maxlength="64" placeholder="例如 LGDS-Net (Our)" />
        </el-form-item>
        <el-form-item :label="xlabel || '横坐标'" required>
          <el-input-number v-model="rows[cursor].x" :controls="false" class="wide" />
        </el-form-item>
        <el-form-item :label="ylabel || '纵坐标'" required>
          <el-input-number v-model="rows[cursor].y" :controls="false" class="wide" />
        </el-form-item>
        <el-form-item label="参数量">
          <el-input-number v-model="rows[cursor].params" :controls="false" :min="0" class="wide" />
          <span class="unit">可选，单位自定（常用 M）</span>
        </el-form-item>
        <el-form-item label="主模型">
          <el-switch v-model="rows[cursor].isMain" @change="onMainChange(cursor)" />
          <span class="unit">主模型圆点固定为红色</span>
        </el-form-item>
      </el-form>
    </section>

    <section v-else class="block">
      <h2>预览与导出</h2>
      <el-table :data="rows" size="small" class="table">
        <el-table-column label="主模型" width="90">
          <template #default="{ row }">
            <span v-if="row.isMain" class="main-dot">主</span>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column prop="name" label="名称" min-width="160" />
        <el-table-column :label="xlabel || 'X'" width="120">
          <template #default="{ row }">{{ row.x }}</template>
        </el-table-column>
        <el-table-column :label="ylabel || 'Y'" width="120">
          <template #default="{ row }">{{ row.y }}</template>
        </el-table-column>
        <el-table-column label="参数量" width="120">
          <template #default="{ row }">{{ row.params == null ? "未填 · 固定直径" : row.params }}</template>
        </el-table-column>
      </el-table>
      <div class="toolbar">
        <el-button type="primary" :loading="busy" @click="preview">生成预览</el-button>
        <el-button :loading="busy" @click="exportFile('png')">导出 PNG</el-button>
        <el-button :loading="busy" @click="exportFile('pdf')">导出 PDF</el-button>
      </div>
      <p v-if="error" class="err">{{ error }}</p>
      <div v-if="previewUrl" class="preview">
        <img :src="previewUrl" alt="性能散点图预览" />
      </div>
    </section>

    <div class="toolbar footer">
      <el-button v-if="step > 0" @click="back">上一步</el-button>
      <el-button v-if="step < 3" type="primary" @click="next">下一步</el-button>
      <router-link to="/models">返回模型库</router-link>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onUnmounted, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { postAuthBlob, saveBlobFile } from "../../api/labels";

type Row = {
  name: string;
  x: number | null;
  y: number | null;
  params: number | null;
  isMain: boolean;
};

function emptyRow(isMain: boolean): Row {
  return { name: "", x: null, y: null, params: null, isMain };
}

const step = ref(0);
const count = ref(4);
const title = ref("Network Performance Comparison");
const xlabel = ref("FPS");
const ylabel = ref("mIoU (%)");
const defaultMarkerMm = ref(5);
const cursor = ref(0);
const rows = ref<Row[]>([emptyRow(true), emptyRow(false), emptyRow(false), emptyRow(false)]);
const busy = ref(false);
const error = ref("");
const previewUrl = ref("");

watch(count, (value) => {
  const nextCount = Math.max(1, Math.min(20, Math.round(Number(value) || 1)));
  const current = rows.value.slice(0, nextCount);
  while (current.length < nextCount) {
    current.push(emptyRow(current.length === 0));
  }
  if (!current.some((row) => row.isMain)) current[0].isMain = true;
  rows.value = current;
  if (cursor.value >= current.length) cursor.value = current.length - 1;
});

function onMainChange(index: number) {
  rows.value = rows.value.map((row, i) => ({ ...row, isMain: i === index }));
}

function validateAxes(): boolean {
  if (!xlabel.value.trim() || !ylabel.value.trim()) {
    ElMessage.warning("请填写横坐标和纵坐标的含义");
    return false;
  }
  return true;
}

function validateRow(index: number): boolean {
  const row = rows.value[index];
  if (!row) return false;
  if (!row.name.trim()) {
    ElMessage.warning(`请填写模型 ${index + 1} 的名称`);
    return false;
  }
  if (row.x == null || Number.isNaN(Number(row.x))) {
    ElMessage.warning(`请填写模型 ${index + 1} 的横坐标`);
    return false;
  }
  if (row.y == null || Number.isNaN(Number(row.y))) {
    ElMessage.warning(`请填写模型 ${index + 1} 的纵坐标`);
    return false;
  }
  return true;
}

function next() {
  if (step.value === 0) {
    count.value = Math.max(1, Math.min(20, Math.round(Number(count.value) || 1)));
    cursor.value = 0;
    step.value = 1;
    return;
  }
  if (step.value === 1) {
    if (!validateAxes()) return;
    cursor.value = 0;
    step.value = 2;
    return;
  }
  if (step.value === 2) {
    if (!validateRow(cursor.value)) return;
    if (cursor.value < rows.value.length - 1) {
      cursor.value += 1;
      return;
    }
    step.value = 3;
  }
}

function back() {
  if (step.value === 2 && cursor.value > 0) {
    cursor.value -= 1;
    return;
  }
  step.value = Math.max(0, step.value - 1);
}

function payload(fmt: "png" | "pdf") {
  return {
    title: title.value.trim(),
    xlabel: xlabel.value.trim(),
    ylabel: ylabel.value.trim(),
    default_marker_mm: defaultMarkerMm.value,
    fmt,
    points: rows.value.map((row) => ({
      name: row.name.trim(),
      x: Number(row.x),
      y: Number(row.y),
      params: row.params == null ? null : Number(row.params),
      is_main: Boolean(row.isMain),
    })),
  };
}

function revokePreview() {
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value);
  previewUrl.value = "";
}

async function preview() {
  error.value = "";
  busy.value = true;
  try {
    const blob = await postAuthBlob("/models/scatter", payload("png"));
    revokePreview();
    previewUrl.value = URL.createObjectURL(blob);
  } catch (err) {
    error.value = err instanceof Error ? err.message : "生成失败";
  } finally {
    busy.value = false;
  }
}

async function exportFile(fmt: "png" | "pdf") {
  error.value = "";
  busy.value = true;
  try {
    const blob = await postAuthBlob("/models/scatter", payload(fmt));
    saveBlobFile(blob, `perf_scatter.${fmt}`);
    if (fmt === "png") {
      revokePreview();
      previewUrl.value = URL.createObjectURL(blob);
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : "导出失败";
  } finally {
    busy.value = false;
  }
}

onUnmounted(revokePreview);
</script>

<style scoped>
.eyebrow {
  color: var(--lab-accent-2);
  letter-spacing: 0.16em;
  font-size: 12px;
}
.head p,
.muted,
.unit {
  color: var(--lab-muted);
  line-height: 1.7;
}
.steps {
  margin: 28px 0 8px;
}
.block {
  margin: 28px 0;
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
.form {
  max-width: 640px;
}
.wide {
  width: 220px;
}
.unit {
  margin-left: 10px;
  font-size: 13px;
}
.toolbar {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
  margin: 16px 0;
}
.footer {
  margin-top: 8px;
}
.err {
  color: #c45c4a;
}
.table {
  width: 100%;
}
.preview {
  margin-top: 16px;
  padding: 16px;
  background: #fff;
  border: 1px solid var(--lab-line);
}
.preview img {
  display: block;
  max-width: 100%;
  height: auto;
}
.main-dot {
  display: inline-block;
  padding: 0 8px;
  background: #d62728;
  color: #fff;
  font-size: 12px;
  line-height: 22px;
}
</style>

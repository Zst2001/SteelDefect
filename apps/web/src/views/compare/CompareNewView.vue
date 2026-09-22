<template>
  <div>
    <header class="head">
      <p class="eyebrow">缺陷检测</p>
      <h1>缺陷分割</h1>
      <p>
        同一批图对照内置或已导入模型。原图请用 <code>images</code> 下的 JPG 钢表面图。掩码用 <code>masks</code> 下的 PNG（看起来接近全黑，是类别索引，不是原图）。文件名主名须一致；全部配对后计算本批参考指标，缺一张则整批不计算精度。
      </p>
    </header>

    <h2>原图</h2>
    <el-upload drag multiple :auto-upload="false" :limit="50" accept=".png,.jpg,.jpeg,.tif,.tiff" :on-change="onChange" :on-remove="onRemove">
      <div class="up">将 JPG 原图拖到此处（钢表面照片，不要用 masks 里的 PNG）</div>
    </el-upload>
    <p class="count">已选 {{ fileList.length }} 张原图</p>

    <h2>配对掩码（可选）</h2>
    <el-upload drag multiple :auto-upload="false" :limit="50" accept=".png,.jpg,.jpeg,.tif,.tiff,.bmp" :on-change="onMaskChange" :on-remove="onMaskRemove">
      <div class="up">将 GT 掩码拖到此处（彩色或类别索引均可）</div>
    </el-upload>
    <p class="count">已选 {{ maskList.length }} 张掩码</p>
    <p v-if="fileList.length && maskList.length" class="meta pair" :class="{ warn: !allPaired }">
      {{ pairSummary }}
    </p>

    <h2>内置 baseline（1–3 个）</h2>
    <el-checkbox-group v-model="selected">
      <el-checkbox v-for="model in builtins" :key="model.id" :label="model.id">
        {{ model.name }}
        <span class="meta">{{ model.slug }} · {{ model.requires_cuda ? "需要 CUDA" : "CPU" }} · {{ formatFps(model.fps_per_image) === "未测量" ? "本机 FPS 未测量" : formatFps(model.fps_per_image) }}</span>
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
      <el-button type="primary" :loading="submitting" :disabled="!canSubmit" @click="submit">开始对照</el-button>
    </div>
    <p v-if="error" class="err">{{ error }}</p>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import type { UploadFile } from "element-plus";
import { formatError, http } from "../../api/http";
import { formatFps, modelStatusLabel } from "../../api/labels";

type ModelCard = {
  id: string;
  name: string;
  slug: string;
  source: string;
  status: string;
  requires_cuda: boolean;
  runnable_here?: boolean;
  fps_per_image?: number | null;
};

const router = useRouter();
const route = useRoute();
const builtins = ref<ModelCard[]>([]);
const students = ref<ModelCard[]>([]);
const selected = ref<string[]>([]);
const studentId = ref("");
const fileList = ref<File[]>([]);
const maskList = ref<File[]>([]);
const submitting = ref(false);
const error = ref("");

function stemOf(file: File) {
  return file.name.replace(/\.[^.]+$/, "");
}

const imageStems = computed(() => new Set(fileList.value.map(stemOf)));
const maskStems = computed(() => new Set(maskList.value.map(stemOf)));
const extraMasks = computed(() => [...maskStems.value].filter((key) => !imageStems.value.has(key)));
const missingMasks = computed(() => [...imageStems.value].filter((key) => !maskStems.value.has(key)));
const pairedCount = computed(() => [...imageStems.value].filter((key) => maskStems.value.has(key)).length);
const allPaired = computed(
  () => fileList.value.length > 0 && maskList.value.length > 0 && extraMasks.value.length === 0 && missingMasks.value.length === 0,
);

const pairSummary = computed(() => {
  if (!maskList.value.length) {
    return "未上传掩码：本批只出可视化，不计算精度。";
  }
  if (extraMasks.value.length) {
    return `有无法配对的掩码（${extraMasks.value.join("、")}）。文件名主名必须与图片一致。`;
  }
  if (missingMasks.value.length) {
    return `已配对 ${pairedCount.value} / ${fileList.value.length}。缺掩码：${missingMasks.value.join("、")}。缺一张则整批不计算精度。`;
  }
  return `已全部配对 ${pairedCount.value} 张，将计算本批参考指标（不代表完整测试集性能）。`;
});

const canSubmit = computed(
  () =>
    fileList.value.length >= 1 &&
    fileList.value.length <= 50 &&
    selected.value.length >= 1 &&
    selected.value.length <= 3 &&
    extraMasks.value.length === 0,
);

onMounted(async () => {
  const { data } = await http.get("/models");
  const grouped = (data.builtins as ModelCard[] | undefined) ?? (data.items as ModelCard[] | undefined) ?? [];
  builtins.value = grouped.filter(
    (item) => item.source === "builtin" && item.status === "runnable" && item.runnable_here !== false && !item.requires_cuda,
  );
  const mine = (data.mine as ModelCard[] | undefined) ?? [];
  const shared = (data.shared as ModelCard[] | undefined) ?? [];
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
});

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

async function submit() {
  submitting.value = true;
  error.value = "";
  try {
    const form = new FormData();
    for (const file of fileList.value) {
      form.append("files", file);
    }
    const uploaded = await http.post("/uploads/images", form);
    if (maskList.value.length) {
      const masks = new FormData();
      masks.append("batch_id", uploaded.data.batch_id);
      for (const file of maskList.value) {
        masks.append("files", file);
      }
      await http.post("/uploads/masks", masks);
    }
    const created = await http.post("/tasks/compare", {
      batch_id: uploaded.data.batch_id,
      baseline_version_ids: selected.value,
      student_version_id: studentId.value || null,
    });
    await router.push(`/compare/${created.data.id}`);
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
.count,
.meta {
  color: var(--lab-muted);
}
.up {
  padding: 28px 0;
  color: var(--lab-text);
}
.actions {
  margin-top: 24px;
}
.err {
  color: var(--lab-danger);
}
.pair {
  margin-top: 8px;
}
.pair.warn {
  color: var(--lab-accent);
}
:deep(.el-checkbox) {
  display: flex;
  margin: 8px 0;
}
</style>

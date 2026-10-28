<template>
  <div class="submission-page">
    <header v-if="!embedded" class="head">
      <p class="eyebrow">钢铁表面 · 语义分割</p>
      <h1>新建分割对照</h1>
      <p>在同一批原图上比较模型。配对掩码可选，全部配对后才计算本批参考指标。</p>
    </header>
    <div class="wb-workflow submission-workflow">
      <div class="wb-stack">
        <section class="wb-panel input-panel">
          <div class="wb-panel-heading">
            <div class="section-title"><span class="wb-section-icon"><el-icon><UploadFilled /></el-icon></span><div><h2>01 / 上传原图</h2><p>选择需要分割的钢铁表面图像</p></div></div>
            <span class="count-pill">{{ fileList.length }} / 50 张</span>
          </div>
          <div class="upload-preview">
            <el-upload drag multiple :disabled="submitting" :auto-upload="false" :limit="50" accept=".png,.jpg,.jpeg,.tif,.tiff" :on-change="onChange" :on-remove="onRemove">
              <div class="up"><el-icon class="upload-symbol"><UploadFilled /></el-icon><strong>拖入原图，或 <em>点击选择</em></strong><p>PNG / JPG / JPEG / TIF / TIFF</p><small>每批 1–50 张</small></div>
            </el-upload>
            <SelectedImages :files="fileList" />
          </div>
          <p class="input-note"><el-icon><InfoFilled /></el-icon>请选择 images 下的照片，勿将 masks 下的标签图当作原图。TIFF 可上传，预览以浏览器支持为准。</p>
        </section>

        <section class="wb-panel input-panel">
          <div class="wb-panel-heading">
            <div class="section-title"><span class="wb-section-icon mask-icon"><el-icon><CopyDocument /></el-icon></span><div><h2>02 / 配对掩码 <small>可选</small></h2><p>完整配对后，才计算本批参考指标</p></div></div>
            <span class="count-pill">{{ maskList.length }} 张掩码</span>
          </div>
          <div class="upload-preview">
            <el-upload drag multiple :disabled="submitting" :auto-upload="false" :limit="50" accept=".png,.jpg,.jpeg,.tif,.tiff,.bmp" :on-change="onMaskChange" :on-remove="onMaskRemove">
              <div class="up"><el-icon class="upload-symbol"><FolderOpened /></el-icon><strong>拖入掩码，或 <em>点击选择</em></strong><p>类别索引或彩色标签图</p><small>标签图不是原始照片</small></div>
            </el-upload>
            <div class="pair-preview">
              <div class="pair-heading"><span>文件配对检查</span><small>{{ pairedCount }} / {{ fileList.length }} 已配对</small></div>
              <div v-if="!fileList.length" class="pair-empty"><el-icon><Connection /></el-icon><strong>先选择原图，再检查配对</strong><p>相同文件名主名会自动配对。没有掩码也可以运行可视化对照。</p></div>
              <div v-else class="pair-list">
                <div v-for="file in fileList.slice(0, 4)" :key="file.name" class="pair-row">
                  <el-icon :class="maskStems.has(stemOf(file)) ? 'paired' : 'unpaired'"><CircleCheckFilled v-if="maskStems.has(stemOf(file))" /><Document v-else /></el-icon>
                  <span :title="file.name">{{ file.name }}</span><small :class="{ paired: maskStems.has(stemOf(file)) }">{{ maskStems.has(stemOf(file)) ? '已配对' : '无掩码' }}</small>
                </div>
                <p v-if="fileList.length > 4" class="meta">另有 {{ fileList.length - 4 }} 张，全部参与配对检查。</p>
              </div>
            </div>
          </div>
          <el-alert :title="pairSummary" :type="extraMasks.length ? 'error' : allPaired ? 'success' : 'info'" :closable="false" show-icon class="pair-status" />
        </section>

        <section class="wb-panel models-panel">
          <div class="wb-panel-heading">
            <div class="section-title"><span class="wb-section-icon"><el-icon><Cpu /></el-icon></span><div><h2>03 / 选择模型</h2><p>同一批图像，多模型并排对照</p></div></div>
            <span class="cpu-label"><el-icon><Cpu /></el-icon> CPU</span>
          </div>
          <div class="model-columns">
            <div class="builtin-column">
              <h3>内置 baseline <small>选择 1–3 个</small></h3>
              <el-checkbox-group v-model="selected" class="wb-model-choices builtin-grid" :disabled="submitting">
                <el-checkbox v-for="model in builtins" :key="model.id" :label="model.id" :disabled="selected.length >= 3 && !selected.includes(model.id)">
                  <strong>{{ model.name }}</strong><span class="meta">{{ model.slug }}</span><span class="model-detail">CPU · {{ formatFps(model.fps_per_image) === '未测量' ? '本机 FPS 未测量' : formatFps(model.fps_per_image) }}</span>
                </el-checkbox>
              </el-checkbox-group>
              <p v-if="!builtins.length" class="model-empty meta">暂无可选 baseline，请确认模型已就绪。</p>
            </div>
            <div class="student-column">
              <h3>学生模型 <small>可选 1 个</small></h3>
              <div v-if="!students.length" class="student-empty"><el-icon><Box /></el-icon><strong>还没有可运行的学生模型</strong><p>导入模型并通过检查后即可选择。</p><router-link to="/models/import">导入模型 <el-icon><ArrowRight /></el-icon></router-link></div>
              <el-radio-group v-else v-model="studentId" class="wb-model-choices" :disabled="submitting">
                <el-radio label="">不使用学生模型</el-radio>
                <el-radio v-for="model in students" :key="model.id" :label="model.id"><strong>{{ model.name }}</strong><span class="meta">{{ modelStatusLabel(model.status) }} · CPU</span></el-radio>
              </el-radio-group>
            </div>
          </div>
        </section>
      </div>

      <div class="summary-stack">
        <aside class="wb-panel wb-summary">
          <div class="section-title"><span class="wb-section-icon"><el-icon><DocumentChecked /></el-icon></span><div><h2>本次对照</h2><p>确认配置，开始实验</p></div></div>
          <div class="protocol-tag"><el-icon><Picture /></el-icon> 语义分割 · 自选图像批次</div>
          <dl>
            <div><dt>原图</dt><dd>{{ fileList.length }} <small>张</small></dd></div>
            <div><dt>已配对</dt><dd :class="{ paired: allPaired }">{{ pairedCount }} / {{ fileList.length }}</dd></div>
            <div><dt>内置模型</dt><dd>{{ selected.length }} <small>个</small></dd></div>
            <div><dt>学生模型</dt><dd>{{ studentId ? '已选择 1 个' : '未选择' }}</dd></div>
          </dl>
          <el-alert :title="allPaired ? '完整配对：计算本批参考指标' : '仅生成可视化，整批不计算精度'" :type="allPaired ? 'success' : 'info'" :closable="false" show-icon />
          <p>本批指标不代表完整测试集性能。正式评测请使用独立的 NEU-20 流程。</p>
          <el-button type="primary" :loading="submitting" :disabled="!canSubmit" @click="submit"><el-icon><VideoPlay /></el-icon><span>开始对照</span></el-button>
          <p v-if="!canSubmit" class="validation-hint">请选择 1–50 张原图和 1–3 个内置模型，并移除无法配对的多余掩码。</p>
          <p v-if="error" class="err" role="alert">{{ error }}</p>
          <div class="runtime-note"><el-icon><Cpu /></el-icon><span>CPU 推理 · 网站不训练</span></div>
        </aside>
        <section class="wb-panel pairing-help">
          <h3><el-icon><InfoFilled /></el-icon> 配对说明</h3>
          <p>按文件名主名一一对应，文件扩展名可以不同。</p>
          <div class="filename-pair"><code>steel_01.jpg</code><el-icon><Connection /></el-icon><code>steel_01.png</code></div>
          <p>不自动识别 <code>_mask</code> 后缀。缺少任意一张掩码，整批只出可视化。</p>
          <router-link class="eval-link" to="/eval/new">前往 NEU-20 正式评测 <el-icon><ArrowRight /></el-icon></router-link>
        </section>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ArrowRight, Box, CircleCheckFilled, Connection, CopyDocument, Cpu, Document, DocumentChecked, FolderOpened, InfoFilled, Picture, UploadFilled, VideoPlay } from "@element-plus/icons-vue";
import SelectedImages from "../../components/SelectedImages.vue";
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import type { UploadFile } from "element-plus";
import { formatError, http } from "../../api/http";
import { formatFps, modelStatusLabel } from "../../api/labels";

withDefaults(defineProps<{ embedded?: boolean }>(), { embedded: false });

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
// Preserve the already uploaded batch when the task POST has no known response.
// Editing any input starts a new submission, while a retry reuses its body/key.
const pendingTask = ref<{ batch_id: string; baseline_version_ids: string[]; student_version_id: string | null } | null>(null);
watch([fileList, maskList, selected, studentId], () => { pendingTask.value = null; }, { deep: true });

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
  try {
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
  } catch (err) { error.value = formatError(err); }
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
    if (!pendingTask.value) {
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
      pendingTask.value = {
        batch_id: uploaded.data.batch_id,
        baseline_version_ids: [...selected.value],
        student_version_id: studentId.value || null,
      };
    }
    const created = await http.post("/tasks/compare", pendingTask.value);
    pendingTask.value = null;
    await router.push(`/compare/${created.data.id}`);
  } catch (err) {
    error.value = formatError(err);
  } finally {
    submitting.value = false;
  }
}
</script>

<style scoped>
.submission-workflow .wb-panel {
  padding: 18px;
}
.submission-workflow .wb-stack {
  gap: 16px;
}
.eyebrow {
  color: var(--lab-fiducial);
  font-size: 14px;
  letter-spacing: .12em;
}
.head p, .meta {
  color: var(--lab-muted);
}
.section-title {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}
.section-title h2 {
  margin: 0;
  font-size: 18px;
}
.section-title p {
  margin: 4px 0 0;
  font-size: 15px;
  color: var(--lab-muted);
  line-height: 1.6;
}
.section-title h2 small {
  display: inline-block;
  color: var(--lab-muted);
  background: #f1f5fa;
  border-radius: 4px;
  padding: 2px 6px;
  font-size: 14px;
  font-weight: 400;
  margin-left: 6px;
  vertical-align: middle;
}
.count-pill {
  white-space: nowrap;
  background: #f0f5fd;
  color: #597394;
  padding: 5px 9px;
  border-radius: 5px;
  font-size: 14px;
}
.input-panel .wb-panel-heading {
  padding-bottom: 10px;
  border-bottom: 1px solid #edf1f6;
  margin-bottom: 12px;
}
.upload-preview {
  display: grid;
  grid-template-columns: minmax(0, .9fr) minmax(0, 1.25fr);
  align-items: start;
  gap: 20px;
}
.upload-preview > * {
  min-width: 0;
}
.up {
  box-sizing: border-box;
  height: 140px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 10px 5px;
}
.upload-symbol {
  font-size: 29px;
  color: #6699ed;
  margin-bottom: 10px;
}
.up strong {
  font-size: 15px;
  font-weight: 500;
  line-height: 1.6;
}
.up em {
  font-style: normal;
  color: var(--lab-fiducial);
}
.up p {
  margin: 6px 0 3px;
  font-size: 14px;
  color: var(--lab-muted);
}
.up small {
  color: #8392a8;
  font-size: 14px;
}
:deep(.el-upload) {
  display: block;
  width: 100%;
}
:deep(.el-upload-dragger) {
  padding: 0 10px;
  border-style: dashed;
  border-color: #bacfea;
  border-radius: 9px;
}
:deep(.el-upload-list) {
  max-height: 125px;
  overflow-y: auto;
}
.input-note {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin: 9px 0 0;
  color: var(--lab-muted);
  font-size: 14px;
  line-height: 1.6;
}
.input-note .el-icon {
  flex-shrink: 0;
  margin-top: 3px;
}
.pair-heading {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 8px;
  font-size: 15px;
  font-weight: 600;
}
.pair-heading small {
  color: var(--lab-muted);
  font-weight: 400;
}
.pair-empty {
  box-sizing: border-box;
  height: 116px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  padding: 10px 12px;
  background: #f6f9fd;
  border: 1px solid #e7edf5;
  border-radius: 9px;
  text-align: center;
}
.pair-empty > .el-icon {
  font-size: 26px;
  color: #94accb;
  margin-bottom: 8px;
}
.pair-empty strong {
  font-size: 15px;
  font-weight: 500;
}
.pair-empty p {
  margin: 5px 0 0;
  color: var(--lab-muted);
  font-size: 15px;
  line-height: 1.5;
}
.pair-row {
  display: flex;
  gap: 7px;
  align-items: center;
  min-width: 0;
  padding: 7px 0;
  border-bottom: 1px solid #edf1f6;
  font-size: 15px;
}
.pair-row > span {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.pair-row small {
  font-size: 14px;
  color: var(--lab-muted);
  white-space: nowrap;
}
.paired {
  color: #149f78 !important;
}
.unpaired {
  color: #657a96;
}
.pair-status {
  margin-top: 10px;
  overflow-wrap: anywhere;
}
.pair-status :deep(.el-alert__title) {
  font-size: 15px;
}
.cpu-label {
  display: inline-flex;
  gap: 5px;
  align-items: center;
  font-size: 14px;
  color: #408775;
  background: #eef9f5;
  border-radius: 4px;
  padding: 5px 7px;
}
.model-columns {
  display: grid;
  grid-template-columns: minmax(0, 1.5fr) minmax(0, 1fr);
  gap: 20px;
}
.model-columns h3 {
  font-size: 15px;
  margin: 0 0 12px;
}
.model-columns h3 small {
  font-weight: 400;
  color: var(--lab-muted);
  margin-left: 6px;
  font-size: 14px;
}
.builtin-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}
.student-column {
  border-left: 1px solid #e9eff6;
  padding-left: 20px;
  min-width: 0;
}
.wb-model-choices :deep(.el-checkbox), .wb-model-choices :deep(.el-radio) {
  min-width: 0;
  align-items: flex-start;
  padding: 12px 10px;
}
.wb-model-choices :deep(.el-checkbox__input), .wb-model-choices :deep(.el-radio__input) {
  margin-top: 3px;
}
.wb-model-choices :deep(.el-checkbox__label), .wb-model-choices :deep(.el-radio__label) {
  min-width: 0;
  padding-left: 8px;
  font-size: 15px;
}
.wb-model-choices strong {
  display: block;
  color: var(--lab-text);
  font-size: 17px;
  font-weight: 600;
  overflow-wrap: anywhere;
}
.wb-model-choices .meta {
  font-size: 14px;
  overflow-wrap: anywhere;
}
.model-detail {
  display: block;
  color: #71819a;
  font-size: 14px;
  margin-top: 5px;
}
.student-empty {
  box-sizing: border-box;
  min-height: 140px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  background: #f7f9fc;
  border: 1px dashed #d8e2ef;
  border-radius: 8px;
  padding: 16px 8px;
  text-align: center;
}
.student-empty > .el-icon {
  font-size: 30px;
  color: #8ba4c4;
  margin-bottom: 12px;
}
.student-empty strong {
  font-weight: 500;
  font-size: 15px;
}
.student-empty p {
  font-size: 15px;
  line-height: 1.7;
  color: var(--lab-muted);
}
.student-empty a {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 15px;
  color: var(--lab-fiducial);
  text-decoration: none;
}
.summary-stack {
  position: sticky;
  top: 24px;
  display: grid;
  gap: 18px;
  min-width: 0;
}
.summary-stack .wb-summary {
  position: static;
}
.protocol-tag {
  display: flex;
  gap: 7px;
  align-items: center;
  padding: 10px 12px;
  margin-top: 18px;
  background: #f2f6fd;
  border-radius: 6px;
  font-size: 14px;
  color: #5274a3;
}
.wb-summary dl {
  margin: 8px 0 18px;
}
.wb-summary dd {
  font-size: 16px;
}
.wb-summary dd small {
  font-size: 14px;
  font-weight: 400;
  color: var(--lab-muted);
}
.wb-summary > .el-button {
  min-height: 43px;
  display: flex;
  gap: 7px;
  margin-top: 18px;
  font-size: 16px;
}
.wb-summary :deep(.el-alert__title) {
  font-size: 14px;
}
.wb-summary p {
  font-size: 15px;
}
.wb-summary .validation-hint {
  font-size: 14px;
}
.runtime-note {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  color: #8493aa;
  margin-top: 14px;
}
.pairing-help h3 {
  display: flex;
  gap: 8px;
  align-items: center;
  font-size: 16px;
  margin: 0 0 12px;
}
.pairing-help h3 .el-icon {
  color: var(--lab-fiducial);
}
.pairing-help p {
  color: var(--lab-muted);
  font-size: 15px;
  line-height: 1.8;
}
.filename-pair {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 5px;
  background: #f4f7fb;
  padding: 10px;
  border-radius: 6px;
  color: #5b7292;
  font-size: 14px;
}
.eval-link {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--lab-fiducial);
  text-decoration: none;
  font-size: 15px;
}
.meta {
  font-size: 14px;
  line-height: 1.7;
}
.wb-summary .err {
  color: var(--lab-danger);
  overflow-wrap: anywhere;
}
@media (max-width: 1250px) {
  .model-columns {
    grid-template-columns: minmax(0, 1fr);
  }
  .student-column {
    border-left: 0;
    padding-left: 0;
    border-top: 1px solid #e9eff6;
    padding-top: 16px;
  }
  .student-empty {
    min-height: 100px;
  }
}
@media (max-width: 1000px) {
  .summary-stack {
    position: static;
    grid-template-columns: minmax(0, 1.2fr) minmax(0, 1fr);
    align-items: start;
  }
}
@media (max-width: 680px) {
  .upload-preview, .summary-stack {
    grid-template-columns: minmax(0, 1fr);
  }
  .wb-panel-heading {
    align-items: flex-start;
  }
  .count-pill {
    font-size: 14px;
  }
  .section-title {
    gap: 8px;
  }
  .section-title h2 {
    font-size: 16px;
  }
  .section-title p {
    font-size: 14px;
  }
}
</style>

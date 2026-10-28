<template>
  <div class="demo-page">
    <header class="head demo-head">
      <div>
        <p class="eyebrow">PUBLIC DEMO / 公开体验</p>
        <h1>钢铁表面缺陷分割演示</h1>
        <p>选择预备样例与内置模型，查看实际推理生成的分割效果。</p>
      </div>
      <span class="demo-badge"><el-icon><View /></el-icon> 无需上传 · 即选即用</span>
    </header>

    <div class="demo-notice">
      <el-icon><InfoFilled /></el-icon>
      <div>
        <strong>本页不计算、不存储、不展示精度</strong>
        <span>{{ disclaimer }}</span>
      </div>
    </div>
    <el-alert v-if="quotaHit" type="warning" show-icon :closable="false" class="mb" :title="quotaText">
      <el-button class="login-link" link type="warning" @click="goLogin">登录后继续</el-button>
    </el-alert>
    <p v-else-if="error" class="err" role="alert">{{ error }}</p>
    <div v-if="catalogError" class="catalog-error" role="alert"><el-icon><InfoFilled /></el-icon><div><strong>演示目录暂不可用</strong><p>{{ catalogError }}</p></div><el-button :loading="loadingCatalog" @click="loadCatalog">重新加载目录</el-button></div>

    <div class="demo-grid">
      <section class="wb-panel samples-panel">
        <div class="wb-panel-heading">
          <div class="section-title">
            <span class="step-number">01</span>
            <div><h2>选择样例</h2><p>点选 1–5 张预备图像</p></div>
          </div>
          <span class="selection-counter">{{ selectedKeys.length }} / 5</span>
        </div>
        <div class="catalog-toolbar">
          <span>共 {{ samples.length }} 张</span>
          <span>{{ selectedKeys.length >= 5 ? '已选满，再次点击可取消' : '点击缩略图选择或取消' }}</span>
        </div>
        <div v-if="loadingCatalog" class="catalog-empty">
          <el-icon><Picture /></el-icon><strong>正在读取样例目录…</strong><p>样例图像将显示在这里</p>
        </div>
        <div v-else-if="!samples.length" class="catalog-empty">
          <el-icon><Picture /></el-icon><strong>{{ catalogError ? '样例目录未就绪' : '暂无可用预备样例' }}</strong><p>样例就绪后即可选择并开始演示。</p>
        </div>
        <div v-else class="tray" role="group" aria-label="预备样例">
          <button
            v-for="sample in samples"
            :key="sample.sample_key"
            type="button"
            class="coupon"
            :class="{ on: selectedKeys.includes(sample.sample_key), full: selectedKeys.length >= 5 && !selectedKeys.includes(sample.sample_key) }"
            :aria-pressed="selectedKeys.includes(sample.sample_key)"
            :disabled="submitting"
            @click="toggleSample(sample.sample_key)"
          >
            <div class="sample-image">
              <img :src="sample.preview_url" :alt="sample.sample_key" />
              <span class="sample-check" aria-hidden="true"><el-icon v-if="selectedKeys.includes(sample.sample_key)"><Check /></el-icon></span>
            </div>
            <span class="sample-name" :title="sample.sample_key">{{ sample.sample_key }}</span>
            <small class="sample-size">{{ sample.width }} × {{ sample.height }}</small>
          </button>
        </div>
        <p class="catalog-scroll-note">在样例区域内滚动，查看全部图像。</p>
        <div v-if="legend.length" class="legend">
          <span class="legend-title">分割类别</span>
          <span v-for="item in legend" :key="item.id" class="chip"><i :style="{ background: item.color }"></i>{{ item.name }}</span>
        </div>
        <p class="catalog-note"><el-icon><InfoFilled /></el-icon>样例只供直观体验，不代表测试集性能。</p>
      </section>

      <section class="wb-panel demo-models">
        <div class="wb-panel-heading">
          <div class="section-title">
            <span class="step-number">02</span>
            <div><h2>选择模型</h2><p>选择 1–3 个内置模型</p></div>
          </div>
          <span class="selection-counter">{{ selectedModels.length }} / 3</span>
        </div>
        <el-checkbox-group v-model="selectedModels" class="wb-model-choices" :disabled="submitting">
          <el-checkbox
            v-for="model in models"
            :key="model.id"
            :label="model.id"
            :disabled="selectedModels.length >= 3 && !selectedModels.includes(model.id)"
          >
            <strong>{{ model.name }}</strong>
            <span class="model-specs">
              <span class="model-spec"><span>CPU 前向速度</span><b>{{ formatFps(model.fps_per_image) }}</b></span>
              <span class="model-spec"><span>参数量</span><b>{{ formatParamCount(model.param_count) }}</b></span>
            </span>
          </el-checkbox>
        </el-checkbox-group>
        <p v-if="!models.length" class="model-empty">{{ loadingCatalog ? '正在读取可用模型…' : catalogError ? '目录读取失败，请使用上方按钮重试。' : '暂无可用内置模型。' }}</p>
        <div class="model-footnote"><el-icon><Cpu /></el-icon><p>速度来自已完成的本机 CPU 测量：batch=1、随机输入，仅计前向。暂无测量记录时显示“未测量”。</p></div>
        <div class="model-footnote model-policy"><el-icon><Lock /></el-icon><p>使用平台内置模型，无上传和学生模型入口。</p></div>
      </section>

      <div class="demo-summary-stack">
        <aside class="wb-panel wb-summary">
          <div class="wb-panel-heading">
            <div class="section-title">
              <span class="step-number">03</span>
              <div><h2>提交演示</h2><p>确认本次选择</p></div>
            </div>
          </div>
          <dl>
            <div><dt>预备样例</dt><dd>{{ selectedKeys.length }} <small>/ 5 张</small></dd></div>
            <div><dt>内置模型</dt><dd>{{ selectedModels.length }} <small>/ 3 个</small></dd></div>
            <div><dt>运行环境</dt><dd><span class="cpu-badge">CPU</span></dd></div>
          </dl>
          <el-alert title="只出可视化，不计算精度" type="info" :closable="false" show-icon />
          <el-button type="primary" :loading="submitting" :disabled="!canSubmit" @click="submit">
            <el-icon><VideoPlay /></el-icon><span>开始演示</span>
          </el-button>
          <p v-if="!canSubmit" class="selection-hint">请选择至少 1 张样例和 1 个模型。</p>
          <div class="quota-note"><el-icon><Clock /></el-icon><p>访客滚动 24 小时内最多成功入队 3 次；登录后不计这 3 次。</p></div>
        </aside>
        <section class="wb-panel next-step">
          <span class="next-step-icon"><el-icon><DataAnalysis /></el-icon></span>
          <div><h3>对照自己的图像</h3><p>登录后上传原图，比较模型。</p><router-link to="/workbench">进入实验台 <el-icon><ArrowRight /></el-icon></router-link></div>
        </section>
      </div>
    </div>
    <p class="result-note"><el-icon><InfoFilled /></el-icon>任务完成后可查看分割掩码与叠加图；结果由本次任务实际推理生成。</p>
  </div>
</template>

<script setup lang="ts">
import { ArrowRight, Check, Clock, Cpu, DataAnalysis, InfoFilled, Lock, Picture, VideoPlay, View } from "@element-plus/icons-vue";
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { asApiError, formatError, http } from "../../api/http";
import { formatFps, formatParamCount } from "../../api/labels";

type Sample = { sample_key: string; width: number; height: number; preview_url: string };
type ModelCard = { id: string; name: string; slug: string; fps_per_image?: number | null; param_count?: number | null };
type Legend = { id: number; name: string; color: string };

const router = useRouter();
const samples = ref<Sample[]>([]);
const models = ref<ModelCard[]>([]);
const legend = ref<Legend[]>([]);
const disclaimer = ref("公开演示 / 预备样例 / 不代表测试集性能");
const selectedKeys = ref<string[]>([]);
const selectedModels = ref<string[]>([]);
const submitting = ref(false);
const error = ref("");
const quotaHit = ref(false);
const quotaText = ref("");
const loadingCatalog = ref(true);
const catalogError = ref("");
let catalogRequest = 0;
onBeforeUnmount(() => { catalogRequest += 1; });

const canSubmit = computed(
  () =>
    !loadingCatalog.value && !catalogError.value &&
    selectedKeys.value.length >= 1 &&
    selectedKeys.value.length <= 5 &&
    selectedModels.value.length >= 1 &&
    selectedModels.value.length <= 3,
);

function toggleSample(key: string) {
  const idx = selectedKeys.value.indexOf(key);
  if (idx >= 0) {
    selectedKeys.value.splice(idx, 1);
    return;
  }
  if (selectedKeys.value.length >= 5) return;
  selectedKeys.value.push(key);
}

function goLogin() {
  void router.push({ path: "/login", query: { redirect: "/demo" } });
}

async function loadCatalog() {
  const request = ++catalogRequest;
  loadingCatalog.value = true;
  catalogError.value = "";
  try {
    const [catalog, listed] = await Promise.all([http.get("/demo/samples"), http.get("/demo/models")]);
    if (request !== catalogRequest) return;
    samples.value = catalog.data.items ?? [];
    legend.value = catalog.data.legend ?? [];
    if (catalog.data.disclaimer) disclaimer.value = catalog.data.disclaimer;
    models.value = listed.data.items ?? [];
    selectedKeys.value = selectedKeys.value.filter(key => samples.value.some(sample => sample.sample_key === key));
    selectedModels.value = selectedModels.value.filter(id => models.value.some(model => model.id === id));
  } catch (err) {
    if (request === catalogRequest) catalogError.value = formatError(err);
  } finally { if (request === catalogRequest) loadingCatalog.value = false; }
}
onMounted(loadCatalog);

async function submit() {
  submitting.value = true;
  error.value = "";
  quotaHit.value = false;
  try {
    const created = await http.post("/demo/tasks", {
      sample_keys: selectedKeys.value,
      baseline_version_ids: selectedModels.value,
    });
    await router.push(`/demo/${created.data.id}`);
  } catch (err) {
    const parsed = asApiError(err);
    if (parsed.code === "DEMO_QUOTA") {
      quotaHit.value = true;
      quotaText.value = parsed.message;
    } else {
      error.value = formatError(err);
    }
  } finally {
    submitting.value = false;
  }
}
</script>

<style scoped>
.eyebrow {
  color: var(--lab-fiducial);
  font-size: 14px;
  letter-spacing: .1em;
}
.demo-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 20px;
  margin-bottom: 18px;
}
.demo-head p {
  color: var(--lab-muted);
  font-size: 16px;
  margin: 6px 0 0;
}
.demo-badge {
  display: flex;
  align-items: center;
  flex-shrink: 0;
  gap: 6px;
  padding: 8px 11px;
  border: 1px solid #d6e5fb;
  border-radius: 7px;
  background: #eaf3ff;
  color: #315d94;
  font-size: 14px;
}
.demo-notice {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 11px 15px;
  margin-bottom: 18px;
  border: 1px solid #dbe9fb;
  border-radius: 8px;
  background: #edf5ff;
  color: #54749b;
}
.demo-notice > .el-icon {
  flex-shrink: 0;
  color: #4584dd;
  font-size: 19px;
}
.demo-notice div {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 14px;
  font-size: 14px;
  line-height: 1.6;
}
.demo-notice strong {
  font-size: 15px;
  font-weight: 500;
  color: #2c619e;
}
.demo-grid {
  display: grid;
  grid-template-columns: minmax(0, .95fr) minmax(390px, 1.3fr) minmax(250px, .8fr);
  align-items: start;
  gap: 18px;
}
.demo-grid .wb-panel {
  padding: 18px;
}
.demo-grid .wb-panel-heading {
  gap: 8px;
  margin-bottom: 14px;
  padding-bottom: 13px;
  border-bottom: 1px solid #e8eef6;
}
.section-title {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}
.step-number {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  flex-shrink: 0;
  border: 1px solid #cfdef7;
  border-radius: 9px;
  background: #edf3ff;
  color: #326cc9;
  font-size: 15px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.section-title h2 {
  margin: 0;
  font-size: 20px;
}
.section-title p {
  margin: 4px 0 0;
  font-size: 14px;
  line-height: 1.5;
  color: var(--lab-muted);
}
.selection-counter {
  padding: 5px 8px;
  border-radius: 5px;
  background: #edf3ff;
  color: var(--lab-fiducial);
  font-size: 14px;
  white-space: nowrap;
}
.catalog-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 10px;
  color: var(--lab-muted);
  font-size: 14px;
  line-height: 1.5;
}
.tray {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(96px, 1fr));
  align-content: start;
  gap: 10px;
  max-height: 344px;
  margin: 0;
  padding: 3px 6px 3px 3px;
  overflow-y: auto;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
  scrollbar-width: thin;
  scrollbar-color: #c2d3e9 #f3f6fb;
}
.coupon {
  min-width: 0;
  padding: 5px 5px 8px;
  border: 1px solid #dce5f0;
  border-radius: 7px;
  background: #fff;
  color: var(--lab-text);
  text-align: left;
  overflow: hidden;
  cursor: pointer;
  transition: border-color .16s ease, box-shadow .16s ease;
}
.coupon:hover:not(:disabled) {
  border-color: #8bb5f6;
  box-shadow: 0 3px 8px #246bfd12;
}
.coupon:focus-visible {
  outline: 3px solid #9ec4ff;
  outline-offset: 1px;
}
.coupon.on {
  border-color: #246bfd;
  box-shadow: 0 0 0 1px #246bfd;
  background: #f2f7ff;
}
.coupon.full {
  opacity: .55;
}
.sample-image {
  position: relative;
  display: flex;
  justify-content: center;
  width: 100%;
  max-width: 112px;
  height: 104px;
  margin: 0 auto;
  border-radius: 4px;
  background: #eaf0f6;
  overflow: hidden;
}
.sample-image img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: contain;
}
.sample-check {
  position: absolute;
  top: 5px;
  right: 5px;
  display: grid;
  place-items: center;
  width: 18px;
  height: 18px;
  border: 1px solid #ffffffc7;
  border-radius: 4px;
  background: #ffffffdc;
  color: #fff;
  box-shadow: 0 1px 4px #00000015;
}
.on .sample-check {
  background: #246bfd;
  border-color: #246bfd;
}
.sample-name {
  display: block;
  padding: 7px 2px 2px;
  font-size: 15px;
  line-height: 1.4;
  text-overflow: ellipsis;
  white-space: nowrap;
  overflow: hidden;
}
.sample-size {
  display: block;
  padding: 0 2px;
  font-size: 14px;
  line-height: 1.4;
  color: #536781;
}
.catalog-scroll-note {
  margin: 8px 0 12px;
  color: #536781;
  font-size: 14px;
  line-height: 1.5;
}
.legend {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 7px 11px;
  padding: 12px 0;
  border-top: 1px solid #edf1f7;
  border-bottom: 1px solid #edf1f7;
}
.legend-title, .chip {
  color: var(--lab-muted);
  font-size: 14px;
}
.chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}
.chip i {
  display: block;
  width: 8px;
  height: 8px;
  border-radius: 2px;
}
.catalog-note, .result-note {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin: 11px 0 0;
  color: var(--lab-muted);
  font-size: 14px;
  line-height: 1.6;
}
.catalog-note .el-icon, .result-note .el-icon {
  flex-shrink: 0;
  margin-top: 3px;
}
.result-note {
  margin-top: 16px;
}
.catalog-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 220px;
  margin-bottom: 12px;
  padding: 16px;
  border: 1px dashed #dce5f1;
  border-radius: 8px;
  background: #f5f8fd;
  text-align: center;
}
.catalog-empty > .el-icon {
  margin-bottom: 14px;
  color: #91abce;
  font-size: 32px;
}
.catalog-empty strong {
  font-size: 16px;
  font-weight: 500;
}
.catalog-empty p {
  font-size: 14px;
  color: var(--lab-muted);
}
.demo-models {
  container-type: inline-size;
}
.demo-models .wb-model-choices {
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}
.wb-model-choices :deep(.el-checkbox) {
  min-width: 0;
  min-height: 140px;
  position: relative;
  align-items: flex-start;
  box-sizing: border-box;
  padding: 14px 12px;
}
.wb-model-choices :deep(.el-checkbox__input) {
  position: absolute;
  top: 19px;
  left: 12px;
}
.wb-model-choices :deep(.el-checkbox__inner) {
  width: 16px;
  height: 16px;
}
.wb-model-choices :deep(.el-checkbox__inner::after) {
  left: 5px;
  top: 2px;
}
.wb-model-choices :deep(.el-checkbox__label) {
  min-width: 0;
  padding-left: 0;
  width: 100%;
}
.wb-model-choices strong {
  display: block;
  padding-left: 26px;
  min-height: 26px;
  margin-bottom: 12px;
  font-size: 18px;
  line-height: 1.4;
  font-weight: 600;
  color: var(--lab-text);
  overflow-wrap: anywhere;
}
.model-specs {
  display: grid;
  gap: 8px;
  padding-top: 10px;
  border-top: 1px solid #dfe7f2;
}
.model-spec {
  display: flex;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 3px 8px;
  font-size: 14px;
  line-height: 1.5;
  color: #52657d;
}
.model-spec b {
  color: #243c5d;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.wb-model-choices :deep(.el-checkbox:not(.is-disabled):hover) {
  border-color: #80a6e2;
  box-shadow: 0 3px 12px #246bfd12;
}
.wb-model-choices :deep(.el-checkbox.is-checked) {
  border-color: #246bfd;
  box-shadow: 0 0 0 1px #246bfd;
}
.model-footnote.model-policy {
  border-top: 0;
  margin-top: 8px;
  padding-top: 0;
}
.model-footnote {
  display: flex;
  align-items: flex-start;
  gap: 7px;
  margin-top: 15px;
  padding-top: 13px;
  border-top: 1px solid #edf1f7;
  color: #536781;
}
.model-footnote > .el-icon {
  flex-shrink: 0;
  margin-top: 3px;
}
.model-footnote p, .model-empty {
  margin: 0;
  color: var(--lab-muted);
  font-size: 14px;
  line-height: 1.6;
}
.demo-summary-stack {
  position: sticky;
  top: 24px;
  display: grid;
  min-width: 0;
  gap: 16px;
}
.demo-summary-stack .wb-summary {
  position: static;
}
.wb-summary dl {
  margin: 0 0 16px;
}
.wb-summary dl > div {
  padding: 11px 0;
}
.wb-summary dt {
  font-size: 16px;
}
.wb-summary dd {
  font-size: 22px;
}
.wb-summary dd small {
  color: var(--lab-muted);
  font-size: 14px;
  font-weight: 400;
}
.cpu-badge {
  padding: 4px 8px;
  border-radius: 4px;
  background: #eaf8f2;
  color: #2b957a;
  font-size: 14px;
}
.wb-summary :deep(.el-alert__title) {
  font-size: 14px;
}
.wb-summary > .el-button {
  display: flex;
  gap: 7px;
  min-height: 44px;
  margin-top: 16px;
  font-size: 17px;
}
.wb-summary .selection-hint {
  font-size: 14px;
  text-align: center;
}
.quota-note {
  display: flex;
  align-items: flex-start;
  gap: 7px;
  margin-top: 15px;
  color: #536781;
}
.quota-note > .el-icon {
  flex-shrink: 0;
  margin-top: 3px;
}
.quota-note p {
  margin: 0;
  font-size: 14px;
  line-height: 1.7;
}
.next-step {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  border-color: #dce8fa;
  background: #f2f7fe;
}
.next-step-icon {
  display: grid;
  place-items: center;
  flex-shrink: 0;
  width: 32px;
  height: 32px;
  border-radius: 9px;
  background: #e5efff;
  color: #3267ac;
  font-size: 22px;
}
.next-step h3 {
  margin: 0;
  font-size: 16px;
}
.next-step p {
  margin: 5px 0 8px;
  color: var(--lab-muted);
  font-size: 14px;
  line-height: 1.6;
}
.next-step a {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  color: var(--lab-fiducial);
  font-size: 15px;
  text-decoration: none;
}
.mb {
  margin-bottom: 18px;
}
.catalog-error { display: flex; align-items: center; gap: 14px; padding: 18px 20px; margin-bottom: 20px; border: 1px solid #e5cbbd; border-radius: 10px; background: #fffbf7; color: #75523b; }
.catalog-error > .el-icon { flex: none; font-size: 22px; }
.catalog-error > div { min-width: 0; flex: 1; }
.catalog-error strong { font-size: 16px; }
.catalog-error p { margin: 5px 0 0; font-size: 14px; overflow-wrap: anywhere; }
@media (max-width: 600px) { .catalog-error { flex-wrap: wrap; }.catalog-error > .el-button { margin-left: 36px; } }
.err {
  color: var(--lab-danger);
  overflow-wrap: anywhere;
}
@media (max-width: 1350px) {
  .demo-grid {
    grid-template-columns: minmax(0, .9fr) minmax(0, 1.1fr);
  }
  .demo-summary-stack {
    position: static;
    grid-column: 1 / -1;
    grid-template-columns: minmax(0, 1.4fr) minmax(0, 1fr);
    align-items: start;
  }
  .demo-summary-stack .wb-summary dl {
    display: flex;
    gap: 18px;
  }
  .demo-summary-stack .wb-summary dl > div {
    flex: 1;
    flex-wrap: wrap;
    gap: 6px;
  }
  .tray {
    max-height: 330px;
  }
}
@media (max-width: 700px) {
  .demo-head {
    display: block;
  }
  .demo-badge {
    display: inline-flex;
    margin-top: 10px;
  }
  .demo-grid, .demo-summary-stack {
    grid-template-columns: minmax(0, 1fr);
  }
  .demo-summary-stack {
    grid-column: auto;
  }
  .demo-models .wb-model-choices {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .wb-model-choices :deep(.el-checkbox) {
    padding: 14px 12px;
  }
  .tray {
    grid-template-columns: repeat(auto-fill, minmax(90px, 1fr));
    max-height: 260px;
    gap: 8px;
  }
  .sample-image {
    height: 96px;
  }
}
@media (max-width: 400px) {
  .demo-grid .wb-panel {
    padding: 15px;
  }
  .demo-summary-stack .wb-summary dl {
    display: block;
  }
  .catalog-toolbar {
    flex-wrap: wrap;
  }
}
@container (max-width: 350px) {
  .demo-models .wb-model-choices {
    grid-template-columns: minmax(0, 1fr);
  }
}
@media (prefers-reduced-motion: reduce) {
  .coupon { transition: none; }
}
</style>

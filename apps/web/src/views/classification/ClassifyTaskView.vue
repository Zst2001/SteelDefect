<template>
  <div class="cls-scope classification-result">
    <header class="head"><p class="eyebrow">CLASSIFICATION / 分类结果</p><div class="result-title"><h1>钢铁缺陷分类结果</h1><TaskStatus v-if="task" :status="task.status" /></div><p class="cls-code">任务 {{ taskId }}</p></header>
    <div class="result-links cls-actions"><router-link to="/inspect/steel/classification">新建分类</router-link><router-link to="/records">结果记录</router-link><el-button v-if="task?.result_download_url" :loading="downloading" :disabled="!!loadError" @click="downloadResult">下载分类结果 JSON</el-button></div>
    <div v-if="loading && !task" class="cls-state" role="status">正在读取分类结果…</div>
    <div v-if="loadError" class="cls-state error" role="alert"><strong>分类结果暂不可用</strong><p>{{ loadError }}</p><el-button :loading="loading" @click="refresh">重新加载</el-button></div>
    <p v-if="downloadError" class="cls-error" role="alert">{{ downloadError }}</p>
    <template v-if="task">
      <aside class="cls-notice"><strong>六类已知缺陷 · 不含正常 / 良品类</strong><p>模型得分为 softmax 输出，不是经过校准的正确概率。该结果不能排除未知缺陷，也不能判断图像是否合格。</p></aside>
      <div v-if="task.error_summary" class="cls-state error task-error" role="alert"><strong>任务提示</strong><p>{{ task.error_summary }}</p></div>
      <div v-if="pending" class="cls-state pending-state" role="status"><strong>{{ task.status === 'queued' ? '任务已排队' : '正在进行 CPU 分类' }}</strong><p>按模型依次执行，结果完成后自动更新。可以离开此页，稍后从结果记录继续查看。</p></div>
      <section class="cls-panel execution-panel">
        <div class="cls-panel-head"><div><h2>执行概况</h2><p>{{ task.n }} 张原图 · {{ task.models.length }} 个内置模型 · {{ task.has_gt ? '已提供完整图级标签' : '未提供图级标签' }}</p></div></div>
        <div v-for="model in task.models" :key="model.model_version_id" class="execution-row"><strong>{{ model.name }}</strong><TaskStatus :status="model.status" /><p v-if="model.fail_message" class="cls-error">{{ model.fail_message }}</p></div>
      </section>
      <section v-if="task.has_gt && task.metrics?.available" class="cls-panel metrics-panel" aria-label="本批分类指标">
        <div class="cls-panel-head"><div><h2>本批分类指标</h2><p>仅依据本批 {{ task.metrics.n ?? task.n }} 张完整标签计算；不代表现场泛化性能。</p></div></div>
        <article v-for="metric in task.metrics.models ?? []" :key="metric.model_version_id" class="model-metrics">
          <h3>{{ modelName(metric.model_version_id) }}</h3><dl class="metric-values"><div><dt>Accuracy</dt><dd>{{ percentage(metric.accuracy) }}</dd></div><div><dt>Macro-F1</dt><dd>{{ percentage(metric.macro_f1) }}</dd></div></dl>
          <details><summary>查看混淆矩阵</summary><p class="cls-muted">行表示真实类别，列表示预测类别；单元格为图像数量。</p><div class="matrix-scroll"><table class="confusion-matrix"><caption class="sr-only">{{ modelName(metric.model_version_id) }} 混淆矩阵</caption><thead><tr><th scope="col">真实 / 预测</th><th v-for="label in task.classes" :key="label.id" scope="col">{{ label.display_zh }}</th></tr></thead><tbody><tr v-for="(row, index) in metric.confusion_matrix" :key="index"><th scope="row">{{ className(index) }}</th><td v-for="(value, column) in row" :key="column" :class="{ diagonal: index === column }">{{ value }}</td></tr></tbody></table></div></details>
        </article>
      </section>
      <aside v-else class="metrics-unavailable" role="note">{{ task.has_gt ? '本批指标尚不可用；待模型完成并生成完整预测后查看。' : '本批未提供真实标签，指标不可用；不计算 Accuracy、Macro-F1 或混淆矩阵。' }}</aside>
      <section class="cls-panel predictions-panel">
        <div class="cls-panel-head"><div><h2>逐图预测</h2><p>同一张图像对应各模型的 Top-1 类别与 Top-3 得分</p></div><span class="cls-count">{{ task.samples.length }} 张</span></div>
        <p v-if="!task.samples.length" class="cls-muted">暂无可展示的样本。</p>
        <article v-for="sample in visibleSamples" :key="sample.sample_key" class="sample-result">
          <div class="sample-source"><img v-if="sample.preview_url" :src="sample.preview_url" :alt="sample.filename || sample.sample_key" loading="lazy" /><div v-else class="preview-unavailable">原图暂不可用</div><strong>{{ sample.filename || sample.sample_key }}</strong><span v-if="task.has_gt && sample.class_id != null" class="gt-label">真实标签：{{ className(sample.class_id) }}</span></div>
          <div class="sample-predictions"><div v-for="model in task.models" :key="model.model_version_id" class="prediction-row"><div class="prediction-head"><strong>{{ model.name }}</strong><span v-if="prediction(sample.sample_key, model.model_version_id)" class="top-label">{{ prediction(sample.sample_key, model.model_version_id)?.display_zh }}</span><span v-else class="cls-muted">{{ model.status === 'failed' ? '该模型执行失败' : pending ? '等待预测' : '无可用预测' }}</span></div><ol v-if="prediction(sample.sample_key, model.model_version_id)" class="top-scores" aria-label="Top-3 模型得分"><li v-for="(score, rank) in prediction(sample.sample_key, model.model_version_id)?.topk.slice(0, 3)" :key="score.class_id"><span class="score-rank">{{ rank + 1 }}</span><span class="score-name">{{ score.display_zh }}</span><span class="score-track" aria-hidden="true"><i :style="{ width: `${Math.max(0, Math.min(100, score.score * 100))}%` }"></i></span><b>{{ percentage(score.score) }}</b></li></ol></div></div>
        </article>
        <div v-if="task.samples.length > pageSize" class="result-pager"><el-button :disabled="pageIndex === 0" @click="pageIndex--">上一页</el-button><span>{{ pageIndex + 1 }} / {{ Math.ceil(task.samples.length / pageSize) }}</span><el-button :disabled="(pageIndex + 1) * pageSize >= task.samples.length" @click="pageIndex++">下一页</el-button></div>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useRoute } from "vue-router";
import TaskStatus from "../../components/TaskStatus.vue";
import { formatError, http } from "../../api/http";
import { saveBlobFile } from "../../api/labels";
import type { ClassificationTask } from "./types";
import "./classification.css";

const route = useRoute();
const taskId = computed(() => String(route.params.taskId ?? ""));
const task = ref<ClassificationTask | null>(null), loadError = ref(""), downloadError = ref("");
const loading = ref(false), downloading = ref(false), pageIndex = ref(0);
const pageSize = 8;
let generation = 0, disposed = false, timer: ReturnType<typeof setTimeout> | undefined;
const pending = computed(() => ["queued", "running"].includes(task.value?.status ?? ""));
const visibleSamples = computed(() => task.value?.samples.slice(pageIndex.value * pageSize, (pageIndex.value + 1) * pageSize) ?? []);
const predictionMap = computed(() => new Map((task.value?.predictions ?? []).map(row => [`${row.sample_key}:${row.model_version_id}`, row])));
function prediction(key: string, model: string) { return predictionMap.value.get(`${key}:${model}`); }
function modelName(id: string) { return task.value?.models.find(model => model.model_version_id === id)?.name ?? id; }
function className(id: number) { return task.value?.classes.find(label => label.id === id)?.display_zh ?? String(id); }
function percentage(value: number) { return Number.isFinite(value) ? `${(value * 100).toFixed(2)}%` : "—"; }
function stopTimer() { if (timer) clearTimeout(timer); timer = undefined; }
async function refresh() {
  if (loading.value || disposed) return;
  stopTimer(); loading.value = true; loadError.value = "";
  const current = generation, id = taskId.value;
  try {
    const { data } = await http.get<ClassificationTask>(`/tasks/${id}`);
    if (disposed || generation !== current) return;
    if (data.type !== "classification") throw new Error("该任务不是钢铁缺陷分类任务，请从结果记录打开对应详情。");
    task.value = data;
    if (pageIndex.value * pageSize >= data.samples.length) pageIndex.value = 0;
    if (["queued", "running"].includes(data.status)) timer = setTimeout(() => void refresh(), 2500);
  } catch (err) { if (!disposed && generation === current) loadError.value = formatError(err); }
  finally { if (!disposed && generation === current) loading.value = false; }
}
async function downloadResult() {
  const id = taskId.value, current = generation, url = task.value?.result_download_url;
  if (!url || downloading.value || loadError.value || url !== `/api/tasks/${id}/file/classification.json`) return;
  downloading.value = true; downloadError.value = "";
  try {
    const { data } = await http.get(url.replace(/^\/api/, ""));
    if (!disposed && current === generation) saveBlobFile(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }), `${id}_classification.json`);
  } catch (err) { if (!disposed && current === generation) downloadError.value = formatError(err); }
  finally { if (!disposed && current === generation) downloading.value = false; }
}
watch(taskId, () => { generation++; stopTimer(); loading.value = false; task.value = null; pageIndex.value = 0; downloading.value = false; downloadError.value = ""; void refresh(); }, { immediate: true });
onBeforeUnmount(() => { disposed = true; generation++; stopTimer(); });
</script>

<style scoped>
.result-title { display: flex; align-items: center; flex-wrap: wrap; gap: 14px; }.result-title h1 { margin: 0 !important; }
.result-links { margin-bottom: 20px; gap: 18px; font-size: 14px; }
.classification-result > .cls-panel, .classification-result > .cls-state { margin-bottom: 20px; }
.execution-row { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; border-top: 1px solid #e9eef5; padding: 13px 0; }
.execution-row > strong { min-width: 180px; font-size: 16px; }.execution-row > p { width: 100%; margin: 0; }
.metrics-unavailable { margin: 20px 0; padding: 14px 17px; border: 1px solid #dce5f1; border-radius: 8px; color: #4f627b; font-size: 14px; line-height: 1.8; }
.model-metrics { border-top: 1px solid #e4ebf5; padding: 16px 0; }.model-metrics h3 { margin: 0 0 14px; font-size: 17px; }
.metric-values { display: flex; gap: 32px; flex-wrap: wrap; margin: 0 0 18px; }.metric-values dt { color: #4f627b; font-size: 14px; }.metric-values dd { margin: 6px 0 0; color: #24528a; font-size: 24px; font-weight: 600; font-variant-numeric: tabular-nums; }
.model-metrics summary { cursor: pointer; color: #225ed0; font-size: 14px; padding: 7px 0; }.matrix-scroll { max-width: 100%; overflow-x: auto; }.confusion-matrix { border-collapse: collapse; width: 100%; min-width: 540px; font-size: 13px; text-align: center; }.confusion-matrix th, .confusion-matrix td { padding: 10px 7px; border: 1px solid #e0e8f2; }.confusion-matrix th { background: #f5f8fc; color: #3e5a7b; font-weight: 500; }.diagonal { background: #edf5ff; color: #225a9c; font-weight: 600; }
.sample-result { display: grid; grid-template-columns: 150px minmax(0, 1fr); gap: 24px; border-top: 1px solid #e3eaf3; padding: 22px 0; }.sample-source { min-width: 0; }.sample-source img, .preview-unavailable { display: block; width: 150px; height: 150px; background: #edf2f8; border-radius: 7px; object-fit: contain; }.preview-unavailable { display: grid; place-items: center; color: #4f627b; font-size: 13px; }.sample-source > strong { display: block; font-size: 14px; margin-top: 10px; overflow-wrap: anywhere; line-height: 1.6; }.gt-label { display: block; margin-top: 5px; color: #28715b; font-size: 13px; }
.sample-predictions { display: grid; gap: 16px; }.prediction-row { padding: 15px 17px; border: 1px solid #e2eaf4; background: #f9fbfe; border-radius: 8px; }.prediction-head { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px; }.prediction-head > strong { font-size: 16px; overflow-wrap: anywhere; }.top-label { color: #245a98; background: #eaf2ff; border-radius: 5px; padding: 4px 9px; font-size: 15px; font-weight: 600; }
.top-scores { margin: 14px 0 0; padding: 0; list-style: none; display: grid; gap: 8px; }.top-scores li { display: grid; grid-template-columns: 15px 98px minmax(30px, 1fr) 68px; align-items: center; gap: 9px; font-size: 13px; }.score-rank { color: #71839a; font-family: var(--lab-font-mono); }.score-name { color: #415c7a; }.score-track { height: 6px; background: #e6edf6; border-radius: 3px; overflow: hidden; }.score-track i { display: block; height: 100%; background: #6d9bd7; border-radius: 3px; }.top-scores b { font-variant-numeric: tabular-nums; color: #365573; font-weight: 500; text-align: right; }
.result-pager { display: flex; justify-content: center; gap: 15px; align-items: center; color: #4f627b; font-size: 14px; border-top: 1px solid #e5ecf4; padding-top: 18px; }.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); }
@media (max-width: 600px) { .sample-result { grid-template-columns: minmax(0, 1fr); gap: 15px; }.sample-source { display: grid; grid-template-columns: 78px minmax(0, 1fr); column-gap: 12px; align-items: center; }.sample-source img, .preview-unavailable { grid-row: span 2; width: 78px; height: 78px; }.sample-source > strong { margin: 0; }.prediction-row { padding: 12px; }.top-scores li { grid-template-columns: 12px 85px minmax(20px, 1fr) 60px; gap: 5px; font-size: 12px; } }
</style>

<template>
  <div class="pcb-scope">
    <PcbTabs classification />
    <header class="pcb-head"><div><p class="pcb-eyebrow">PCB / ROI 分类结果</p><h1>PCB 缺陷分类结果</h1><p class="pcb-code">任务 {{ taskId }}</p></div><TaskStatus v-if="task && !loadError" :status="task.status" /></header>
    <p class="pcb-note">仅适用于已裁剪单缺陷 ROI。没有正常类，不提供定位；六类概率与置信度均不是准确率。</p>
    <div class="pcb-actions roi-links"><router-link to="/inspect/pcb/classification">新建分类</router-link><router-link to="/records?type=pcb_classify">历史记录 · 再跑 / 提交导师 / 撤回</router-link></div>
    <div v-if="loading && !task" class="pcb-state" role="status">正在读取分类任务…</div>
    <div v-if="loadError" class="pcb-state error" role="alert"><strong>任务暂不可用</strong><p>{{ loadError }}</p><el-button @click="refresh">重新加载</el-button></div>
    <template v-if="task && !loadError">
      <div v-if="pending" class="pcb-state" role="status"><strong>{{ task.status === 'queued' ? '任务已排队' : '正在进行 CPU 分类' }}</strong><p>自动读取服务端状态。离开页面不会取消任务，可稍后从历史记录查看。</p><p v-if="task.error_summary">{{ task.error_summary }}</p></div>
      <div v-else-if="task.status === 'failed'" class="pcb-state error" role="alert"><strong>本次分类未完成</strong><p>{{ task.error_summary || '请检查图像或联系管理员核查服务状态。' }}</p></div>
      <section v-if="task.status === 'success' && result" class="pcb-panel">
        <div class="pcb-panel-head"><div><h2>{{ task.model?.name }}</h2><p>单张 ROI · {{ task.protocol_id }}</p></div><el-button :loading="downloading" @click="download">下载结果 JSON</el-button></div>
        <div class="roi-result-grid">
          <figure class="roi-figure"><div class="pcb-frame roi-image"><img v-if="preview && !imageFailed" :src="preview" alt="模型输入 ROI 灰度预览" @error="imageFailed = true" /><span v-else class="pcb-muted">预览暂不可用</span></div><figcaption>模型输入预览 · 224 × 224 灰度<br />只显示 ROI，不绘制检测框或热力图</figcaption></figure>
          <div><p class="roi-prediction-label">预测类别</p><h2 class="roi-prediction">{{ result.label_zh }} <small>{{ result.label_en }}</small></h2><p class="roi-confidence">置信度 <strong>{{ percent(result.confidence) }}</strong></p>
            <div class="roi-probabilities" aria-label="六类概率"><div v-for="label in task.classes" :key="label.class_id" class="roi-probability"><div><span>{{ label.label_zh }} <small>{{ label.label_en }}</small></span><strong>{{ percent(result.probabilities[label.class_id]) }}</strong></div><meter :value="result.probabilities[label.class_id]" min="0" max="1" :aria-label="`${label.label_zh}概率`" :aria-valuetext="percent(result.probabilities[label.class_id])" /></div></div>
          </div>
        </div>
        <p v-if="result.input_adapted" class="pcb-note roi-adapted">{{ result.adaptation_notice || '已进行灰度或尺寸转换，训练集准确率不保证适用于此图。' }}</p><p v-else class="pcb-muted">输入为原生 224 × 224 灰度 PNG，预处理保留原始像素。</p>
        <details class="roi-identity"><summary>查看输入与模型标识</summary><p class="pcb-code">模型 {{ task.model?.id }}<br />输入 SHA-256 {{ result.sample_sha256 }}</p></details>
        <p v-if="downloadError" class="pcb-error" role="alert">{{ downloadError }}</p>
      </section>
      <div v-else-if="task.status === 'success'" class="pcb-state error" role="alert"><p>结果数据未通过六类契约校验，请重新加载或联系管理员。</p><el-button :loading="loading" @click="refresh">重新加载结果</el-button></div>
    </template>
  </div>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useRoute } from "vue-router";
import TaskStatus from "../../components/TaskStatus.vue";
import { http, formatError } from "../../api/http";
import { saveBlobFile } from "../../api/labels";
import PcbTabs from "./PcbTabs.vue";
import { checkedRoiResult, ROI_PROTOCOL, type RoiTask } from "./classification-types";
import "./pcb.css";
const route = useRoute(), taskId = computed(() => String(route.params.taskId || "")), task = ref<RoiTask | null>(null);
const loading = ref(false), loadError = ref(""), imageFailed = ref(false), downloading = ref(false), downloadError = ref("");
let disposed = false, generation = 0, timer:ReturnType<typeof setTimeout> | undefined;
const pending = computed(() => ["queued","running"].includes(task.value?.status || ""));
const result = computed(() => checkedRoiResult(task.value));
const preview = computed(() => Array.isArray(task.value?.artifacts) ? task.value.artifacts.find(a => a?.kind === "origin" && a.url === `/api/tasks/${encodeURIComponent(taskId.value)}/file/origin/image.png`)?.url : undefined);
function percent(n:number) {
  if (n > 0 && n < .0001) return "<0.01%";
  if (n < 1 && n > .9999) return ">99.99%";
  return `${(n*100).toFixed(2)}%`;
}
function stop() { if (timer) clearTimeout(timer); timer = undefined; }
async function refresh() {
  if (loading.value || disposed) return;
  stop(); const current = generation, id = taskId.value; loading.value = true; loadError.value = "";
  try {
    const {data} = await http.get<RoiTask>(`/tasks/${encodeURIComponent(id)}`);
    if (disposed || current !== generation) return;
    if (data.id !== id || data.type !== "pcb_classify" || data.scene !== "pcb" || data.task_kind !== "classification" || data.protocol_id !== ROI_PROTOCOL) throw new Error("该任务不是当前协议的 PCB 分类任务，请从历史记录打开正确详情。");
    if (!["queued","running","success","failed"].includes(data.status)) throw new Error("无法识别任务状态，请重新加载或联系管理员。");
    task.value = data; imageFailed.value = false;
    if (pending.value) timer = setTimeout(() => void refresh(),2500);
  } catch(err) { if (!disposed && current === generation) loadError.value = formatError(err); }
  finally { if (!disposed && current === generation) loading.value = false; }
}
async function download() {
  const current = generation, id = taskId.value, url = task.value?.result_download_url;
  if (!result.value || url !== `/api/tasks/${encodeURIComponent(id)}/file/pcb_classification.json` || downloading.value) return;
  downloading.value = true; downloadError.value = "";
  try {
    const {data} = await http.get(url.replace(/^\/api/,""));
    if (disposed || current !== generation) return;
    if (!checkedRoiResult(task.value, data)) throw new Error("下载内容未通过当前任务的六类契约校验，未保存文件。请重新加载或联系管理员。");
    saveBlobFile(new Blob([JSON.stringify(data,null,2)],{type:"application/json"}), `${id}_pcb_classification.json`);
  } catch(err) { if (!disposed && current === generation) downloadError.value = formatError(err); }
  finally { if (!disposed && current === generation) downloading.value = false; }
}
watch(taskId, () => { generation++; stop(); task.value = null; loadError.value = ""; loading.value = false; downloading.value = false; downloadError.value = ""; void refresh(); }, {immediate:true});
onBeforeUnmount(() => { disposed = true; generation++; stop(); });
</script>
<style scoped>
.roi-links { margin-bottom:22px; font-size:14px; }.roi-result-grid { display:grid; grid-template-columns:minmax(0,.8fr) minmax(0,1fr); gap:32px; }.roi-figure { margin:0; min-width:0; }.roi-image { min-height:315px; padding:20px; }.roi-image img { width:224px; height:224px; image-rendering:pixelated; }.roi-figure figcaption { margin-top:12px; font-size:14px; color:#516983; line-height:1.8; }.roi-prediction-label { color:#516983; font-size:14px; margin:0 0 8px; }.roi-prediction { font-size:30px !important; }.roi-prediction small { font-size:17px; font-weight:400; color:#516983; }.roi-confidence { font-size:15px; color:#476483; margin-bottom:22px; }.roi-confidence strong { font-size:22px; color:#24528a; margin-left:9px; }.roi-probabilities { display:grid; gap:12px; }.roi-probability>div { display:flex; justify-content:space-between; gap:10px; font-size:15px; color:#294967; }.roi-probability small { color:#617b96; font-size:12px; }.roi-probability strong { font-size:14px; font-variant-numeric:tabular-nums; }meter { display:block; width:100%; height:12px; margin-top:3px; }meter::-webkit-meter-bar { background:#edf2f8; border:none; border-radius:3px; }meter::-webkit-meter-optimum-value { background:#547fc3; border-radius:3px; }.roi-adapted { margin-top:24px; }.roi-identity { border-top:1px solid #e3eaf3; margin-top:20px; padding-top:16px; }.roi-identity summary { color:#315e96; cursor:pointer; font-size:14px; }
@media(max-width:850px) { .roi-result-grid { grid-template-columns:minmax(0,1fr); gap:24px; }.roi-image { min-height:260px; } }
</style>

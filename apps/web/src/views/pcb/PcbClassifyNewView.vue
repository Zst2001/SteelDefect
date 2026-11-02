<template>
  <div class="pcb-scope pcb-classify">
    <PcbTabs classification />
    <header class="pcb-head"><div><p class="pcb-eyebrow">PCB / 单缺陷 ROI 六分类</p><h1>PCB 缺陷分类工作台</h1><p>先裁剪，再识别。选择一张以单个缺陷为主的 ROI 图片。</p></div><span class="pcb-pill">CPU · 单张图片</span></header>
    <p class="pcb-note">本功能不包含正常类，不提供整板定位、自动裁框或分割。置信度表示模型的六类倾向，不是准确率。</p>
    <div v-if="loading" class="pcb-state" role="status">正在检查分类模型准入…</div>
    <div v-else-if="catalogError" class="pcb-state error" role="alert"><strong>模型目录读取失败</strong><p>{{ catalogError }}</p><el-button @click="loadCatalog">重试目录</el-button></div>
    <div v-else-if="!ready" class="pcb-state" role="status"><strong>PCB 分类暂未启用</strong><p>两模型须通过本机 CPU 准入，并由管理员开启独立分类开关。已有结果仍可查看。</p><el-button @click="loadCatalog">重新检查状态</el-button></div>
    <div class="roi-grid">
      <section class="pcb-panel"><div class="pcb-panel-head"><div><h2>已裁剪的缺陷 ROI</h2><p>单张 PNG / JPEG，最大 2 MiB</p></div><span class="pcb-pill">推荐 224 × 224 灰度</span></div>
        <div class="pcb-frame roi-preview"><img v-if="preview" :src="preview" alt="待分类 ROI 预览" /><div v-else class="roi-placeholder"><strong>选择单缺陷局部图像</strong><p>请先在站外完成裁剪</p><span>不上传整板图进行缺陷定位</span></div></div>
        <div class="pcb-actions roi-upload"><el-button :disabled="!ready || submitting || validating" @click="input?.click()">{{ file ? '更换 ROI' : '选择 ROI' }}</el-button><el-button v-if="file || imageError" :disabled="submitting" @click="clearImage">移除 ROI</el-button><span class="pcb-muted roi-filename">{{ file?.name || '尚未选择图像' }}</span></div>
        <input ref="input" class="pcb-file-input" type="file" accept=".png,.jpg,.jpeg" aria-label="PCB 分类 ROI" :disabled="!ready || submitting" @change="choose" />
        <p v-if="validating" role="status" class="pcb-muted">正在校验图片…</p><p v-if="imageError" class="pcb-error" role="alert">{{ imageError }}</p>
        <p v-if="size" class="pcb-muted">原图 {{ size }}。最终格式和像素由服务端核验。</p>
        <p class="pcb-muted">原生 224 × 224 灰度 PNG 保留像素；其他合法 ROI 按冻结协议转为灰度并双线性缩放。转换不保证训练集准确率适用于此图。</p>
      </section>
      <div class="roi-stack">
        <section class="pcb-panel"><div class="pcb-panel-head"><div><h2>选择分类模型</h2><p>固定内置模型 · 共享同一六类协议</p></div></div>
          <label class="roi-model-label" for="roi-model">本次使用的模型</label><select id="roi-model" v-model="selected" :disabled="!ready || submitting"><option v-for="model in catalog?.models || []" :key="model.model_id" :value="model.model_id" :disabled="!model.available">{{ model.name }}{{ model.default ? '（默认）' : '（轻量备选）' }}</option></select>
          <p class="pcb-muted">{{ selectedModel ? `参数量 ${formatParamCount(selectedModel.params)}` : '等待准入目录' }} · CPU 推理</p>
          <div class="roi-classes" aria-label="六类缺陷"><span v-for="label in catalog?.classes || []" :key="label.class_id">{{ label.label_zh }}<small>{{ label.label_en }}</small></span></div>
        </section>
        <section class="pcb-panel"><h2>开始分类</h2><p class="pcb-muted">图片和模型身份随任务冻结，结果仅对您及明确提交后的导师可见。</p>
          <p v-if="submitError" class="pcb-error" role="alert">{{ submitError }}</p><p v-if="batch && submitError" class="pcb-muted">上传已保存，重试沿用同一批次及幂等请求。</p>
          <el-button class="roi-submit" type="primary" :disabled="!canSubmit" :loading="submitting" @click="submit">{{ submitting ? stage : '开始 PCB 分类' }}</el-button>
          <p class="pcb-muted">关闭页面不会取消任务。可在历史记录查看、再跑、提交导师或撤回。</p><router-link to="/records?type=pcb_classify">查看 PCB 分类历史 →</router-link>
        </section>
      </div>
    </div>
  </div>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { formatError, http } from "../../api/http";
import { formatParamCount } from "../../api/labels";
import PcbTabs from "./PcbTabs.vue";
import type { RoiCatalog } from "./classification-types";
import "./pcb.css";
const router = useRouter(), catalog = ref<RoiCatalog | null>(null), loading = ref(true), catalogError = ref("");
const file = ref<File | null>(null), preview = ref(""), input = ref<HTMLInputElement | null>(null), size = ref(""), imageError = ref("");
const selected = ref(""), submitting = ref(false), validating = ref(false), submitError = ref(""), stage = ref(""), batch = ref("");
let disposed = false, revision = 0, request = 0;
// An uncertain response may already have created a task. Returning to a model
// must reuse its request key, even after another model was selected or retried.
const requestKeys = new Map<string,string>();
const ready = computed(() => catalog.value?.enabled === true && catalog.value?.available === true && catalog.value.models.length === 2 && catalog.value.models.every(m => m.available));
const selectedModel = computed(() => catalog.value?.models.find(m => m.model_id === selected.value));
const canSubmit = computed(() => ready.value && !loading.value && !catalogError.value && !!file.value && !imageError.value && !validating.value && !submitting.value && !!selectedModel.value?.available);
watch(selected, () => { submitError.value = ""; });
function clearImage() {
  if (submitting.value) return;
  revision++;
  if (preview.value) URL.revokeObjectURL(preview.value);
  preview.value = ""; file.value = null; size.value = ""; batch.value = "";
  validating.value = false; imageError.value = ""; submitError.value = ""; requestKeys.clear();
}
async function loadCatalog() {
  const current = ++request; loading.value = true; catalogError.value = "";
  try { const {data} = await http.get<RoiCatalog>("/scenes/pcb/classification/models"); if (!disposed && current === request) { catalog.value = data; selected.value = data.default_model; } }
  catch (err) { if (!disposed && current === request) catalogError.value = formatError(err); }
  finally { if (!disposed && current === request) loading.value = false; }
}
async function choose(event:Event) {
  const element = event.target as HTMLInputElement, chosen = element.files?.[0]; element.value = "";
  if (!chosen || !ready.value || submitting.value) return;
  const current = ++revision; validating.value = true; imageError.value = ""; let url = "";
  try {
    if (!chosen.size || chosen.size > 2097152 || !/\.(png|jpe?g)$/i.test(chosen.name)) throw new Error("请选择非空 PNG/JPEG，单张不超过 2 MiB。");
    const bytes = new Uint8Array(await chosen.slice(0, 16).arrayBuffer());
    const png = [137,80,78,71,13,10,26,10].every((n,i) => bytes[i] === n), jpeg = bytes[0] === 255 && bytes[1] === 216 && bytes[2] === 255;
    if (!(png && /\.png$/i.test(chosen.name) || jpeg && /\.jpe?g$/i.test(chosen.name))) throw new Error("文件内容与扩展名不一致。");
    url = URL.createObjectURL(chosen); const image = new Image(); image.src = url; await image.decode();
    if (image.naturalWidth * image.naturalHeight > 16777216) throw new Error("图像像素超过 4096²，请先裁剪 ROI。");
    if (disposed || current !== revision) return;
    if (preview.value) URL.revokeObjectURL(preview.value);
    preview.value = url; url = ""; file.value = chosen; size.value = `${image.naturalWidth} × ${image.naturalHeight}`;
    batch.value = ""; requestKeys.clear(); submitError.value = "";
  } catch (err) { if (!disposed && current === revision) imageError.value = err instanceof Error ? err.message : "无法解码图像"; }
  finally { if (url) URL.revokeObjectURL(url); if (!disposed && current === revision) validating.value = false; }
}
async function submit() {
  if (!canSubmit.value || !file.value) return;
  submitting.value = true; submitError.value = ""; stage.value = "正在上传…";
  try {
    if (!batch.value) { const form = new FormData(); form.append("file", file.value); const {data} = await http.post("/scenes/pcb/classification/uploads", form); if (disposed) return; batch.value = data.batch_id; }
    const identity = `${batch.value}\0${selected.value}`;
    let idempotencyKey = requestKeys.get(identity);
    if (!idempotencyKey) { idempotencyKey = crypto.randomUUID(); requestKeys.set(identity, idempotencyKey); }
    stage.value = "正在提交…";
    const {data} = await http.post("/scenes/pcb/classification/tasks", {batch_id:batch.value, model_id:selected.value}, {headers:{"Idempotency-Key":idempotencyKey}});
    if (!disposed) await router.push(`/inspect/pcb/classification/tasks/${encodeURIComponent(data.id)}`);
  } catch (err) { if (!disposed) submitError.value = formatError(err); }
  finally { if (!disposed) submitting.value = false; }
}
onMounted(loadCatalog);
onBeforeUnmount(() => { disposed = true; revision++; request++; if (preview.value) URL.revokeObjectURL(preview.value); });
</script>
<style scoped>
.roi-grid { display:grid; grid-template-columns:minmax(0,1.05fr) minmax(0,1fr); gap:22px; align-items:start; }.roi-stack { display:grid; gap:20px; min-width:0; }.roi-preview { min-height:290px; padding:20px; background:#f1f5f9; }.roi-preview img { width:224px; height:224px; }.roi-placeholder { text-align:center; color:#516983; line-height:1.8; }.roi-placeholder strong { font-size:18px; color:#294967; }.roi-placeholder span { font-size:14px; }.roi-upload { margin-top:18px; }.roi-filename { overflow-wrap:anywhere; min-width:0; }.roi-model-label { display:block; color:#476483; font-size:14px; margin-bottom:9px; }select { width:100%; font:inherit; color:#203b5c; background:#f8faff; border:1px solid #becfe4; padding:12px; border-radius:7px; min-width:0; }.roi-classes { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:9px; margin-top:20px; }.roi-classes>span { padding:10px; background:#f3f6fa; border-radius:6px; font-size:15px; color:#294967; }.roi-classes small { display:block; margin-top:4px; color:#58728c; font-size:12px; }.roi-submit { width:100%; min-height:44px; }
@media(max-width:1050px) { .roi-grid { grid-template-columns:minmax(0,1fr); } } @media(max-width:600px) { .roi-preview { min-height:250px; }.pcb-panel-head { flex-wrap:wrap; } }
</style>

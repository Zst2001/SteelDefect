<template>
  <div class="models-page">
    <header class="head">
      <p class="eyebrow">模型中心</p>
      <h1>模型库</h1>
      <p>内置 baseline 只读。学生模型经自动检查后才能加入对比；不能启动的模型会标明失败阶段。</p>
    </header>

    <div class="toolbar">
      <router-link to="/models/import" class="import-link"><el-icon><UploadFilled /></el-icon>导入 .py + .pth</router-link>
      <nav class="related-links" aria-label="模型相关页面">
        <router-link to="/models/perf">去模型测评</router-link>
        <router-link to="/models/scatter">性能散点图</router-link>
        <router-link to="/compare/new">去缺陷分割<el-icon><ArrowRight /></el-icon></router-link>
      </nav>
    </div>

    <div v-if="error" class="load-state error-state" role="alert"><el-icon><WarningFilled /></el-icon><div><strong>模型目录暂不可用</strong><p>{{ error }}</p></div><el-button :loading="loading" @click="loadList">重新加载</el-button></div>
    <div v-else-if="loading && !loaded" class="load-state" role="status"><el-icon><Box /></el-icon><div><strong>正在读取模型目录</strong><p>正在获取可访问的模型版本与测参档案。</p></div></div>
    <template v-if="loaded">
    <section class="block">
      <div class="block-head"><div><h2>内置 baseline <span>{{ builtins.length }}</span></h2><p>查看内置模型版本与本机测参档案</p></div></div>
      <div v-if="!builtins.length" class="empty-state"><span class="empty-icon"><el-icon><Box /></el-icon></span><div><h3>暂无可用的内置模型</h3><p>内置模型就绪后将在这里显示。</p></div></div>
      <div v-else class="cards">
        <router-link v-for="model in builtins" :key="model.id" class="card" :to="`/models/${model.id}`">
          <div class="card-head"><span class="model-icon"><el-icon><Box /></el-icon></span><span class="status-tag">{{ modelStatusLabel(model.status) }}</span></div>
          <div class="name">{{ model.name }}</div>
          <div class="meta">{{ model.slug }} · 语义分割</div>
          <div class="model-specs"><div><span>参数量</span><strong>{{ formatParamCount(model.param_count) }}</strong></div><div><span>本机前向</span><strong>{{ formatFps(model.fps_per_image) }}</strong></div></div>
          <div class="card-foot"><span>{{ model.requires_cuda ? "当前环境不可运行" : "CPU" }}</span><span>查看模型卡<el-icon><ArrowRight /></el-icon></span></div>
        </router-link>
      </div>
    </section>

    <section class="block">
      <div class="block-head"><div><h2>我的导入 <span>{{ mine.length }}</span></h2><p>已上传的源码与权重版本，以及自动检查结果</p></div></div>
      <div v-if="!mine.length" class="empty-state"><span class="empty-icon"><el-icon><UploadFilled /></el-icon></span><div><h3>还没有学生模型</h3><p>从导入入口提交 .py 与 .pth，通过隔离检查后即可用于对比。</p></div><router-link to="/models/import">导入模型<el-icon><ArrowRight /></el-icon></router-link></div>
      <div v-else class="cards">
        <router-link v-for="model in mine" :key="model.id" class="card" :to="`/models/${model.id}`">
          <div class="card-head"><span class="model-icon student"><el-icon><Box /></el-icon></span><span class="status-tag">{{ modelStatusLabel(model.status) }}</span></div>
          <div class="name">{{ model.name }}</div>
          <div v-if="model.fail_stage" class="fail">{{ model.fail_stage }} / {{ model.fail_message }}</div>
          <div class="card-foot"><span>我的模型版本</span><span>查看模型卡<el-icon><ArrowRight /></el-icon></span></div>
        </router-link>
      </div>
    </section>

    <section class="block">
      <div class="block-head"><div><h2>课题组共享 <span>{{ shared.length }}</span></h2><p>课题组内可访问的学生模型版本</p></div></div>
      <div v-if="!shared.length" class="empty-state"><span class="empty-icon"><el-icon><Collection /></el-icon></span><div><h3>暂无共享模型</h3><p>还没有共享到课题组的学生模型。</p></div></div>
      <div v-else class="cards">
        <router-link v-for="model in shared" :key="model.id" class="card" :to="`/models/${model.id}`">
          <div class="card-head"><span class="model-icon shared"><el-icon><Collection /></el-icon></span><span class="status-tag">{{ modelStatusLabel(model.status) }}</span></div>
          <div class="name">{{ model.name }}</div>
          <div class="card-foot"><span>课题组共享</span><span>查看模型卡<el-icon><ArrowRight /></el-icon></span></div>
        </router-link>
      </div>
    </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { ArrowRight, Box, Collection, UploadFilled, WarningFilled } from "@element-plus/icons-vue";
import { formatError, http } from "../../api/http";
import { formatFps, formatParamCount, modelStatusLabel } from "../../api/labels";

type Card = {
  id: string;
  name: string;
  slug: string;
  source?: string;
  status: string;
  requires_cuda: boolean;
  fail_stage: string | null;
  fail_message: string | null;
  param_count?: number | null;
  fps_per_image?: number | null;
};

const builtins = ref<Card[]>([]);
const mine = ref<Card[]>([]);
const shared = ref<Card[]>([]);
const loading = ref(true);
const loaded = ref(false);
const error = ref("");

async function loadList() {
  loading.value = true;
  error.value = "";
  try {
    const { data } = await http.get("/models");
    const items = (data.items ?? []) as Card[];
    builtins.value = data.builtins ?? items.filter((row) => row.source === "builtin");
    mine.value = data.mine ?? [];
    shared.value = data.shared ?? [];
    loaded.value = true;
  } catch (err) {
    error.value = formatError(err);
  } finally {
    loading.value = false;
  }
}

onMounted(loadList);
</script>

<style scoped>
.models-page { min-width: 0; }
.eyebrow { color: var(--lab-accent-2); letter-spacing: .14em; font-size: 14px; margin: 0 0 9px; }
.head h1 { margin: 0 0 10px; }
.head > p:last-child { color: var(--lab-muted); font-size: 16px; line-height: 1.8; margin: 0; max-width: 850px; }
.toolbar { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 18px; margin: 23px 0 30px; padding-bottom: 22px; border-bottom: 1px solid var(--lab-line); }
.import-link { display: inline-flex; align-items: center; gap: 8px; border-radius: 8px; padding: 11px 17px; background: #2c6eea; color: #fff; font-size: 16px; font-weight: 500; text-decoration: none; box-shadow: 0 3px 8px #286bea15; }
.import-link:hover { background: #1d5ed7; }
.related-links { display: flex; flex-wrap: wrap; gap: 22px; }
.related-links a { display: inline-flex; align-items: center; gap: 7px; color: #54769d; text-decoration: none; font-size: 16px; }
.related-links a:hover { color: #286bea; }
.block { margin-bottom: 30px; }
.block-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.block-head h2 { display: flex; align-items: center; gap: 10px; margin: 0; font-size: 20px; color: #263f5d; }
.block-head h2 span { display: inline-flex; align-items: center; justify-content: center; min-width: 23px; height: 22px; padding: 0 6px; border-radius: 6px; color: #7b8fa9; background: #eaf0f8; font-size: 14px; font-weight: 500; }
.block-head p { margin: 7px 0 0; color: #5c7089; font-size: 15px; line-height: 1.6; }
.cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(280px, 100%), 1fr)); gap: 17px; }
.card { display: flex; flex-direction: column; min-width: 0; text-decoration: none; background: #fff; border: 1px solid #e0e8f3; border-radius: 12px; padding: 21px; transition: border-color 180ms ease, box-shadow 180ms ease; }
.card:hover, .card:focus-visible { border-color: #93b5e4; box-shadow: 0 5px 18px #2348760b; }
.card-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 17px; }
.model-icon { display: inline-flex; align-items: center; justify-content: center; width: 39px; height: 39px; border-radius: 10px; color: #4f82cc; background: #edf4ff; font-size: 24px; }
.model-icon.student { color: #7d77b9; background: #f0effb; }
.model-icon.shared { color: #45968b; background: #ecf7f3; }
.status-tag { padding: 5px 8px; color: #667e9c; background: #f1f5fa; border-radius: 5px; font-size: 14px; line-height: 1.4; }
.name { color: #294362; font-size: 18px; font-weight: 600; line-height: 1.5; overflow-wrap: anywhere; }
.meta { color: #5c7089; font-size: 14px; margin-top: 6px; line-height: 1.6; overflow-wrap: anywhere; }
.model-specs { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; padding: 14px 12px; margin: 16px 0 18px; background: #f6f9fd; border-radius: 8px; }
.model-specs div { display: flex; flex-direction: column; gap: 6px; }
.model-specs span { color: #5c7089; font-size: 14px; }
.model-specs strong { color: #4b6482; font-size: 16px; font-weight: 500; overflow-wrap: anywhere; }
.card-foot { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-top: auto; padding-top: 14px; border-top: 1px solid #edf1f7; color: #5c7089; font-size: 14px; }
.card-foot > span:last-child { display: inline-flex; align-items: center; gap: 6px; color: #6689b6; }
.card > .name + .card-foot { margin-top: 20px; }
.fail { margin: 12px 0 18px; padding: 10px 12px; border-radius: 6px; background: #fff5f1; color: #a66d52; font-size: 15px; line-height: 1.65; overflow-wrap: anywhere; }
.empty-state { display: flex; align-items: center; gap: 18px; padding: 25px; background: #fff; border: 1px dashed #d8e3f1; border-radius: 12px; }
.empty-icon { display: inline-flex; align-items: center; justify-content: center; flex-shrink: 0; width: 48px; height: 48px; border-radius: 12px; color: #99b0ce; background: #f1f6fc; font-size: 27px; }
.empty-state h3 { color: #506a89; font-size: 17px; font-weight: 500; margin: 0 0 7px; }
.empty-state p { color: #5c7089; font-size: 16px; line-height: 1.7; margin: 0; }
.empty-state > a { display: inline-flex; align-items: center; gap: 7px; margin-left: auto; flex-shrink: 0; color: #477dc7; font-size: 16px; text-decoration: none; }
a:focus-visible { outline: 2px solid #3979ef; outline-offset: 4px; }
@media (max-width: 650px) { .toolbar { align-items: flex-start; flex-direction: column; gap: 17px; } .related-links { gap: 14px 20px; } .empty-state { align-items: flex-start; flex-wrap: wrap; gap: 13px; padding: 20px; } .empty-state > div { flex: 1; min-width: 170px; } .empty-state > a { margin-left: 61px; } .card { padding: 18px; } }
@media (prefers-reduced-motion: reduce) { .card { transition: none; } }

.load-state { display: flex; align-items: center; gap: 14px; padding: 24px; margin: 20px 0 28px; border: 1px solid #dce5f1; border-radius: 12px; background: #fff; color: #4f627b; }
.load-state > .el-icon { flex: none; font-size: 24px; color: #3f72bd; }
.load-state > div { flex: 1; min-width: 0; }
.load-state strong { color: #263f5d; font-size: 16px; font-weight: 600; }
.load-state p { margin: 6px 0 0; line-height: 1.7; font-size: 14px; overflow-wrap: anywhere; }
.load-state.error-state { background: #fffaf7; border-color: #ead9cf; }
.load-state.error-state > .el-icon { color: #9b6243; }
.load-state .el-button { flex: none; }
@media (max-width: 560px) { .load-state { flex-wrap: wrap; padding: 19px; }.load-state .el-button { margin-left: 38px; } }
</style>

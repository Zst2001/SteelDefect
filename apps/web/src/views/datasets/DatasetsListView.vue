<template>
  <div class="datasets-page">
    <header class="head">
      <p class="eyebrow">实验台</p>
      <h1>数据集</h1>
      <p>浏览预置数据与自己的对比批次，核对样本数量、配对掩码与适用范围。</p>
    </header>

    <div class="protocol-note"><el-icon><InfoFilled /></el-icon><p>预置集只读。正式评测只用 <strong>NEU-20</strong>（不是论文完整 test split）。全量 NEU 从磁盘登记后可浏览，不能评测。快速对比仍最多 50 张。</p></div>
    <div v-if="error" class="load-state error-state" role="alert"><el-icon><WarningFilled /></el-icon><div><strong>数据集目录暂不可用</strong><p>{{ error }}</p></div><el-button :loading="loading" @click="loadList">重新加载</el-button></div>
    <div v-else-if="loading && !loaded" class="load-state" role="status"><el-icon><Files /></el-icon><div><strong>正在读取数据集目录</strong><p>正在获取可访问的数据版本和样本数量。</p></div></div>
    <template v-if="loaded">

    <section class="block">
      <div class="block-head"><h2>预置数据集 <span>{{ presets.length }}</span></h2><p>固定数据版本，按各数据集开放范围使用</p></div>
      <div v-if="!presets.length" class="empty-state"><span class="empty-icon"><el-icon><FolderOpened /></el-icon></span><div><h3>暂无预置数据集</h3><p>确认实验台已启动并完成种子导入。</p></div></div>
      <div v-else class="cards">
        <router-link v-for="item in presets" :key="item.id" class="card" :to="`/datasets/${item.id}`">
          <div class="card-head"><span class="dataset-icon"><el-icon><Files /></el-icon></span><span class="access-tag">预置 · 只读</span></div>
          <div class="name">{{ item.name }}</div>
          <div class="count"><strong>{{ item.sample_count }}</strong><span>张样本</span></div>
          <div class="tags"><span v-if="item.eval_ready" class="eval-tag">可正式评测</span><span v-else-if="item.visibility === 'preset'">只读浏览</span><span v-if="item.has_gt">已配对掩码</span><span v-if="item.fixed">固定测试集</span></div>
          <p v-if="item.ingest_hint" class="hint">{{ item.ingest_hint }}</p>
          <div class="card-foot"><span>查看数据版本与样本</span><el-icon><ArrowRight /></el-icon></div>
        </router-link>
      </div>
    </section>

    <section class="block">
      <div class="block-head"><h2>我的对比批次 <span>{{ mine.length }}</span></h2><p>快速对比中上传的私有样本批次</p></div>
      <div v-if="!mine.length" class="empty-state"><span class="empty-icon"><el-icon><FolderOpened /></el-icon></span><div><h3>还没有对比批次</h3><p>快速对比上传会出现在这里。完整 NEU 请放到磁盘目录登记，不要在网页一次选几千张。</p></div></div>
      <div v-else class="cards">
        <router-link v-for="item in mine" :key="item.id" class="card" :to="`/datasets/${item.id}`">
          <div class="card-head"><span class="dataset-icon private"><el-icon><FolderOpened /></el-icon></span><span class="access-tag">私有</span></div>
          <div class="name">{{ item.name }}</div>
          <div class="count"><strong>{{ item.sample_count }}</strong><span>张样本</span></div>
          <div class="tags"><span v-if="item.has_gt">已配对掩码</span></div>
          <div class="card-foot"><span>查看数据版本与样本</span><el-icon><ArrowRight /></el-icon></div>
        </router-link>
      </div>
    </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ArrowRight, Files, FolderOpened, InfoFilled, WarningFilled } from "@element-plus/icons-vue";
import { formatError, http } from "../../api/http";

type Version = {
  id: string;
  sample_count: number;
  has_gt: boolean;
  eval_ready: boolean;
  is_fixed_test: boolean;
  browse_only?: boolean;
};

type DatasetCard = {
  id: string;
  name: string;
  visibility: string;
  eval_ready: boolean;
  sample_count: number;
  ingest_hint?: string | null;
  versions?: Version[];
  has_gt: boolean;
  fixed: boolean;
};

const items = ref<DatasetCard[]>([]);
const error = ref("");
const loading = ref(true);
const loaded = ref(false);

const presets = computed(() => items.value.filter((row) => row.visibility === "preset"));
const mine = computed(() => items.value.filter((row) => row.visibility !== "preset"));

async function loadList() {
  loading.value = true;
  error.value = "";
  try {
    const { data } = await http.get("/datasets");
    items.value = (data.items ?? []).map((row: DatasetCard) => {
      const versions = row.versions ?? [];
      return {
        ...row,
        has_gt: versions.some((version) => version.has_gt),
        fixed: versions.some((version) => version.is_fixed_test),
      };
    });
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
.datasets-page { min-width: 0; }
.eyebrow { color: var(--lab-accent-2); letter-spacing: .14em; font-size: 14px; margin: 0 0 9px; }
.head h1 { margin: 0 0 10px; }
.head > p:last-child { color: var(--lab-muted); font-size: 16px; line-height: 1.8; margin: 0; }
.protocol-note { display: flex; align-items: flex-start; gap: 11px; margin: 23px 0 28px; padding: 15px 18px; border: 1px solid #dce8f7; border-radius: 9px; background: #f0f6ff; color: #617e9f; }
.protocol-note > .el-icon { flex-shrink: 0; margin-top: 3px; color: #5689cf; font-size: 19px; }
.protocol-note p { font-size: 16px; line-height: 1.8; margin: 0; }
.protocol-note strong { font-weight: 600; color: #3b669c; }
.err { padding: 12px 15px; border-radius: 8px; color: var(--lab-danger); background: #fff3f1; font-size: 16px; line-height: 1.7; }
.block { margin-bottom: 30px; }
.block-head { margin-bottom: 16px; }
.block-head h2 { display: flex; align-items: center; gap: 10px; color: #263f5d; font-size: 20px; margin: 0; }
.block-head h2 span { display: inline-flex; align-items: center; justify-content: center; min-width: 23px; height: 22px; padding: 0 6px; border-radius: 6px; color: #7b8fa9; background: #eaf0f8; font-size: 14px; font-weight: 500; }
.block-head p { margin: 7px 0 0; color: #5c7089; font-size: 15px; line-height: 1.6; }
.cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(280px, 100%), 1fr)); gap: 17px; }
.card { display: flex; flex-direction: column; min-width: 0; text-decoration: none; background: #fff; border: 1px solid #e0e8f3; border-radius: 12px; padding: 22px; transition: border-color 180ms ease, box-shadow 180ms ease; }
.card:hover, .card:focus-visible { border-color: #93b5e4; box-shadow: 0 5px 18px #2348760b; }
.card-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 17px; }
.dataset-icon { display: inline-flex; align-items: center; justify-content: center; width: 41px; height: 41px; border-radius: 10px; color: #4e82cf; background: #edf4ff; font-size: 25px; }
.dataset-icon.private { color: #469b8b; background: #ebf7f2; }
.access-tag { color: #5c7089; font-size: 14px; }
.name { color: #294362; font-size: 18px; font-weight: 600; line-height: 1.6; overflow-wrap: anywhere; }
.count { display: flex; align-items: baseline; gap: 8px; margin: 13px 0 18px; font-variant-numeric: tabular-nums; }
.count strong { color: #2d486a; font-size: 29px; font-weight: 550; letter-spacing: -.03em; }
.count span { color: #5c7089; font-size: 14px; }
.tags { display: flex; flex-wrap: wrap; gap: 7px; margin-bottom: 17px; }
.tags span { padding: 5px 8px; border-radius: 5px; background: #f2f6fb; color: #5c7089; font-size: 14px; line-height: 1.4; }
.tags .eval-tag { color: #448c79; background: #eaf7f1; }
.hint { margin: 0 0 18px; padding: 10px 12px; background: #f7f9fc; border-left: 2px solid #d4e0f0; border-radius: 4px; color: #5c7089; font-size: 14px; line-height: 1.8; overflow-wrap: anywhere; }
.card-foot { display: flex; align-items: center; justify-content: space-between; gap: 14px; margin-top: auto; padding-top: 14px; border-top: 1px solid #edf1f7; color: #6d8bb2; font-size: 15px; }
.empty-state { display: flex; align-items: center; gap: 18px; padding: 25px; background: #fff; border: 1px dashed #d8e3f1; border-radius: 12px; }
.empty-icon { display: inline-flex; align-items: center; justify-content: center; flex-shrink: 0; width: 48px; height: 48px; border-radius: 12px; color: #99b0ce; background: #f1f6fc; font-size: 27px; }
.empty-state h3 { margin: 0 0 7px; color: #506a89; font-size: 17px; font-weight: 500; }
.empty-state p { margin: 0; color: #5c7089; font-size: 16px; line-height: 1.8; }
a:focus-visible { outline: 2px solid #3979ef; outline-offset: 4px; }
@media (max-width: 650px) { .card { padding: 19px; } .empty-state { align-items: flex-start; gap: 13px; padding: 20px; } .protocol-note { padding: 13px 14px; } }
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

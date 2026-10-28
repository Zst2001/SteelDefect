<template>
  <div class="dataset-detail">
    <header class="head">
      <p class="eyebrow">数据集</p>
      <h1>{{ detail?.name ?? "数据详情" }}</h1>
      <p v-if="detail?.disclaimer">{{ detail.disclaimer }}</p>
    </header>

    <section v-if="error" class="load-state error-state" role="alert">
      <div><strong>数据集详情暂不可用</strong><p>{{ error }}</p></div>
      <el-button :loading="loading" @click="loadDetail">重新加载</el-button>
      <router-link to="/datasets">返回列表</router-link>
    </section>
    <section v-else-if="loading" class="load-state" role="status">
      <strong>正在读取数据集详情…</strong>
    </section>

    <template v-else-if="detail">
      <section class="overview-card" aria-label="数据集概览">
      <div class="section-head">
        <h2>数据概览</h2>
        <div class="toolbar">
          <router-link v-if="activeVersion?.eval_ready" to="/eval/new">去正式评测</router-link>
          <router-link to="/datasets">返回列表</router-link>
        </div>
      </div>
      <dl class="facts">
        <div><dt>当前版本样本</dt><dd>{{ sampleCount }} <small>张</small></dd></div>
        <div><dt>预处理</dt><dd>{{ detail.preprocess || "未提供" }}</dd></div>
        <div><dt>使用范围</dt><dd>{{ !activeVersion ? "暂无版本" : activeVersion.eval_ready ? "可正式评测" : activeVersion.browse_only ? "只读浏览" : "对照批次" }}</dd></div>
        <div><dt>配对掩码</dt><dd>{{ !activeVersion ? "—" : activeVersion.has_gt ? "已配对" : "未完整配对" }}</dd></div>
      </dl>
      <p v-if="activeVersion?.is_fixed_test" class="protocol-note">固定测试集 · 学生不可下载 GT</p>
      <p v-if="detail.ingest_hint" class="hint">{{ detail.ingest_hint }}</p>

      <div v-if="detail.legend?.length" class="legend" aria-label="分割类别">
        <span class="legend-label">分割类别</span>
        <span v-for="item in detail.legend || []" :key="item.id" class="chip">
          <i :style="{ background: item.color }"></i>{{ item.name }}
        </span>
      </div>
      </section>

      <section class="samples-card" :aria-busy="pageLoading">
      <div class="section-head"><h2>样例预览</h2><span class="meta">每页最多 24 张 · 原图浏览</span></div>
      <div v-if="(detail.versions || []).length > 1" class="versions">
        <el-radio-group v-model="versionId" aria-label="数据版本" @change="loadPage(0)">
          <el-radio v-for="version in detail.versions" :key="version.id" :label="version.id">
            {{ versionLabel(version) }}
          </el-radio>
        </el-radio-group>
      </div>

      <div v-if="pageError" class="load-state error-state" role="alert">
        <div><strong>样例暂不可用</strong><p>{{ pageError }}</p></div>
        <el-button @click="loadPage(requestedOffset)">重试当前页</el-button>
      </div>
      <p v-else-if="pageLoading" class="empty" role="status">正在读取当前版本的样例…</p>
      <p v-else-if="!versionId" class="empty">暂无可浏览的数据版本。</p>
      <p v-else-if="!page.items.length" class="empty">这一页没有样例。</p>
      <div v-else class="strip" aria-label="样例预览">
        <figure v-for="sample in page.items" :key="sample.sample_key" class="coupon">
          <img :src="sample.preview_url" :alt="sample.sample_key" loading="lazy" />
          <figcaption>
            <div><strong>{{ sample.sample_key }}</strong><span>{{ sample.width }} × {{ sample.height }} px</span></div>
            <em v-if="sample.has_mask" title="有配对掩码，不代表可下载">GT</em>
          </figcaption>
        </figure>
      </div>

      <div v-if="versionId" class="pager">
        <el-button :disabled="pageLoading || !!pageError || page.offset <= 0" @click="loadPage(page.offset - page.limit)">上一页</el-button>
        <span v-if="pageLoading">读取中…</span>
        <span v-else-if="pageError">加载未完成</span>
        <span v-else>
          {{ page.total ? page.offset + 1 : 0 }}–{{ Math.min(page.offset + page.items.length, page.total) }}
          / {{ page.total }}
        </span>
        <el-button :disabled="pageLoading || !!pageError || page.offset + page.limit >= page.total" @click="loadPage(page.offset + page.limit)">
          下一页
        </el-button>
      </div>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { formatError, http } from "../../api/http";

type Version = {
  id: string;
  kind: string;
  sample_count: number;
  has_gt: boolean;
  eval_ready: boolean;
  is_fixed_test: boolean;
  browse_only?: boolean;
};

type Sample = {
  sample_key: string;
  width: number;
  height: number;
  has_mask: boolean;
  preview_url: string;
};

type Detail = {
  id: string;
  name: string;
  disclaimer?: string;
  ingest_hint?: string | null;
  preprocess?: string | null;
  legend?: Array<{ id: number; name: string; color: string }>;
  versions?: Version[];
};

const route = useRoute();
const detail = ref<Detail | null>(null);
const versionId = ref("");
const error = ref("");
const loading = ref(true);
const pageLoading = ref(false);
const pageError = ref("");
const requestedOffset = ref(0);
const page = ref({ items: [] as Sample[], total: 0, offset: 0, limit: 24 });
let detailRequest = 0;
let pageRequest = 0;

const activeVersion = computed(() => (detail.value?.versions ?? []).find((row) => row.id === versionId.value));
const sampleCount = computed(() => activeVersion.value?.sample_count ?? 0);

function versionLabel(version: Version): string {
  if (version.eval_ready) return `固定测试集 · ${version.sample_count} 张`;
  if (version.browse_only) return `浏览 · ${version.sample_count} 张`;
  return `${version.kind} · ${version.sample_count} 张`;
}

async function loadPage(offset: number) {
  if (!detail.value || !versionId.value) return;
  const request = ++pageRequest;
  const datasetId = detail.value.id;
  const selectedVersion = versionId.value;
  requestedOffset.value = Math.max(0, offset);
  pageLoading.value = true;
  pageError.value = "";
  page.value = { items: [], total: 0, offset: requestedOffset.value, limit: 24 };
  try {
    const { data } = await http.get(`/datasets/${datasetId}/versions/${selectedVersion}/samples`, {
      params: { offset: requestedOffset.value, limit: 24 },
    });
    if (request === pageRequest) page.value = data;
  } catch (err) {
    if (request === pageRequest) pageError.value = formatError(err);
  } finally {
    if (request === pageRequest) pageLoading.value = false;
  }
}

async function loadDetail() {
  const request = ++detailRequest;
  ++pageRequest;
  const datasetId = String(route.params.id ?? "");
  loading.value = true;
  error.value = "";
  detail.value = null;
  versionId.value = "";
  pageError.value = "";
  pageLoading.value = false;
  requestedOffset.value = 0;
  page.value = { items: [], total: 0, offset: 0, limit: 24 };
  try {
    const { data } = await http.get(`/datasets/${datasetId}`);
    if (request !== detailRequest) return;
    detail.value = data;
    const versions = (data.versions ?? []) as Version[];
    const preferred = versions.find((row) => row.eval_ready) ?? versions[0];
    versionId.value = preferred?.id ?? "";
    if (versionId.value) void loadPage(0);
  } catch (err) {
    if (request === detailRequest) error.value = formatError(err);
  } finally {
    if (request === detailRequest) loading.value = false;
  }
}

watch(() => route.params.id, loadDetail, { immediate: true });
onBeforeUnmount(() => {
  ++detailRequest;
  ++pageRequest;
});
</script>

<style scoped>
.dataset-detail { min-width: 0; }
.eyebrow {
  color: var(--lab-fiducial);
  letter-spacing: 0.14em;
  font-size: 14px;
}
.head p,
.meta,
.hint,
.empty,
.pager,
figcaption {
  color: var(--lab-muted);
}
.head h1 { overflow-wrap: anywhere; }
.head p { max-width: 1050px; }
.overview-card,
.samples-card {
  padding: 24px;
  margin-bottom: 22px;
  border: 1px solid #dfe7f2;
  border-radius: 12px;
  background: var(--lab-panel);
  box-shadow: 0 2px 8px #233f6605;
  min-width: 0;
}
.section-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 20px;
}
.section-head h2 { margin: 0; font-size: 20px; }
.section-head .meta { font-size: 14px; }
.facts { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; margin: 0; }
.facts > div { padding: 16px 18px; background: #f5f8fc; border: 1px solid #e7edf5; border-radius: 8px; min-width: 0; }
.facts dt { color: var(--lab-muted); font-size: 14px; }
.facts dd { margin: 9px 0 0; color: var(--lab-text); font-size: 18px; font-weight: 600; overflow-wrap: anywhere; line-height: 1.5; }
.facts small { font-size: 14px; font-weight: 400; color: var(--lab-muted); }
.hint, .protocol-note { margin: 16px 0 0; padding: 11px 14px; border-radius: 7px; line-height: 1.7; font-size: 14px; background: #f3f7fd; }
.protocol-note { color: #285a98; border-left: 3px solid #8cadd8; }
.hint { overflow-wrap: anywhere; }
.load-state {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 16px;
  padding: 24px;
  border: 1px solid #dfe7f2;
  border-radius: 10px;
  background: var(--lab-panel);
  color: var(--lab-muted);
  line-height: 1.7;
}
.load-state > div { flex: 1; min-width: 170px; }
.load-state strong { color: var(--lab-text); font-size: 16px; }
.load-state p { margin: 6px 0 0; overflow-wrap: anywhere; font-size: 14px; }
.error-state { border-color: #ead9cf; background: #fffaf7; }
.load-state a, .toolbar a { color: var(--lab-accent-2); font-size: 15px; text-decoration: none; }
.load-state a:hover, .toolbar a:hover { text-decoration: underline; }
.legend {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin: 18px 0 0;
}
.legend-label { color: var(--lab-muted); font-size: 14px; }
.chip {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-size: 14px;
}
.chip i {
  width: 10px;
  height: 10px;
  display: inline-block;
  border-radius: 3px;
}
.toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
}
.empty { padding: 36px 16px; margin: 0; text-align: center; background: #f7f9fc; border: 1px dashed #dce5f1; border-radius: 9px; line-height: 1.7; font-size: 15px; }
.strip {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(154px, 1fr));
  gap: 14px;
}
.coupon {
  margin: 0;
  padding: 7px;
  min-width: 0;
  background: var(--lab-panel);
  border: 1px solid #dce5f1;
  border-radius: 9px;
}
.coupon img {
  display: block;
  width: 100%;
  aspect-ratio: 1;
  object-fit: contain;
  image-rendering: pixelated;
  background: var(--lab-well);
  border-radius: 5px;
}
figcaption {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
  padding: 10px 5px 5px;
  font-size: 13px;
  line-height: 1.5;
}
figcaption > div { min-width: 0; }
figcaption strong { display: block; color: var(--lab-text); font-size: 14px; font-weight: 600; overflow-wrap: anywhere; }
figcaption span { display: block; margin-top: 4px; }
figcaption em {
  font-style: normal;
  color: #256d59;
  background: #eaf7f1;
  border-radius: 4px;
  padding: 2px 5px;
  font-size: 12px;
}
.pager {
  display: flex;
  justify-content: center;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 22px;
  padding-top: 20px;
  border-top: 1px solid var(--lab-line);
  font-size: 14px;
  font-variant-numeric: tabular-nums;
}
.pager .el-button { margin-left: 0; }
.versions { margin-bottom: 20px; padding: 12px 16px; border-radius: 8px; background: #f5f8fc; }
.versions :deep(.el-radio-group) { display: flex; flex-wrap: wrap; gap: 10px 20px; }
.versions :deep(.el-radio) { margin: 0; height: auto; min-height: 28px; }
@media (max-width: 1050px) { .facts { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 560px) {
  .overview-card, .samples-card { padding: 17px; }
  .facts { gap: 10px; }
  .facts > div { padding: 12px; }
  .facts dd { font-size: 16px; }
  .strip { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
  .load-state { padding: 18px; }
  .coupon { padding: 5px; }
  figcaption { flex-wrap: wrap; gap: 5px; padding: 8px 3px 3px; }
  figcaption span { font-size: 12px; }
  .pager { gap: 9px; }
}
</style>

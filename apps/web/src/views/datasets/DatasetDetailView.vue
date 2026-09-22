<template>
  <div>
    <header class="head">
      <p class="eyebrow">数据集</p>
      <h1>{{ detail?.name ?? "数据详情" }}</h1>
      <p v-if="detail?.disclaimer">{{ detail.disclaimer }}</p>
    </header>

    <p v-if="error" class="err">{{ error }}</p>
    <p v-else-if="!detail" class="meta">正在读取…</p>

    <template v-else>
      <div class="meta-row">
        <span>{{ sampleCount }} 张</span>
        <span>{{ detail.preprocess || "neu_200" }}</span>
        <span v-if="activeVersion?.eval_ready">可正式评测</span>
        <span v-else-if="activeVersion?.browse_only">只读浏览</span>
        <span v-if="activeVersion?.has_gt">已配对掩码</span>
        <span v-if="activeVersion?.is_fixed_test">学生不可下载 GT</span>
      </div>
      <p v-if="detail.ingest_hint" class="hint">{{ detail.ingest_hint }}</p>

      <div class="legend">
        <span v-for="item in detail.legend || []" :key="item.id" class="chip">
          <i :style="{ background: item.color }"></i>{{ item.name }}
        </span>
      </div>

      <div v-if="(detail.versions || []).length > 1" class="versions">
        <el-radio-group v-model="versionId" @change="loadPage(0)">
          <el-radio v-for="version in detail.versions" :key="version.id" :label="version.id">
            {{ versionLabel(version) }}
          </el-radio>
        </el-radio-group>
      </div>

      <div class="toolbar">
        <router-link v-if="activeVersion?.eval_ready" to="/eval/new">去正式评测</router-link>
        <router-link to="/datasets">返回列表</router-link>
      </div>

      <p v-if="!page.items.length" class="empty">这一页没有样例。</p>
      <div v-else class="strip" aria-label="样例预览">
        <figure v-for="sample in page.items" :key="sample.sample_key" class="coupon">
          <img :src="sample.preview_url" :alt="sample.sample_key" />
          <figcaption>
            <span>{{ sample.sample_key }}</span>
            <em v-if="sample.has_mask">GT</em>
          </figcaption>
        </figure>
      </div>

      <div class="pager">
        <el-button :disabled="page.offset <= 0" @click="loadPage(page.offset - page.limit)">上一页</el-button>
        <span>
          {{ page.total ? page.offset + 1 : 0 }}–{{ Math.min(page.offset + page.items.length, page.total) }}
          / {{ page.total }}
        </span>
        <el-button :disabled="page.offset + page.limit >= page.total" @click="loadPage(page.offset + page.limit)">
          下一页
        </el-button>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
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
const page = ref({ items: [] as Sample[], total: 0, offset: 0, limit: 24 });

const activeVersion = computed(() => (detail.value?.versions ?? []).find((row) => row.id === versionId.value));
const sampleCount = computed(() => activeVersion.value?.sample_count ?? 0);

function versionLabel(version: Version): string {
  if (version.eval_ready) return `固定测试集 · ${version.sample_count} 张`;
  if (version.browse_only) return `浏览 · ${version.sample_count} 张`;
  return `${version.kind} · ${version.sample_count} 张`;
}

async function loadPage(offset: number) {
  if (!detail.value || !versionId.value) return;
  const { data } = await http.get(`/datasets/${detail.value.id}/versions/${versionId.value}/samples`, {
    params: { offset, limit: 24 },
  });
  page.value = data;
}

onMounted(async () => {
  try {
    const { data } = await http.get(`/datasets/${route.params.id}`);
    detail.value = data;
    const versions = (data.versions ?? []) as Version[];
    const preferred = versions.find((row) => row.eval_ready) ?? versions[0];
    versionId.value = preferred?.id ?? "";
    if (versionId.value) await loadPage(0);
  } catch (err) {
    error.value = formatError(err);
  }
});
</script>

<style scoped>
.eyebrow {
  color: var(--lab-accent-2);
  letter-spacing: 0.16em;
  font-size: 12px;
}
.head p,
.meta,
.hint,
.empty,
.pager,
.meta-row,
figcaption {
  color: var(--lab-muted);
}
.err {
  color: var(--lab-danger);
}
.meta-row {
  display: flex;
  flex-wrap: wrap;
  gap: 12px 18px;
  margin: 8px 0 16px;
  font-size: 13px;
}
.hint {
  max-width: 720px;
  line-height: 1.6;
}
.legend {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  margin: 12px 0 20px;
}
.chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
}
.chip i {
  width: 10px;
  height: 10px;
  display: inline-block;
}
.toolbar {
  display: flex;
  gap: 16px;
  margin: 12px 0 20px;
}
.strip {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(148px, 1fr));
  gap: 10px;
}
.coupon {
  margin: 0;
  background: #0f1318;
  border: 1px solid var(--lab-line);
}
.coupon img {
  display: block;
  width: 100%;
  aspect-ratio: 1;
  object-fit: cover;
  image-rendering: pixelated;
}
figcaption {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  padding: 6px 8px 8px;
  font-size: 11px;
}
figcaption em {
  font-style: normal;
  color: var(--lab-accent-2);
  letter-spacing: 0.08em;
}
.pager {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 18px;
  font-variant-numeric: tabular-nums;
}
.versions {
  margin-bottom: 12px;
}
</style>

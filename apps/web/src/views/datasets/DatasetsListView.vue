<template>
  <div>
    <header class="head">
      <p class="eyebrow">实验台</p>
      <h1>数据集</h1>
      <p>
        预置集只读。正式评测只用 <strong>NEU-20</strong>（不是论文完整 test split）。全量 NEU 从磁盘登记后可浏览，不能评测。快速对比仍最多 50 张。
      </p>
    </header>

    <p v-if="error" class="err">{{ error }}</p>

    <section class="block">
      <h2>预置</h2>
      <p v-if="!presets.length" class="empty">还没有预置数据集。确认实验台已启动并完成种子导入。</p>
      <div v-else class="cards">
        <router-link v-for="item in presets" :key="item.id" class="card" :to="`/datasets/${item.id}`">
          <div class="name">{{ item.name }}</div>
          <div class="count">{{ item.sample_count }} 张</div>
          <div class="tags">
            <span v-if="item.eval_ready">可正式评测</span>
            <span v-else-if="item.visibility === 'preset'">只读浏览</span>
            <span v-if="item.has_gt">已配对掩码</span>
            <span v-if="item.fixed">固定测试集</span>
          </div>
          <p v-if="item.ingest_hint" class="hint">{{ item.ingest_hint }}</p>
        </router-link>
      </div>
    </section>

    <section class="block">
      <h2>我的对比批次</h2>
      <p v-if="!mine.length" class="empty">快速对比上传会出现在这里。完整 NEU 请放到磁盘目录登记，不要在网页一次选几千张。</p>
      <div v-else class="cards">
        <router-link v-for="item in mine" :key="item.id" class="card" :to="`/datasets/${item.id}`">
          <div class="name">{{ item.name }}</div>
          <div class="count">{{ item.sample_count }} 张</div>
          <div class="tags">
            <span>私有</span>
            <span v-if="item.has_gt">已配对掩码</span>
          </div>
        </router-link>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
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

const presets = computed(() => items.value.filter((row) => row.visibility === "preset"));
const mine = computed(() => items.value.filter((row) => row.visibility !== "preset"));

onMounted(async () => {
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
.empty,
.hint,
.tags,
.count {
  color: var(--lab-muted);
}
.err {
  color: var(--lab-danger);
}
.block {
  margin: 28px 0 36px;
}
.cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 14px;
}
.card {
  display: block;
  text-decoration: none;
  background: var(--lab-panel);
  border: 1px solid var(--lab-line);
  padding: 18px;
  min-height: 128px;
}
.card:hover {
  border-color: var(--lab-accent);
}
.name {
  font-weight: 600;
  letter-spacing: 0.04em;
}
.count {
  font-variant-numeric: tabular-nums;
  margin: 8px 0 12px;
  font-size: 20px;
  color: var(--lab-text);
}
.tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  font-size: 12px;
}
.hint {
  margin: 12px 0 0;
  font-size: 12px;
  line-height: 1.55;
}
</style>

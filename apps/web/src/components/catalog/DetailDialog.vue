<template>
  <el-dialog v-model="visible" :title="title" width="560px" destroy-on-close>
    <dl class="facts">
      <div v-for="row in rows" :key="row.label">
        <dt>{{ row.label }}</dt>
        <dd>
          <a v-if="row.href" :href="row.href" target="_blank" rel="noopener noreferrer">{{ row.value }}</a>
          <span v-else>{{ row.value }}</span>
        </dd>
      </div>
    </dl>
    <p v-if="detail" class="detail">{{ detail }}</p>
    <p v-if="!rows.length && !detail" class="empty">暂无更多可展示信息。</p>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed } from "vue";
import {
  FUND_ROLE_LABELS,
  FUND_SOURCE_LABELS,
  FUND_STATUS_LABELS,
  WORK_KIND_LABELS,
  taskLabel,
  type CatalogDataset,
  type CatalogFund,
  type CatalogModel,
  type CatalogWork,
} from "../../api/catalog";

const props = defineProps<{
  model?: CatalogModel | null;
  dataset?: CatalogDataset | null;
  work?: CatalogWork | null;
  fund?: CatalogFund | null;
}>();

const emit = defineEmits<{
  "update:model": [value: CatalogModel | null];
  "update:dataset": [value: CatalogDataset | null];
  "update:work": [value: CatalogWork | null];
  "update:fund": [value: CatalogFund | null];
}>();

const visible = computed({
  get: () => Boolean(props.model || props.dataset || props.work || props.fund),
  set: (value: boolean) => {
    if (!value) {
      emit("update:model", null);
      emit("update:dataset", null);
      emit("update:work", null);
      emit("update:fund", null);
    }
  },
});

const title = computed(
  () => props.work?.name || props.fund?.name || props.model?.name || props.dataset?.name || "详情",
);
const detail = computed(() => props.work?.summary || props.fund?.detail || props.model?.detail || props.dataset?.detail || "");

const rows = computed(() => {
  const out: Array<{ label: string; value: string; href?: string }> = [];
  if (props.work) {
    const item = props.work;
    out.push({ label: "类型", value: WORK_KIND_LABELS[item.kind] ?? item.kind });
    if (item.year) out.push({ label: "年份", value: String(item.year) });
    if (item.venue) out.push({ label: "载体", value: item.venue });
    if (item.authors) out.push({ label: "作者", value: item.authors });
    if (item.link_url) out.push({ label: "原文", value: item.link_url, href: item.link_url });
  }
  if (props.fund) {
    const item = props.fund;
    out.push({ label: "类别", value: FUND_SOURCE_LABELS[item.source] ?? item.source });
    out.push({ label: "状态", value: FUND_STATUS_LABELS[item.status] ?? item.status });
    out.push({ label: "角色", value: FUND_ROLE_LABELS[item.role] ?? item.role });
    if (item.number) out.push({ label: "批准号", value: item.number });
    if (item.start_year || item.end_year) {
      const start = item.start_year ? String(item.start_year) : "";
      const end = item.end_year ? String(item.end_year) : "";
      out.push({ label: "周期", value: [start, end].filter(Boolean).join("–") });
    }
    if (item.amount_text) out.push({ label: "经费", value: item.amount_text });
  }
  if (props.model) {
    const item = props.model;
    if (item.year) out.push({ label: "年份", value: String(item.year) });
    out.push({ label: "任务类型", value: taskLabel(item.task_type) });
    if (item.backbone) out.push({ label: "Backbone", value: item.backbone });
    if (item.keywords) out.push({ label: "核心方法", value: item.keywords });
    if (item.dataset) out.push({ label: "数据集", value: item.dataset });
    if (item.paper_url) out.push({ label: "论文", value: item.paper_url, href: item.paper_url });
    if (item.code_url) out.push({ label: "代码", value: item.code_url, href: item.code_url });
  }
  if (props.dataset) {
    const item = props.dataset;
    out.push({ label: "任务类型", value: taskLabel(item.task_type) });
    if (item.source_object) out.push({ label: "来源", value: item.source_object });
    if (item.class_count != null) out.push({ label: "缺陷类别数量", value: String(item.class_count) });
    if (item.image_count != null) out.push({ label: "图像数量", value: String(item.image_count) });
    if (item.numbers_text) out.push({ label: "规模说明", value: item.numbers_text });
    if (item.defect_types) out.push({ label: "缺陷类别", value: item.defect_types });
    if (item.size) out.push({ label: "尺寸", value: item.size });
    if (item.url) {
      const label = item.access_note ? `外部链接（${item.access_note}）` : "外部链接";
      out.push({ label, value: item.url, href: item.url });
    }
  }
  return out;
});
</script>

<style scoped>
.facts {
  margin: 0;
  display: grid;
  gap: 12px;
}
.facts div {
  display: grid;
  grid-template-columns: 110px 1fr;
  gap: 12px;
}
dt {
  color: var(--lab-muted);
  font-size: 13px;
}
dd {
  margin: 0;
  word-break: break-all;
  line-height: 1.5;
}
a {
  color: var(--lab-accent-2);
  text-decoration: none;
}
a:hover {
  text-decoration: underline;
}
.detail,
.empty {
  color: var(--lab-muted);
  line-height: 1.7;
  margin: 16px 0 0;
}
</style>

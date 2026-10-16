<template>
  <article class="card">
    <div class="top">
      <div class="source">{{ sourceLabel }}</div>
      <div class="status">{{ statusLabel }}</div>
    </div>
    <div class="name">{{ fund.name }}</div>
    <div v-if="period" class="meta">{{ period }}</div>
    <div class="row">角色：{{ roleLabel }}</div>
    <div v-if="fund.number" class="row">批准号：{{ fund.number }}</div>
    <div v-if="fund.amount_text" class="row">经费：{{ fund.amount_text }}</div>
    <p v-if="fund.detail" class="summary">{{ fund.detail }}</p>
    <div class="actions">
      <button class="ext ghost" type="button" @click="$emit('detail', fund)">详情</button>
      <template v-if="editable">
        <button class="ext ghost" type="button" @click="$emit('edit', fund)">编辑</button>
        <button class="ext danger" type="button" @click="$emit('remove', fund)">删除</button>
      </template>
    </div>
  </article>
</template>

<script setup lang="ts">
import { computed } from "vue";
import {
  FUND_ROLE_LABELS,
  FUND_SOURCE_LABELS,
  FUND_STATUS_LABELS,
  type CatalogFund,
} from "../../api/catalog";

const props = defineProps<{
  fund: CatalogFund;
  editable?: boolean;
}>();

defineEmits<{
  detail: [fund: CatalogFund];
  edit: [fund: CatalogFund];
  remove: [fund: CatalogFund];
}>();

const sourceLabel = computed(() => FUND_SOURCE_LABELS[props.fund.source] ?? "科研项目");
const statusLabel = computed(() => FUND_STATUS_LABELS[props.fund.status] ?? "");
const roleLabel = computed(() => FUND_ROLE_LABELS[props.fund.role] ?? "");
const period = computed(() => {
  if (props.fund.start_year && props.fund.end_year) {
    return `${props.fund.start_year}–${props.fund.end_year}`;
  }
  if (props.fund.start_year) {
    return `${props.fund.start_year} 起`;
  }
  if (props.fund.end_year) {
    return `至 ${props.fund.end_year}`;
  }
  return "";
});
</script>

<style scoped>
.card {
  background: var(--lab-panel);
  border: 1px solid var(--lab-line);
  padding: 22px 20px;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  transition: border-color 180ms ease;
}
.card:hover {
  border-color: var(--lab-fiducial);
}
.top {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
  font-size: 12px;
}
.source {
  color: var(--lab-accent-2);
  font-family: var(--lab-font-mono);
  letter-spacing: 0.08em;
}
.status {
  color: var(--lab-muted);
}
.name {
  font-weight: 600;
  margin-bottom: 6px;
  font-size: 16px;
  line-height: 1.4;
}
.meta,
.row,
.summary {
  color: var(--lab-muted);
  font-size: 13px;
  line-height: 1.55;
}
.row {
  margin-top: 6px;
}
.summary {
  margin: 10px 0 0;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: auto;
  padding-top: 14px;
}
.ext {
  color: var(--lab-accent-2);
  text-decoration: none;
  background: none;
  border: none;
  padding: 0;
  font-size: 13px;
}
.ext:hover {
  text-decoration: underline;
}
.ghost {
  color: var(--lab-text);
}
.danger {
  color: var(--lab-danger);
}
</style>

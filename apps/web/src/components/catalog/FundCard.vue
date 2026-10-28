<template>
  <article class="card">
    <div class="card-top"><span class="card-icon"><el-icon><Collection /></el-icon></span><span class="source">{{ sourceLabel }}</span><span class="status" :class="fund.status">{{ statusLabel }}</span></div>
    <h3 class="name">{{ fund.name }}</h3>
    <div v-if="period" class="meta"><el-icon><Calendar /></el-icon>{{ period }}</div>
    <dl class="fund-facts">
      <div><dt>承担角色</dt><dd>{{ roleLabel }}</dd></div>
      <div v-if="fund.number"><dt>批准号</dt><dd class="mono">{{ fund.number }}</dd></div>
      <div v-if="fund.amount_text"><dt>项目经费</dt><dd>{{ fund.amount_text }}</dd></div>
    </dl>
    <p v-if="fund.detail" class="summary">{{ fund.detail }}</p>
    <div class="actions">
      <button class="ext ghost" type="button" @click="$emit('detail', fund)">查看详情<el-icon><ArrowRight /></el-icon></button>
      <template v-if="editable">
        <button class="ext ghost" type="button" @click="$emit('edit', fund)">编辑</button>
        <button class="ext danger" type="button" @click="$emit('remove', fund)">删除</button>
      </template>
    </div>
  </article>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { ArrowRight, Calendar, Collection } from "@element-plus/icons-vue";
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
  --catalog-accent: #206847;
  --catalog-tint: #eaf5ed;
  display: flex;
  flex-direction: column;
  min-width: 0;
  padding: 22px;
  background: #fff;
  border: 1px solid #ccd8e7;
  border-top: 3px solid var(--catalog-accent);
  border-radius: 12px;
  box-sizing: border-box;
  box-shadow: 0 3px 12px #203b5d08;
  transition: border-color 160ms ease, box-shadow 160ms ease;
}
.card:hover {
  border-color: var(--catalog-accent);
  box-shadow: 0 7px 22px #203b5d12;
}
.card-top {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 18px;
  min-height: 40px;
}
.card-icon {
  display: grid;
  place-items: center;
  width: 40px;
  height: 40px;
  flex: none;
  border-radius: 10px;
  background: var(--catalog-accent);
  color: #fff;
  font-size: 22px;
}
.kind {
  padding: 4px 8px;
  border-radius: 5px;
  background: var(--catalog-tint);
  color: var(--catalog-accent);
  font-size: 14px;
  font-weight: 600;
  line-height: 1.5;
}
.name {
  margin: 0 0 10px;
  color: #172d49;
  font-size: 18px;
  font-weight: 650;
  line-height: 1.5;
  overflow-wrap: anywhere;
}
.meta {
  color: #53657e;
  font-size: 14px;
  line-height: 1.8;
  margin-bottom: 6px;
}
.row {
  display: flex;
  align-items: start;
  gap: 7px;
  margin-top: 9px;
  color: #465d77;
  font-size: 14px;
  line-height: 1.8;
  overflow-wrap: anywhere;
}
.row > .el-icon {
  flex: none;
  color: var(--catalog-accent);
  margin-top: 5px;
}
.summary {
  margin: 13px 0 0;
  color: #465d77;
  font-size: 16px;
  line-height: 1.8;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 9px 14px;
  margin-top: auto;
  padding-top: 20px;
}
.actions::before {
  content: '';
  width: 100%;
  height: 1px;
  background: #dce5ef;
}
.ext {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  min-height: 26px;
  color: #2255aa;
  text-decoration: none;
  background: none;
  border: none;
  padding: 0;
  font: inherit;
  font-size: 14px;
  font-weight: 500;
  line-height: 1.7;
  cursor: pointer;
}
.ext .el-icon {
  font-size: 14px;
}
.ext:hover {
  color: #153b7b;
  text-decoration: underline;
}
.ghost {
  color: #465d77;
}
.danger {
  color: #b52d39;
}
.danger:hover {
  color: #941e29;
}
.resource-label {
  margin-left: auto;
  color: #56677d;
  font-size: 14px;
  line-height: 1.5;
}
button:focus-visible, a:focus-visible {
  outline: 2px solid #2255aa;
  outline-offset: 4px;
  border-radius: 3px;
}
@media (max-width: 540px) {
  .card { padding: 20px; }
}
@media (prefers-reduced-motion: reduce) {
  .card { transition: none; }
}

.source {
  color: #206847;
  font-size: 14px;
  font-weight: 600;
  line-height: 1.6;
}
.status {
  padding: 3px 7px;
  margin-left: auto;
  color: #53657e;
  background: #f0f4f8;
  border-radius: 5px;
  font-size: 14px;
  white-space: nowrap;
}
.status.ongoing {
  color: #206847;
  background: #eaf5ed;
}
.meta {
  display: flex;
  align-items: center;
  gap: 6px;
}
.fund-facts {
  margin: 12px 0 0;
  padding: 14px;
  background: #f4f8f6;
  border: 1px solid #d9e8df;
  border-radius: 8px;
}
.fund-facts > div {
  display: flex;
  justify-content: space-between;
  align-items: start;
  gap: 14px;
  margin-bottom: 10px;
}
.fund-facts > div:last-child {
  margin-bottom: 0;
}
.fund-facts dt {
  color: #53657e;
  font-size: 14px;
  flex: none;
}
.fund-facts dd {
  color: #263b56;
  font-size: 14px;
  text-align: right;
  overflow-wrap: anywhere;
  margin: 0;
}
.mono {
  font-family: var(--lab-font-mono);
}
</style>

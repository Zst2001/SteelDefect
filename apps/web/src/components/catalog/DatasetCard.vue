<template>
  <article class="card">
    <div class="name">{{ dataset.name }}</div>
    <div class="meta">{{ taskLabel(dataset.task_type) }}</div>
    <div v-if="dataset.class_count != null" class="row">缺陷类别数量：{{ dataset.class_count }}</div>
    <div v-if="dataset.image_count != null" class="row">图像数量：{{ dataset.image_count }}</div>
    <div v-else-if="dataset.numbers_text" class="row">规模：{{ dataset.numbers_text }}</div>
    <div v-if="dataset.defect_types" class="row">缺陷类别：{{ dataset.defect_types }}</div>
    <div v-if="dataset.source_object" class="row">来源：{{ dataset.source_object }}</div>
    <div v-if="dataset.size" class="row">尺寸：{{ dataset.size }}</div>
    <div class="actions">
      <button class="ext ghost" type="button" @click="$emit('detail', dataset)">详情</button>
      <a
        v-if="dataset.url"
        class="ext"
        :href="dataset.url"
        target="_blank"
        rel="noopener noreferrer"
      >
        {{ dataset.access_note ? `下载 · ${dataset.access_note}` : "数据下载" }}
      </a>
      <span v-else class="missing">暂无链接</span>
      <template v-if="editable">
        <button class="ext ghost" type="button" @click="$emit('edit', dataset)">编辑</button>
        <button class="ext danger" type="button" @click="$emit('remove', dataset)">删除</button>
      </template>
    </div>
  </article>
</template>

<script setup lang="ts">
import { taskLabel, type CatalogDataset } from "../../api/catalog";

defineProps<{
  dataset: CatalogDataset;
  editable?: boolean;
}>();

defineEmits<{
  detail: [dataset: CatalogDataset];
  edit: [dataset: CatalogDataset];
  remove: [dataset: CatalogDataset];
}>();
</script>

<style scoped>
.card {
  background: var(--lab-panel);
  border: 1px solid var(--lab-line);
  padding: 18px;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  transition: border-color 180ms ease;
}
.card:hover {
  border-color: var(--lab-accent);
}
.name {
  font-weight: 600;
  margin-bottom: 6px;
  font-size: 16px;
}
.meta,
.row,
.missing {
  color: var(--lab-muted);
  font-size: 13px;
  line-height: 1.55;
}
.row {
  margin-top: 6px;
}
.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: auto;
  padding-top: 14px;
  align-items: center;
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

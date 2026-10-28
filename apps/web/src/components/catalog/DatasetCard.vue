<template>
  <article class="card">
    <div class="card-top"><span class="card-icon"><el-icon><Files /></el-icon></span><span class="kind">{{ taskLabel(dataset.task_type) }}</span><span class="resource-label">公开数据资源</span></div>
    <h3 class="name">{{ dataset.name }}</h3>
    <div v-if="dataset.class_count != null || dataset.image_count != null" class="dataset-numbers">
      <div v-if="dataset.image_count != null"><strong>{{ dataset.image_count.toLocaleString() }}</strong><span>图像数量</span></div>
      <div v-if="dataset.class_count != null"><strong>{{ dataset.class_count }}</strong><span>缺陷类别</span></div>
    </div>
    <div v-if="dataset.image_count == null && dataset.numbers_text" class="row"><span class="row-label">规模</span><span>{{ dataset.numbers_text }}</span></div>
    <div v-if="dataset.defect_types" class="row"><span class="row-label">类别</span><span>{{ dataset.defect_types }}</span></div>
    <div v-if="dataset.source_object" class="row"><span class="row-label">来源</span><span>{{ dataset.source_object }}</span></div>
    <div v-if="dataset.size" class="row"><span class="row-label">尺寸</span><span>{{ dataset.size }}</span></div>
    <div class="actions">
      <button class="ext ghost" type="button" @click="$emit('detail', dataset)">详情</button>
      <a
        v-if="dataset.url"
        class="ext"
        :href="dataset.url"
        target="_blank"
        rel="noopener noreferrer"
      >
        <el-icon><Download /></el-icon>{{ dataset.access_note ? `下载 · ${dataset.access_note}` : "数据下载" }}<el-icon><TopRight /></el-icon>
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
import { Download, Files, TopRight } from "@element-plus/icons-vue";
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
  --catalog-accent: #0b6b67;
  --catalog-tint: #eaf5f3;
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

.dataset-numbers {
  display: flex;
  flex-wrap: wrap;
  gap: 22px;
  padding: 15px 0;
  border-bottom: 1px solid #dce5ef;
  margin-bottom: 3px;
}
.dataset-numbers > div {
  min-width: 80px;
}
.dataset-numbers strong {
  display: block;
  font-family: var(--lab-font-mono);
  font-size: 25px;
  font-weight: 600;
  color: #0b6b67;
}
.dataset-numbers span {
  display: block;
  margin-top: 6px;
  color: #53657e;
  font-size: 14px;
}
.row-label {
  flex: none;
  min-width: 29px;
  color: #53657e;
}
.missing {
  font-size: 14px;
  color: #56677d;
}
</style>

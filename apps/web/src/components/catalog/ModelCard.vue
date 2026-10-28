<template>
  <article class="card">
    <div class="card-top"><span class="card-icon"><el-icon><Box /></el-icon></span><span v-if="model.task_type" class="kind">{{ taskLabel(model.task_type) }}</span><span class="resource-label">公开文献模型</span></div>
    <h3 class="name">{{ model.name }}</h3>
    <div v-if="metaLine" class="meta">{{ metaLine }}</div>
    <div v-if="tags.length" class="method-tags" aria-label="核心方法"><span v-for="tag in tags" :key="tag">{{ tag }}</span></div>
    <div v-if="model.dataset" class="row"><el-icon><Files /></el-icon><span>数据集：{{ model.dataset }}</span></div>
    <div class="actions">
      <a
        v-if="model.paper_url"
        class="ext"
        :href="model.paper_url"
        target="_blank"
        rel="noopener noreferrer"
      ><el-icon><Reading /></el-icon>论文<el-icon><TopRight /></el-icon></a>
      <a
        v-if="model.code_url"
        class="ext"
        :href="model.code_url"
        target="_blank"
        rel="noopener noreferrer"
      ><el-icon><Connection /></el-icon>代码<el-icon><TopRight /></el-icon></a>
      <button class="ext ghost" type="button" @click="$emit('detail', model)">详情</button>
      <template v-if="editable">
        <button class="ext ghost" type="button" @click="$emit('edit', model)">编辑</button>
        <button class="ext danger" type="button" @click="$emit('remove', model)">删除</button>
      </template>
    </div>
  </article>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { Box, Connection, Files, Reading, TopRight } from "@element-plus/icons-vue";
import { keywordTags, taskLabel, type CatalogModel } from "../../api/catalog";

const props = defineProps<{
  model: CatalogModel;
  editable?: boolean;
}>();

defineEmits<{
  detail: [model: CatalogModel];
  edit: [model: CatalogModel];
  remove: [model: CatalogModel];
}>();

const tags = computed(() => keywordTags(props.model.keywords));
const metaLine = computed(() => {
  const bits = [props.model.year ? String(props.model.year) : "", props.model.backbone ?? ""].filter(Boolean);
  return bits.join(" · ");
});
</script>

<style scoped>

.card {
  --catalog-accent: #2255aa;
  --catalog-tint: #edf3fb;
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

.method-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 10px 0 4px;
}
.method-tags span {
  color: #294c7d;
  background: #edf3fb;
  border: 1px solid #ccdbee;
  font-size: 14px;
  line-height: 1.6;
  padding: 3px 8px;
  border-radius: 5px;
  overflow-wrap: anywhere;
}
</style>

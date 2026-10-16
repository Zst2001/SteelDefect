<template>
  <article class="card">
    <div class="name">{{ model.name }}</div>
    <div v-if="metaLine" class="meta">{{ metaLine }}</div>
    <div v-if="model.task_type" class="row">任务：{{ taskLabel(model.task_type) }}</div>
    <div v-if="tags.length" class="row">核心方法：{{ tags.join("、") }}</div>
    <div v-if="model.dataset" class="row">数据集：{{ model.dataset }}</div>
    <div class="actions">
      <a
        v-if="model.paper_url"
        class="ext"
        :href="model.paper_url"
        target="_blank"
        rel="noopener noreferrer"
      >论文</a>
      <a
        v-if="model.code_url"
        class="ext"
        :href="model.code_url"
        target="_blank"
        rel="noopener noreferrer"
      >代码</a>
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
.name {
  font-weight: 600;
  margin-bottom: 6px;
  font-size: 16px;
}
.meta,
.row,
.tags {
  color: var(--lab-muted);
  font-size: 13px;
  line-height: 1.55;
}
.meta {
  font-family: var(--lab-font-mono);
  font-size: 11px;
  letter-spacing: 0.06em;
  margin-bottom: 8px;
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

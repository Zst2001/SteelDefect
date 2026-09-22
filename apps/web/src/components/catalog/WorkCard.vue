<template>
  <article class="card">
    <div class="kind">{{ kindLabel }}</div>
    <div class="name">{{ work.name }}</div>
    <div v-if="metaLine" class="meta">{{ metaLine }}</div>
    <div v-if="work.authors" class="row">作者：{{ work.authors }}</div>
    <p v-if="work.summary" class="summary">{{ work.summary }}</p>
    <div class="actions">
      <button class="ext ghost" type="button" @click="$emit('detail', work)">详情</button>
      <a
        v-if="work.link_url"
        class="ext"
        :href="work.link_url"
        target="_blank"
        rel="noopener noreferrer"
      >查看原文</a>
      <template v-if="editable">
        <button class="ext ghost" type="button" @click="$emit('edit', work)">编辑</button>
        <button class="ext danger" type="button" @click="$emit('remove', work)">删除</button>
      </template>
    </div>
  </article>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { WORK_KIND_LABELS, type CatalogWork } from "../../api/catalog";

const props = defineProps<{
  work: CatalogWork;
  editable?: boolean;
}>();

defineEmits<{
  detail: [work: CatalogWork];
  edit: [work: CatalogWork];
  remove: [work: CatalogWork];
}>();

const kindLabel = computed(() => WORK_KIND_LABELS[props.work.kind] ?? "成果");
const metaLine = computed(() => {
  const bits = [props.work.year ? String(props.work.year) : "", props.work.venue ?? ""].filter(Boolean);
  return bits.join(" · ");
});
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
.kind {
  color: var(--lab-accent-2);
  font-size: 12px;
  letter-spacing: 0.08em;
  margin-bottom: 8px;
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

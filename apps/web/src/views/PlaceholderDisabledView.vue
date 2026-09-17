<template>
  <div>
    <h1>{{ title }}</h1>
    <p v-if="kind === 'detection'">规划中的数据格式：检测框；指标为 mAP。第一版不跑真实检测任务。</p>
    <p v-else>规划中的数据格式：图级标签；指标为 Accuracy / F1。第一版不跑真实分类任务。</p>
    <el-button disabled>提交任务（未开放）</el-button>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { useRoute } from "vue-router";

const route = useRoute();
const title = computed(() => String(route.meta.title ?? "占位"));
const kind = computed(() => String(route.meta.kind ?? "detection"));
</script>

<style scoped>
p {
  color: var(--lab-muted);
  max-width: 640px;
  line-height: 1.7;
}
</style>

<template>
  <div>
    <nav class="switch" aria-label="钢铁检测方向">
      <router-link
        v-for="item in tasks"
        :key="item.id"
        :to="`/inspect/steel/${item.id}`"
        :class="{ on: task === item.id }"
      >
        {{ item.label }}
      </router-link>
    </nav>
    <CompareNewView v-if="task === 'segmentation'" />
    <section v-else-if="task === 'detection'">
      <h1>目标检测</h1>
      <p>规划中的数据格式：检测框；指标为 mAP。第一版不跑真实检测任务。</p>
      <el-button disabled>提交任务（未开放）</el-button>
    </section>
    <section v-else-if="task === 'classification'">
      <h1>缺陷分类</h1>
      <p>规划中的数据格式：图级标签；指标为 Accuracy / F1。第一版不跑真实分类任务。</p>
      <el-button disabled>提交任务（未开放）</el-button>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import CompareNewView from "../compare/CompareNewView.vue";

const tasks = [
  { id: "segmentation", label: "缺陷分割" },
  { id: "detection", label: "目标检测" },
  { id: "classification", label: "缺陷分类" },
] as const;

const route = useRoute();
const router = useRouter();
const task = computed(() => String(route.params.task ?? ""));

watch(
  task,
  (value) => {
    if (!tasks.some((item) => item.id === value)) {
      void router.replace("/inspect/steel/segmentation");
    }
  },
  { immediate: true },
);
</script>

<style scoped>
.switch {
  display: flex;
  gap: 8px;
  margin-bottom: 20px;
}
.switch a {
  text-decoration: none;
  color: var(--lab-muted);
  border: 1px solid var(--lab-line);
  background: var(--lab-panel);
  padding: 8px 14px;
  font-family: var(--lab-font);
}
.switch a.on {
  color: var(--lab-text);
  border-color: var(--lab-fiducial);
  background: var(--lab-nav-active);
}
section p {
  color: var(--lab-muted);
  max-width: 640px;
  line-height: 1.7;
}
</style>

<template>
  <div>
    <h1>{{ title }}</h1>
    <p>{{ hint }}</p>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { useRoute } from "vue-router";

const route = useRoute();
const title = computed(() => String(route.meta.title ?? "页面"));
const hint = computed(() => String(route.meta.hint ?? ""));
</script>

<style scoped>
p {
  color: var(--lab-muted);
  max-width: 640px;
  line-height: 1.7;
}
</style>

<template>
  <div>
    <header class="head">
      <p class="eyebrow">课题组科研网站</p>
      <h1>首页</h1>
      <p>
        钢铁缺陷分割对照台。下列为公开论文代码与基准数据（外链打开），与本站可运行模型、评测集不是同一套资源。
      </p>
      <router-link class="go" to="/workbench">进入工作台</router-link>
    </header>
    <OpenResourcesSection />
  </div>
</template>

<script setup lang="ts">
import OpenResourcesSection from "../components/OpenResourcesSection.vue";
</script>

<style scoped>
.eyebrow {
  color: var(--lab-accent-2);
  letter-spacing: 0.16em;
  font-size: 12px;
  margin: 0 0 8px;
}
.head h1 {
  margin: 0 0 8px;
}
.head p {
  color: var(--lab-muted);
  line-height: 1.6;
  max-width: 720px;
}
.go {
  display: inline-block;
  margin: 16px 0 8px;
  color: var(--lab-accent-2);
  text-decoration: none;
}
.go:hover {
  text-decoration: underline;
}
</style>

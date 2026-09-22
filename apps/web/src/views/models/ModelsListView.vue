<template>
  <div>
    <header class="head">
      <p class="eyebrow">模型中心</p>
      <h1>模型库</h1>
      <p>内置 baseline 只读。学生模型经自动检查后才能加入对比；不能启动的模型会标明失败阶段。</p>
    </header>

    <div class="toolbar">
      <router-link to="/models/import">
        <el-button type="primary">导入 .py + .pth</el-button>
      </router-link>
      <router-link to="/models/perf">去模型测评</router-link>
      <router-link to="/models/scatter">性能散点图</router-link>
      <router-link to="/compare/new">去缺陷分割</router-link>
    </div>

    <section class="block">
      <h2>内置 baseline</h2>
      <div class="cards">
        <router-link v-for="model in builtins" :key="model.id" class="card" :to="`/models/${model.id}`">
          <div class="name">{{ model.name }}</div>
          <div class="meta">{{ model.slug }} · 语义分割</div>
          <div class="tags">
            <span>{{ modelStatusLabel(model.status) }}</span>
            <span>{{ model.requires_cuda ? "当前环境不可运行" : "CPU" }}</span>
            <span>{{ formatParamCount(model.param_count) }}</span>
            <span>{{ formatFps(model.fps_per_image) }}</span>
          </div>
        </router-link>
      </div>
    </section>

    <section class="block">
      <h2>我的导入</h2>
      <p v-if="!mine.length" class="empty">还没有学生模型。从导入入口提交 .py 与 .pth。</p>
      <div v-else class="cards">
        <router-link v-for="model in mine" :key="model.id" class="card" :to="`/models/${model.id}`">
          <div class="name">{{ model.name }}</div>
          <div class="meta">{{ modelStatusLabel(model.status) }}</div>
          <div v-if="model.fail_stage" class="fail">{{ model.fail_stage }} / {{ model.fail_message }}</div>
        </router-link>
      </div>
    </section>

    <section class="block">
      <h2>课题组共享</h2>
      <p v-if="!shared.length" class="empty">还没有共享到课题组的学生模型。</p>
      <div v-else class="cards">
        <router-link v-for="model in shared" :key="model.id" class="card" :to="`/models/${model.id}`">
          <div class="name">{{ model.name }}</div>
          <div class="meta">{{ modelStatusLabel(model.status) }}</div>
        </router-link>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { http } from "../../api/http";
import { formatFps, formatParamCount, modelStatusLabel } from "../../api/labels";

type Card = {
  id: string;
  name: string;
  slug: string;
  source?: string;
  status: string;
  requires_cuda: boolean;
  fail_stage: string | null;
  fail_message: string | null;
  param_count?: number | null;
  fps_per_image?: number | null;
};

const builtins = ref<Card[]>([]);
const mine = ref<Card[]>([]);
const shared = ref<Card[]>([]);

async function loadList() {
  const { data } = await http.get("/models");
  const items = (data.items ?? []) as Card[];
  builtins.value = data.builtins ?? items.filter((row) => row.source === "builtin");
  mine.value = data.mine ?? [];
  shared.value = data.shared ?? [];
}

onMounted(loadList);
</script>

<style scoped>
.eyebrow {
  color: var(--lab-accent-2);
  letter-spacing: 0.16em;
  font-size: 12px;
}
.head p,
.empty,
.meta,
.fail,
.tags {
  color: var(--lab-muted);
}
.toolbar {
  display: flex;
  gap: 16px;
  align-items: center;
  margin: 16px 0 28px;
}
.block {
  margin-bottom: 36px;
}
.cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 14px;
}
.card {
  display: block;
  text-decoration: none;
  background: var(--lab-panel);
  border: 1px solid var(--lab-line);
  padding: 18px;
  transition: border-color 180ms ease;
}
.card:hover {
  border-color: var(--lab-accent);
}
.name {
  font-weight: 600;
  margin-bottom: 6px;
}
.tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
  font-size: 12px;
}
</style>

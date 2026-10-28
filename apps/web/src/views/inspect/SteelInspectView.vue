<template>
  <div class="steel-page">
    <header class="head steel-head">
      <div>
        <p class="eyebrow">STEEL INSPECTION / 钢铁表面检测</p>
        <h1>{{ task === 'segmentation' ? '钢铁表面缺陷分割' : task === 'detection' ? '钢铁表面目标检测' : '钢铁表面缺陷分类' }}</h1>
        <p>{{ task === 'segmentation' ? '上传原图、选择模型，在同一批图像上完成分割对照。' : task === 'classification' ? '使用已接入的 CPU 内置模型，识别整张图像所属的已知缺陷类别。' : '当前方向暂未开放，请使用已经接入的钢铁语义分割。' }}</p>
      </div>
    </header>
    <div class="scene-toolbar">
      <nav class="switch" aria-label="钢铁检测方向">
      <router-link
        v-for="item in tasks"
        :key="item.id"
        :to="`/inspect/steel/${item.id}`"
        :class="{ on: task === item.id }"
      >
        <el-icon><component :is="item.icon" /></el-icon>
        {{ item.label }}<small v-if="item.id === 'detection'">未开放</small>
      </router-link>
      </nav>
      <router-link v-if="task === 'segmentation'" class="eval-shortcut" to="/eval/new"><el-icon><DataAnalysis /></el-icon> NEU-20 正式评测 <el-icon><ArrowRight /></el-icon></router-link>
      <router-link v-else-if="task === 'classification'" class="eval-shortcut" to="/records"><el-icon><DataAnalysis /></el-icon> 结果记录 <el-icon><ArrowRight /></el-icon></router-link>
    </div>
    <CompareNewView v-if="task === 'segmentation'" embedded />
    <section v-else-if="task === 'detection'" class="wb-panel unavailable-scene">
      <span class="placeholder-icon"><el-icon><Aim /></el-icon></span>
      <span class="placeholder-status">尚未开放</span>
      <h1>目标检测</h1>
      <p>规划中的数据格式：检测框；指标为 mAP。第一版不跑真实检测任务。</p>
      <el-button disabled>提交任务（未开放）</el-button>
      <router-link to="/inspect/steel/segmentation">前往缺陷分割 <el-icon><ArrowRight /></el-icon></router-link>
    </section>
    <ClassifyNewView v-else-if="task === 'classification'" />
  </div>
</template>

<script setup lang="ts">
import { computed, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { Aim, ArrowRight, DataAnalysis, Grid, Picture } from "@element-plus/icons-vue";
import CompareNewView from "../compare/CompareNewView.vue";
import ClassifyNewView from "../classification/ClassifyNewView.vue";

const tasks = [
  { id: "segmentation", label: "缺陷分割", icon: Picture },
  { id: "detection", label: "目标检测", icon: Aim },
  { id: "classification", label: "缺陷分类", icon: Grid },
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
.steel-page {
  display: grid;
  grid-template-columns: minmax(280px, .85fr) minmax(0, 1.45fr);
  column-gap: 24px;
  align-items: center;
}
.steel-page > :deep(.submission-page), .steel-page > :deep(.classification-new), .unavailable-scene {
  grid-column: 1 / -1;
}
.steel-head {
  display: flex;
  gap: 24px;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 18px;
}
.steel-head p {
  color: var(--lab-muted);
  margin: 4px 0 0;
  font-size: 14px;
}
.steel-head h1 {
  font-size: 28px;
  margin: 0 0 6px;
}
.steel-head .eyebrow {
  color: var(--lab-fiducial);
  letter-spacing: .12em;
  font-size: 9px;
  margin-bottom: 6px;
}
.eval-shortcut {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  flex-shrink: 0;
  border: 1px solid #d9e4f4;
  background: #fff;
  padding: 10px 13px;
  border-radius: 7px;
  color: #51749f;
  text-decoration: none;
  font-size: 14px;
}
.scene-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 18px;
}
.switch {
  display: inline-flex;
  gap: 4px;
  flex-wrap: nowrap;
  padding: 5px;
  border: 1px solid #dde6f1;
  border-radius: 10px;
  background: #eaf0f8;
}
.switch a {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  text-decoration: none;
  color: #7c8ca2;
  padding: 9px 11px;
  font-family: var(--lab-font);
  border: 1px solid transparent;
  border-radius: 7px;
  font-size: 14px;
}
.switch a.on {
  color: #2365d9;
  background: #fff;
  border-color: #d4e2f7;
  box-shadow: 0 2px 5px #243c6310;
  font-weight: 600;
}
.switch a:hover {
  color: var(--lab-fiducial);
}
.switch small {
  color: #929fb3;
  border: 1px solid #d9e2ed;
  padding: 1px 4px;
  border-radius: 4px;
  font-size: 9px;
  font-weight: 400;
}
.unavailable-scene {
  display: flex;
  align-items: center;
  flex-direction: column;
  justify-content: center;
  min-height: 380px;
  padding: 48px 24px;
  text-align: center;
}
.placeholder-icon {
  display: grid;
  place-items: center;
  width: 68px;
  height: 68px;
  background: #edf3fc;
  color: #86a8d5;
  font-size: 32px;
  border-radius: 20px;
  margin-bottom: 22px;
}
.placeholder-status {
  background: #f1f5fa;
  color: #8090a6;
  border-radius: 5px;
  padding: 4px 8px;
  font-size: 10px;
}
.unavailable-scene h1 {
  font-size: 25px;
  margin: 15px 0 0;
}
.unavailable-scene p {
  color: var(--lab-muted);
  max-width: 640px;
  line-height: 1.8;
  font-size: 15px;
  margin-bottom: 24px;
}
.unavailable-scene a {
  display: flex;
  align-items: center;
  gap: 5px;
  color: var(--lab-fiducial);
  font-size: 14px;
  text-decoration: none;
  margin-top: 17px;
}
@media (max-width: 1250px) {
  .steel-page {
    grid-template-columns: minmax(0, 1fr);
  }
  .steel-head {
    margin-bottom: 12px;
  }
  .scene-toolbar {
    margin-bottom: 18px;
  }
}
@media (max-width: 740px) {
  .steel-head {
    align-items: flex-start;
    flex-direction: column;
    gap: 6px;
  }
  .scene-toolbar {
    align-items: flex-start;
    flex-direction: column;
  }
  .switch {
    width: 100%;
    box-sizing: border-box;
  }
  .switch a {
    flex: 1;
    justify-content: center;
    padding: 9px 7px;
    gap: 5px;
    font-size: 14px;
  }
  .switch small {
    font-size: 8px;
  }
}
</style>

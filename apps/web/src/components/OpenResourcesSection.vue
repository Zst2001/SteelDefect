<template>
  <section class="block">
    <h3>相关模型与公开数据集</h3>
    <p class="lead">
      公开论文代码与基准数据，外链打开；与本站可运行模型、评测集不是同一套资源。
    </p>
    <el-tabs v-model="tab">
      <el-tab-pane label="分割模型" name="models">
        <div class="cards">
          <article v-for="model in segmentationModels" :key="model.name" class="card">
            <div class="name">{{ model.name }}</div>
            <div class="meta">{{ model.year }} · {{ model.backbone }}</div>
            <div class="tags">
              <span v-for="tag in keywordTags(model.keywords)" :key="tag">{{ tag }}</span>
            </div>
            <a
              v-if="model.codeUrl"
              class="ext"
              :href="model.codeUrl"
              target="_blank"
              rel="noopener noreferrer"
            >
              代码仓库
            </a>
            <span v-else class="missing">暂无链接</span>
          </article>
        </div>
      </el-tab-pane>
      <el-tab-pane
        v-for="group in datasetGroups"
        :key="group.name"
        :label="group.label"
        :name="group.name"
      >
        <el-table :data="group.rows" size="small">
          <el-table-column prop="name" label="名称" min-width="160" />
          <el-table-column prop="object" label="对象" min-width="160" />
          <el-table-column prop="numbers" label="规模" min-width="220" />
          <el-table-column prop="size" label="尺寸" min-width="140" />
          <el-table-column label="链接" min-width="140">
            <template #default="{ row }">
              <a
                v-if="row.url"
                class="ext"
                :href="row.url"
                target="_blank"
                rel="noopener noreferrer"
              >
                打开
                <template v-if="row.accessNote"> · {{ row.accessNote }}</template>
              </a>
              <span v-else class="missing">暂无链接</span>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>
  </section>
</template>

<script setup lang="ts">
import { ref } from "vue";
import {
  classificationDatasets,
  detectionDatasets,
  segmentationDatasets,
  segmentationModels,
} from "../data/openResources";

const tab = ref("models");

const datasetGroups = [
  { name: "classification", label: "分类数据集", rows: classificationDatasets },
  { name: "detection", label: "检测数据集", rows: detectionDatasets },
  { name: "segmentation", label: "分割数据集", rows: segmentationDatasets },
];

function keywordTags(keywords: string) {
  return keywords
    .split(";")
    .map((part) => part.trim())
    .filter(Boolean);
}
</script>

<style scoped>
.block {
  margin-bottom: 32px;
}
.block h3 {
  margin: 0 0 8px;
}
.lead,
.meta,
.tags,
.missing {
  color: var(--lab-muted);
}
.lead {
  line-height: 1.6;
  margin: 0 0 16px;
}
.cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 14px;
  padding: 4px 0 8px;
}
.card {
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
.ext {
  color: var(--lab-accent-2);
  text-decoration: none;
}
.card .ext,
.card .missing {
  display: inline-block;
  margin-top: 14px;
}
.ext:hover {
  text-decoration: underline;
}
:deep(.el-tabs__active-bar) {
  background-color: var(--lab-accent);
}
:deep(.el-tabs__item.is-active),
:deep(.el-tabs__item:hover) {
  color: var(--lab-accent-2);
}
</style>

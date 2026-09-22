<template>
  <div>
    <header class="hero">
      <div class="hero-inner">
        <h1 class="hero-title">智能感知与精密工业检测实验室</h1>
        <p class="hero-subtitle">江西师范大学人工智能学院 · IPPI Lab</p>
        <p class="hero-desc">
          智能感知与精密工业检测实验室（IPPI Lab）隶属于江西师范大学人工智能学院，由邹翔老师领衔。实验室聚焦计算机视觉前沿领域，深耕工业缺陷检测与精密图像分割核心方向，科研工作获国家自然科学基金、江西省科技创新基地计划等国家级与省级项目资助。团队现有师生20余人，以计算机技术、软件工程专业硕士为核心力量，科研成果丰硕，人才培养成效突出，多名优秀本科生保研至985高校深造。
        </p>
        <p class="hero-site">本站是实验室的科研实验平台，汇集成果、公开模型与数据集，并提供对照与演示。</p>
        <details class="about" @toggle="onAboutToggle">
          <summary>{{ aboutOpen ? "收起介绍" : "详细介绍" }}</summary>
          <div class="about-body">
            <p>
              智能感知与精密工业检测实验室（Intelligent Perception and Precision Industrial Inspection Laboratory，简称IPPI Lab）隶属于江西师范大学人工智能学院，由邹翔老师领衔组建。实验室现有核心成员二十余名，以计算机技术、软件工程专业硕士研究生为主体，同时吸纳优秀本科生参与科研攻关。团队立足计算机视觉学科前沿，聚焦工业缺陷检测、工业图像精密分割核心研究方向，围绕智能感知基础算法、工业场景高精度检测、缺陷语义分割与实例分割等方向开展系统性理论创新与应用落地研究，致力于破解高端制造领域精密质检的关键技术难题。
            </p>
            <p>
              实验室科研工作得到国家级与省级科研基金的持续资助，相关研究先后获得国家自然科学基金项目（项目编号：62202211）、江西省科技创新基地计划项目（项目编号：20242BCC32021）支持，配备完善的算力支撑平台与工业实验环境，为高质量科研产出提供了坚实保障。
            </p>
            <p>
              团队科研成果与人才培养成效突出：研究生成员累计斩获多项国家级、省级专业竞赛奖项与学术荣誉，研究成果陆续发表于国内外权威期刊与学术会议；人才培养梯队建设成果显著，先后有多名优秀本科生成员保研至985高校深造，构建了“本研衔接、研用结合”的高质量人才培养体系。
            </p>
            <p>
              面向未来，实验室将紧扣智能制造国家战略需求，持续深耕智能感知与精密工业检测领域，致力建设成为省内领先、国内具有一定影响力的工业视觉科研创新与高水平人才培养基地。
            </p>
          </div>
        </details>
        <div class="hero-actions">
          <router-link class="btn btn-primary" to="/workbench">进入工作台</router-link>
          <a class="btn btn-secondary" href="#research-works" @click.prevent="scrollTo('research-works')">查看研究成果</a>
        </div>
      </div>
    </header>

    <section class="stats" aria-label="平台数据统计">
      <div class="stat">
        <div class="stat-label">研究模型</div>
        <div class="stat-value">{{ stats.research_models }}</div>
      </div>
      <div class="stat">
        <div class="stat-label">论文成果</div>
        <div class="stat-value">{{ stats.papers }}</div>
      </div>
      <button v-if="isAdvisor" class="edit-stats" type="button" @click="editingStats = true">编辑统计</button>
    </section>

    <section id="research-works" class="block">
      <div class="head-row">
        <div>
          <h2>课题组研究成果</h2>
          <p class="lead">本组论文、专利、软著与奖项等成果条目。只展示有哪些成果，不提供代码仓库。</p>
        </div>
        <el-button v-if="isAdvisor" type="primary" @click="creatingWork = true">上传成果</el-button>
      </div>
      <div v-if="works.length" class="cards">
        <WorkCard
          v-for="item in works"
          :key="item.id"
          :work="item"
          :editable="isAdvisor"
          @detail="detailWork = $event"
          @edit="editWork = $event"
          @remove="removeWork"
        />
      </div>
      <p v-else class="empty">暂无课题组研究成果。导师可在此录入真实成果，不编造条目。</p>
    </section>

    <section id="advisor-funds" class="block">
      <div class="head-row">
        <div>
          <h2>导师科研基金</h2>
          <p class="lead">导师主持或参与的科研项目与基金。按真实立项信息展示，没有批准号或金额则留空。</p>
        </div>
        <el-button v-if="isAdvisor" type="primary" @click="creatingFund = true">新增基金</el-button>
      </div>
      <div v-if="funds.length" class="cards">
        <FundCard
          v-for="item in funds"
          :key="item.id"
          :fund="item"
          :editable="isAdvisor"
          @detail="detailFund = $event"
          @edit="editFund = $event"
          @remove="removeFund"
        />
      </div>
      <p v-else class="empty">暂无导师基金条目。导师可在此录入真实立项信息。</p>
    </section>

    <section id="defect-models" class="block">
      <div class="head-row">
        <div>
          <h2>钢铁缺陷模型</h2>
          <p class="lead">公开文献与代码仓库中的钢铁缺陷模型，外链打开；与本站可运行权重不是同一套资源。</p>
        </div>
        <el-button v-if="isAdvisor" @click="creatingModel = true">新增模型</el-button>
      </div>
      <div class="filters">
        <button
          v-for="item in TASK_FILTERS"
          :key="item"
          class="chip"
          :class="{ on: modelFilter === item }"
          type="button"
          @click="modelFilter = item"
        >
          {{ TASK_LABELS[item] }}
        </button>
      </div>
      <div v-if="filteredModels.length" class="cards">
        <ModelCard
          v-for="item in filteredModels"
          :key="item.id"
          :model="item"
          :editable="isAdvisor"
          @detail="detailModel = $event"
          @edit="editModel = $event"
          @remove="removeModel"
        />
      </div>
      <p v-else class="empty">该任务类型暂无模型条目。</p>
    </section>

    <section id="defect-datasets" class="block">
      <div class="head-row">
        <div>
          <h2>钢铁缺陷数据集</h2>
          <p class="lead">分类、检测、分割公开数据集。仅展示来源中已有的规模与链接，不编造类别名单或精度。</p>
        </div>
        <el-button v-if="isAdvisor" @click="creatingDataset = true">新增数据集</el-button>
      </div>
      <div class="filters">
        <button
          v-for="item in TASK_FILTERS"
          :key="item"
          class="chip"
          :class="{ on: datasetFilter === item }"
          type="button"
          @click="datasetFilter = item"
        >
          {{ TASK_LABELS[item] }}
        </button>
      </div>
      <div v-if="filteredDatasets.length" class="cards">
        <DatasetCard
          v-for="item in filteredDatasets"
          :key="item.id"
          :dataset="item"
          :editable="isAdvisor"
          @detail="detailDataset = $event"
          @edit="editDataset = $event"
          @remove="removeDataset"
        />
      </div>
      <p v-else class="empty">该任务类型暂无数据集条目。</p>
    </section>

    <p v-if="loadError" class="err">{{ loadError }}</p>

    <DetailDialog
      v-model:model="detailModel"
      v-model:dataset="detailDataset"
      v-model:work="detailWork"
      v-model:fund="detailFund"
    />
    <WorkFormDialog :work="editWork" :create="creatingWork" @close="closeWorkForm" @saved="reload" />
    <FundFormDialog :fund="editFund" :create="creatingFund" @close="closeFundForm" @saved="reload" />
    <ModelFormDialog
      :model="editModel"
      :create="creatingModel"
      @close="closeModelForm"
      @saved="reload"
    />
    <DatasetFormDialog
      :dataset="editDataset"
      :create="creatingDataset"
      @close="closeDatasetForm"
      @saved="reload"
    />

    <el-dialog v-model="editingStats" title="编辑平台统计" width="420px">
      <el-form label-position="top">
        <el-form-item label="研究模型">
          <el-input-number v-model="statsForm.research_models" :min="0" :max="99999" />
        </el-form-item>
        <el-form-item label="论文成果">
          <el-input-number v-model="statsForm.papers" :min="0" :max="99999" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editingStats = false">取消</el-button>
        <el-button type="primary" :loading="savingStats" @click="saveStats">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  TASK_FILTERS,
  TASK_LABELS,
  fetchCatalog,
  filterByTask,
  type CatalogDataset,
  type CatalogFund,
  type CatalogModel,
  type CatalogStats,
  type CatalogWork,
  type TaskType,
} from "../api/catalog";
import { formatError, http } from "../api/http";
import DatasetCard from "../components/catalog/DatasetCard.vue";
import DatasetFormDialog from "../components/catalog/DatasetFormDialog.vue";
import DetailDialog from "../components/catalog/DetailDialog.vue";
import FundCard from "../components/catalog/FundCard.vue";
import FundFormDialog from "../components/catalog/FundFormDialog.vue";
import ModelCard from "../components/catalog/ModelCard.vue";
import ModelFormDialog from "../components/catalog/ModelFormDialog.vue";
import WorkCard from "../components/catalog/WorkCard.vue";
import WorkFormDialog from "../components/catalog/WorkFormDialog.vue";

const stats = ref<CatalogStats>({ research_models: 0, papers: 0, updated_at: "" });
const models = ref<CatalogModel[]>([]);
const datasets = ref<CatalogDataset[]>([]);
const works = ref<CatalogWork[]>([]);
const funds = ref<CatalogFund[]>([]);
const isAdvisor = ref(false);
const loadError = ref("");
const modelFilter = ref<TaskType | "all">("all");
const datasetFilter = ref<TaskType | "all">("all");
const detailModel = ref<CatalogModel | null>(null);
const detailDataset = ref<CatalogDataset | null>(null);
const detailWork = ref<CatalogWork | null>(null);
const detailFund = ref<CatalogFund | null>(null);
const editModel = ref<CatalogModel | null>(null);
const creatingModel = ref(false);
const editDataset = ref<CatalogDataset | null>(null);
const creatingDataset = ref(false);
const editWork = ref<CatalogWork | null>(null);
const creatingWork = ref(false);
const editFund = ref<CatalogFund | null>(null);
const creatingFund = ref(false);
const editingStats = ref(false);
const savingStats = ref(false);
const aboutOpen = ref(false);
const statsForm = reactive({ research_models: 0, papers: 0 });

const filteredModels = computed(() => filterByTask(models.value, modelFilter.value));
const filteredDatasets = computed(() => filterByTask(datasets.value, datasetFilter.value));

watch(editingStats, (open) => {
  if (open) {
    statsForm.research_models = stats.value.research_models;
    statsForm.papers = stats.value.papers;
  }
});

function scrollTo(id: string) {
  document.getElementById(id)?.scrollIntoView({ block: "start" });
}

function onAboutToggle(event: Event) {
  const el = event.target;
  aboutOpen.value = el instanceof HTMLDetailsElement && el.open;
}

async function reload() {
  loadError.value = "";
  try {
    const data = await fetchCatalog();
    stats.value = data.stats;
    models.value = data.models;
    datasets.value = data.datasets;
    works.value = data.works ?? [];
    funds.value = data.funds ?? [];
  } catch (err) {
    loadError.value = formatError(err);
  }
}

function closeModelForm() {
  editModel.value = null;
  creatingModel.value = false;
}

function closeWorkForm() {
  editWork.value = null;
  creatingWork.value = false;
}

function closeFundForm() {
  editFund.value = null;
  creatingFund.value = false;
}

function closeDatasetForm() {
  editDataset.value = null;
  creatingDataset.value = false;
}

async function saveStats() {
  savingStats.value = true;
  try {
    const { data } = await http.put("/catalog/stats", {
      research_models: statsForm.research_models,
      papers: statsForm.papers,
    });
    stats.value = data;
    editingStats.value = false;
    ElMessage.success("统计已更新");
  } catch (err) {
    ElMessage.error(formatError(err));
  } finally {
    savingStats.value = false;
  }
}

async function removeModel(item: CatalogModel) {
  try {
    await ElMessageBox.confirm(`删除「${item.name}」？此操作不可恢复。`, "删除", {
      confirmButtonText: "删除",
      cancelButtonText: "取消",
      type: "warning",
    });
    await http.delete(`/catalog/models/${item.id}`);
    ElMessage.success("已删除");
    await reload();
  } catch (err) {
    if (err === "cancel" || err === "close") {
      return;
    }
    ElMessage.error(formatError(err));
  }
}

async function removeDataset(item: CatalogDataset) {
  try {
    await ElMessageBox.confirm(`删除数据集「${item.name}」？`, "删除", {
      confirmButtonText: "删除",
      cancelButtonText: "取消",
      type: "warning",
    });
    await http.delete(`/catalog/datasets/${item.id}`);
    ElMessage.success("已删除");
    await reload();
  } catch (err) {
    if (err === "cancel" || err === "close") {
      return;
    }
    ElMessage.error(formatError(err));
  }
}

async function removeWork(item: CatalogWork) {
  try {
    await ElMessageBox.confirm(`删除成果「${item.name}」？此操作不可恢复。`, "删除", {
      confirmButtonText: "删除",
      cancelButtonText: "取消",
      type: "warning",
    });
    await http.delete(`/catalog/works/${item.id}`);
    ElMessage.success("已删除");
    await reload();
  } catch (err) {
    if (err === "cancel" || err === "close") {
      return;
    }
    ElMessage.error(formatError(err));
  }
}

async function removeFund(item: CatalogFund) {
  try {
    await ElMessageBox.confirm(`删除基金「${item.name}」？此操作不可恢复。`, "删除", {
      confirmButtonText: "删除",
      cancelButtonText: "取消",
      type: "warning",
    });
    await http.delete(`/catalog/funds/${item.id}`);
    ElMessage.success("已删除");
    await reload();
  } catch (err) {
    if (err === "cancel" || err === "close") {
      return;
    }
    ElMessage.error(formatError(err));
  }
}

onMounted(async () => {
  await reload();
  try {
    const { data } = await http.get("/auth/me");
    isAdvisor.value = data.role === "advisor";
  } catch {
    isAdvisor.value = false;
  }
});
</script>

<style scoped>
.hero {
  background: var(--lab-panel);
  border: 1px solid var(--lab-line);
  border-left: 3px solid var(--lab-accent);
  padding: 40px 36px 36px;
  margin-bottom: 28px;
}
.hero-inner {
  max-width: 720px;
}
.hero-title {
  margin: 0 0 14px;
  font-size: 32px;
  font-weight: 700;
  line-height: 1.28;
  letter-spacing: 0.02em;
}
.hero-subtitle {
  margin: 0 0 18px;
  font-size: 16px;
  line-height: 1.55;
  color: var(--lab-accent-2);
}
.hero-desc {
  margin: 0 0 12px;
  color: var(--lab-muted);
  font-size: 14px;
  line-height: 1.75;
}
.hero-site {
  margin: 0 0 16px;
  color: var(--lab-muted);
  font-size: 13px;
  line-height: 1.7;
}
.about {
  margin: 0 0 28px;
}
.about summary {
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--lab-accent-2);
  font-size: 14px;
  list-style: none;
}
.about summary::-webkit-details-marker {
  display: none;
}
.about summary::after {
  content: "";
  width: 0;
  height: 0;
  border-left: 4px solid transparent;
  border-right: 4px solid transparent;
  border-top: 5px solid currentColor;
  transform: translateY(1px);
}
.about[open] summary::after {
  transform: translateY(-1px) rotate(180deg);
}
.about summary:hover {
  color: var(--lab-text);
}
.about-body {
  margin-top: 14px;
}
.about-body p {
  margin: 0 0 12px;
  color: var(--lab-muted);
  font-size: 14px;
  line-height: 1.75;
}
.about-body p:last-child {
  margin-bottom: 0;
}
.hero-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 40px;
  padding: 8px 20px;
  font-size: 14px;
  text-decoration: none;
  box-sizing: border-box;
}
.btn-primary {
  background: var(--lab-accent);
  border: 1px solid var(--lab-accent);
  color: var(--lab-text);
  font-weight: 600;
}
.btn-primary:hover {
  background: #d46832;
  border-color: #d46832;
}
.btn-secondary {
  background: transparent;
  border: 1px solid var(--lab-line);
  color: var(--lab-text);
}
.btn-secondary:hover {
  border-color: var(--lab-accent);
  color: var(--lab-accent-2);
}
.stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 180px));
  gap: 14px;
  margin: 0 0 36px;
  align-items: stretch;
}
.stat {
  background: var(--lab-panel);
  border: 1px solid var(--lab-line);
  padding: 18px 20px;
}
.stat-label {
  color: var(--lab-muted);
  font-size: 13px;
}
.stat-value {
  margin-top: 8px;
  font-size: 32px;
  font-weight: 700;
  color: var(--lab-accent-2);
}
.edit-stats {
  align-self: center;
  background: transparent;
  color: var(--lab-muted);
  border: 1px solid var(--lab-line);
  padding: 8px 14px;
}
.edit-stats:hover {
  color: var(--lab-text);
  border-color: var(--lab-accent);
}
.block {
  margin-bottom: 40px;
  scroll-margin-top: 16px;
}
.block h2 {
  margin: 0 0 8px;
  font-size: 22px;
}
.head-row {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  margin-bottom: 16px;
}
.lead,
.empty,
.err {
  color: var(--lab-muted);
  line-height: 1.7;
  margin: 0;
  max-width: 720px;
}
.empty {
  margin-top: 8px;
}
.err {
  color: var(--lab-danger);
}
.filters {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
}
.chip {
  background: transparent;
  color: var(--lab-muted);
  border: 1px solid var(--lab-line);
  padding: 6px 14px;
  font-size: 13px;
}
.chip.on,
.chip:hover {
  color: var(--lab-text);
  border-color: var(--lab-accent);
}
.chip.on {
  background: rgba(196, 92, 38, 0.16);
}
.cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  column-gap: 18px;
  row-gap: 28px;
  align-items: stretch;
}
@media (max-width: 720px) {
  .hero {
    padding: 28px 20px 24px;
  }
  .hero-title {
    font-size: 24px;
  }
  .hero-actions,
  .head-row {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>

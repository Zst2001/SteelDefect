<template>
  <div>
    <header class="hero">
      <div class="hero-inner">
        <h1 class="hero-title">钢铁缺陷智能检测平台</h1>
        <p class="hero-subtitle">面向钢铁表面缺陷分类、检测与分割的科研实验平台</p>
        <p class="hero-desc">
          汇集课题组研究成果、钢铁缺陷检测模型及公开数据集，为算法研究、模型对比与实验验证提供统一入口。
        </p>
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
  margin: 0 0 28px;
  color: var(--lab-muted);
  font-size: 14px;
  line-height: 1.75;
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
  gap: 14px;
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

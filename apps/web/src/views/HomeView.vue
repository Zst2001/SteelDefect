<template>
  <div>
    <header class="hero">
      <div class="hero-inner">
        <h1 class="hero-title">智能感知与精密工业检测实验室</h1>
        <p class="hero-subtitle">江西师范大学人工智能学院 · IPPI Lab</p>
        <p class="hero-desc">
          智能感知与精密工业检测实验室（Intelligent Perception and Precision Industrial Inspection Laboratory，简称 IPPI Lab）由江西师范大学与江西博方教育科技集团有限公司联合筹建，依托江西师范大学人工智能学院，由邹翔博士领衔建设，是面向高端智能制造精密质检领域的产学研协同创新平台。共建单位江西博方教育科技集团为高新技术企业、省级专精特新中小企业，组建专职研发团队深度参与科研攻关，提供工程化开发、场景验证与成果转化支撑。实验室团队汇聚高校科研骨干、企业研发人员、硕士研究生及优秀本科生，聚焦工业缺陷检测、工业图像精密分割方向，开展智能感知基础算法研究，攻克高端制造精密质检关键技术瓶颈。相关研究先后获国家自然科学基金（62202211）、江西省科技创新基地计划项目（20242BCC32021）资助，已搭建高性能算力平台与工业仿真实验环境。实验室坚持校企协同、本研衔接育人，在学科竞赛、学术产出、拔尖人才培养方面已取得阶段性成效。实验室现未来将紧扣智能制造国家战略，充分融合高校学科创新优势与企业工程落地能力，致力打造省内领先、国内具有一定影响力的工业视觉科研创新、成果转化与高水平人才培养基地。
        </p>
        <div class="hero-actions">
          <router-link class="btn btn-primary" to="/workbench">进入工作台</router-link>
          <a class="btn btn-secondary" href="#research-works" @click.prevent="scrollTo('research-works')">查看研究成果</a>
        </div>
      </div>
      <figure class="stage">
        <figcaption class="stage-meta">
          <span>预备样例</span>
          <span class="mono">{{
            heroSample ? `NEU-20 · ${heroSample.sample_key} · ${heroSample.width}×${heroSample.height} px` : "NEU-20"
          }}</span>
        </figcaption>
        <div class="stage-frame">
          <i class="corner tl"></i>
          <i class="corner tr"></i>
          <i class="corner bl"></i>
          <i class="corner br"></i>
          <img
            v-if="heroSample"
            :src="heroSample.preview_url"
            :alt="`NEU-20 预备样例 ${heroSample.sample_key}`"
          />
          <div v-else class="stage-empty">钢板表面样例载入后显示于此</div>
        </div>
        <p class="stage-note">热轧钢板表面原图，不是模型输出。</p>
      </figure>
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
type HeroSample = { sample_key: string; width: number; height: number; preview_url: string };
const heroSample = ref<HeroSample | null>(null);

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
    const { data } = await http.get("/demo/samples");
    const items = (data.items ?? []) as HeroSample[];
    heroSample.value = items[0] ?? null;
  } catch {
    heroSample.value = null;
  }
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
  display: grid;
  grid-template-columns: minmax(280px, 1fr) minmax(300px, 1.15fr);
  gap: 36px 40px;
  align-items: stretch;
  margin-bottom: 36px;
}
.hero-inner {
  min-width: 0;
  padding: 8px 0 4px;
}
.hero-title {
  margin: 0 0 12px;
  font-size: 34px;
  font-weight: 700;
  line-height: 1.22;
  letter-spacing: 0.06em;
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
  font-size: 16px;
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
  background: #d45c4e;
  border-color: #d45c4e;
}
.btn-secondary {
  background: transparent;
  border: 1px solid var(--lab-line);
  color: var(--lab-text);
}
.btn-secondary:hover {
  border-color: var(--lab-fiducial);
  color: var(--lab-fiducial);
}
.stage {
  margin: 0;
  min-width: 0;
  background: var(--lab-well);
  border: 1px solid var(--lab-line);
  padding: 16px 18px 18px;
  height: 100%;
  box-sizing: border-box;
}
.stage-meta {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  color: var(--lab-fiducial);
  font-size: 12px;
  letter-spacing: 0.08em;
  margin-bottom: 10px;
}
.mono {
  font-family: var(--lab-font-mono);
  color: var(--lab-muted);
  letter-spacing: 0;
  font-size: 11px;
}
.stage-frame {
  position: relative;
  padding: 10px;
}
.stage-frame img {
  display: block;
  width: 100%;
  aspect-ratio: 1;
  object-fit: cover;
  image-rendering: pixelated;
}
.stage-empty {
  display: grid;
  place-items: center;
  aspect-ratio: 1;
  color: var(--lab-muted);
  font-size: 13px;
  border: 1px dashed var(--lab-line);
}
.corner {
  position: absolute;
  width: 16px;
  height: 16px;
  border-color: var(--lab-fiducial);
  border-style: solid;
  pointer-events: none;
}
.corner.tl {
  top: 0;
  left: 0;
  border-width: 1px 0 0 1px;
}
.corner.tr {
  top: 0;
  right: 0;
  border-width: 1px 1px 0 0;
}
.corner.bl {
  bottom: 0;
  left: 0;
  border-width: 0 0 1px 1px;
}
.corner.br {
  bottom: 0;
  right: 0;
  border-width: 0 1px 1px 0;
}
.stage-note {
  margin: 10px 0 0;
  color: var(--lab-muted);
  font-size: 12px;
  line-height: 1.5;
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
  font-family: var(--lab-font-mono);
  font-size: 32px;
  font-weight: 500;
  color: var(--lab-fiducial);
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
  border-color: var(--lab-fiducial);
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
  border-color: var(--lab-fiducial);
}
.chip.on {
  background: rgba(62, 199, 216, 0.12);
}
.cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  column-gap: 18px;
  row-gap: 28px;
  align-items: stretch;
}
@media (max-width: 900px) {
  .hero {
    grid-template-columns: 1fr;
  }
  .hero-title {
    font-size: 26px;
  }
  .hero-actions,
  .head-row {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>

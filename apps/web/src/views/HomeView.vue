<template>
  <div class="home-page">
    <header class="hero">
      <div class="hero-inner">
        <p class="hero-overline"><span class="lab-symbol"><el-icon><Connection /></el-icon></span>IPPI LAB <span class="overline-divider"></span>INDUSTRIAL VISION</p>
        <p class="hero-subtitle">江西师范大学人工智能学院</p>
        <h1 class="hero-title">智能感知与精密工业检测实验室</h1>
        <p class="hero-desc">{{ labIntroduction }}</p>
        <div class="hero-tags"><span>工业缺陷检测</span><span>工业图像精密分割</span><span>校企协同研究</span></div>
        <div class="hero-actions">
          <router-link class="btn btn-primary" to="/demo"><el-icon><VideoPlay /></el-icon>体验公开演示<el-icon class="action-arrow"><ArrowRight /></el-icon></router-link>
          <router-link class="btn btn-secondary" to="/workbench"><el-icon><Grid /></el-icon>进入工作台</router-link>
        </div>
        <p class="hero-footnote"><el-icon><InfoFilled /></el-icon>公开演示无需登录，仅展示分割效果；实验台需登录。</p>
      </div>
      <figure class="stage">
        <figcaption class="stage-meta">
          <span><el-icon><Picture /></el-icon>钢铁表面 · 公开样例</span>
          <span class="sample-badge">NEU-20</span>
        </figcaption>
        <div class="stage-frame">
          <i class="corner tl"></i><i class="corner tr"></i><i class="corner bl"></i><i class="corner br"></i>
          <div class="sample-image">
            <img v-if="heroSample" :src="heroSample.preview_url" :alt="`NEU-20 预备样例 ${heroSample.sample_key}`" @error="sampleImageFailed = true" :class="{ 'image-failed': sampleImageFailed }" />
            <div v-if="!heroSample || sampleImageFailed" class="stage-empty"><el-icon><Picture /></el-icon><strong>{{ sampleLoading ? '正在加载公开样例' : sampleError || sampleImageFailed ? '样例暂不可用' : '暂无公开样例' }}</strong><span>样例载入后显示原始钢板表面图像</span></div>
          </div>
          <span class="frame-label">ORIGINAL IMAGE</span>
        </div>
        <div class="sample-caption"><span class="mono">{{ heroSample ? `${heroSample.sample_key} · ${heroSample.width} × ${heroSample.height} px` : 'NEU-20' }}</span><span>原始图像</span></div>
        <p class="stage-note"><el-icon><InfoFilled /></el-icon>热轧钢板表面原图，不是模型输出，不报告精度。</p>
      </figure>
    </header>

    <div class="overview-row">
      <section class="stats" aria-label="平台数据统计">
        <div class="stat"><span class="stat-icon"><el-icon><Box /></el-icon></span><div><div class="stat-value">{{ catalogLoaded ? stats.research_models : '—' }}</div><div class="stat-label">研究模型</div></div></div>
        <div class="stat"><span class="stat-icon papers"><el-icon><Document /></el-icon></span><div><div class="stat-value">{{ catalogLoaded ? stats.papers : '—' }}</div><div class="stat-label">论文成果</div></div></div>
        <button v-if="isAdvisor" class="edit-stats" type="button" @click="editingStats = true"><el-icon><Edit /></el-icon>编辑统计</button>
      </section>
      <div class="overview-description"><strong>研究、资源与实验，在此连接</strong><p>浏览课题组成果和公开资源，进入工作台开展钢铁语义分割对照。</p></div>
    </div>

    <nav class="section-nav" aria-label="首页分区导航">
      <a href="#research-works" @click.prevent="scrollTo('research-works')"><el-icon><Document /></el-icon>研究成果</a>
      <a href="#advisor-funds" @click.prevent="scrollTo('advisor-funds')"><el-icon><Collection /></el-icon>科研基金</a>
      <a href="#defect-models" @click.prevent="scrollTo('defect-models')"><el-icon><Box /></el-icon>公开模型</a>
      <a href="#defect-datasets" @click.prevent="scrollTo('defect-datasets')"><el-icon><Files /></el-icon>公开数据集</a>
      <a href="#about-lab" @click.prevent="openAbout()"><el-icon><School /></el-icon>关于实验室</a>
    </nav>

    <div v-if="loadError" class="load-error" role="alert"><el-icon><WarningFilled /></el-icon><div><strong>目录加载失败</strong><p>{{ loadError }}</p></div><el-button @click="reload">重新加载</el-button></div>

    <section id="research-works" class="block">
      <div class="head-row">
        <div>
          <div class="section-heading"><span class="section-icon"><el-icon><Document /></el-icon></span><h2>课题组研究成果</h2><span v-if="catalogLoaded" class="section-count">{{ works.length }} 项</span></div>
          <p class="lead">论文、专利、软件著作权与奖项，记录课题组的研究进展。</p>
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
      <div v-else class="empty"><el-icon><FolderOpened /></el-icon><div><strong>{{ catalogLoading ? '正在加载目录…' : !catalogLoaded && loadError ? '目录暂不可用' : '暂无课题组研究成果' }}</strong><p>{{ catalogLoading ? '稍后即可查看课题组资源。' : !catalogLoaded && loadError ? '请使用上方重新加载按钮重试。' : '成果录入后将在此展示论文、专利与获奖信息。' }}</p></div></div>
    </section>

    <section id="advisor-funds" class="block">
      <div class="head-row">
        <div>
          <div class="section-heading"><span class="section-icon fund"><el-icon><Collection /></el-icon></span><h2>导师科研基金</h2><span v-if="catalogLoaded" class="section-count">{{ funds.length }} 项</span></div>
          <p class="lead">导师主持或参与的科研项目与基金，依据实际立项信息展示。</p>
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
      <div v-else class="empty"><el-icon><FolderOpened /></el-icon><div><strong>{{ catalogLoading ? '正在加载目录…' : !catalogLoaded && loadError ? '目录暂不可用' : '暂无科研基金条目' }}</strong><p>{{ catalogLoading ? '稍后即可查看课题组资源。' : !catalogLoaded && loadError ? '请使用上方重新加载按钮重试。' : '科研项目录入后将在此展示立项与资助信息。' }}</p></div></div>
    </section>

    <section id="defect-models" class="block">
      <div class="head-row">
        <div>
          <div class="section-heading"><span class="section-icon model"><el-icon><Box /></el-icon></span><h2>钢铁缺陷模型</h2><span v-if="catalogLoaded" class="section-count">{{ models.length }} 项公开资源</span></div>
          <p class="lead">公开文献与代码资源目录。条目通过外链查看，不代表本站已接入对应权重。</p>
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
      <div v-else class="empty"><el-icon><FolderOpened /></el-icon><div><strong>{{ catalogLoading ? '正在加载目录…' : !catalogLoaded && loadError ? '目录暂不可用' : '该任务类型暂无模型条目' }}</strong><p>{{ catalogLoading ? '稍后即可查看课题组资源。' : !catalogLoaded && loadError ? '请使用上方重新加载按钮重试。' : '可以切换其他任务类型浏览公开模型资源。' }}</p></div></div>
    </section>

    <section id="defect-datasets" class="block">
      <div class="head-row">
        <div>
          <div class="section-heading"><span class="section-icon dataset"><el-icon><Files /></el-icon></span><h2>钢铁缺陷数据集</h2><span v-if="catalogLoaded" class="section-count">{{ datasets.length }} 项公开资源</span></div>
          <p class="lead">浏览分类、检测与分割数据资源；规模、类别与访问方式以原始来源为准。</p>
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
      <div v-else class="empty"><el-icon><FolderOpened /></el-icon><div><strong>{{ catalogLoading ? '正在加载目录…' : !catalogLoaded && loadError ? '目录暂不可用' : '该任务类型暂无数据集条目' }}</strong><p>{{ catalogLoading ? '稍后即可查看课题组资源。' : !catalogLoaded && loadError ? '请使用上方重新加载按钮重试。' : '可以切换其他任务类型浏览公开数据资源。' }}</p></div></div>
    </section>

    <details id="about-lab" ref="aboutEl" class="about-lab">
      <summary><span class="section-icon"><el-icon><School /></el-icon></span><span><strong>关于实验室</strong><span>IPPI Lab · 校企协同的工业视觉研究平台</span></span><el-icon class="about-chevron"><ArrowDown /></el-icon></summary>
      <div class="about-content"><h2>智能感知与精密工业检测实验室</h2><p class="lab-full-introduction">{{ labIntroduction }}</p></div>
    </details>

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
  ArrowDown, ArrowRight, Box, Collection, Connection, Document, Edit, Files,
  FolderOpened, Grid, InfoFilled, Picture, School, VideoPlay, WarningFilled,
} from "@element-plus/icons-vue";
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

const labIntroduction = "智能感知与精密工业检测实验室（Intelligent Perception and Precision Industrial Inspection Laboratory，简称 IPPI Lab）由江西师范大学与江西博方教育科技集团有限公司联合筹建，依托江西师范大学人工智能学院，由邹翔博士领衔建设，是面向高端智能制造精密质检领域的产学研协同创新平台。共建单位江西博方教育科技集团为高新技术企业、省级专精特新中小企业，组建专职研发团队深度参与科研攻关，提供工程化开发、场景验证与成果转化支撑。实验室团队汇聚高校科研骨干、企业研发人员、硕士研究生及优秀本科生，聚焦工业缺陷检测、工业图像精密分割方向，开展智能感知基础算法研究，攻克高端制造精密质检关键技术瓶颈。相关研究先后获国家自然科学基金（62202211）、江西省科技创新基地计划项目（20242BCC32021）资助，已搭建高性能算力平台与工业仿真实验环境。实验室坚持校企协同、本研衔接育人，在学科竞赛、学术产出、拔尖人才培养方面已取得阶段性成效。实验室现未来将紧扣智能制造国家战略，充分融合高校学科创新优势与企业工程落地能力，致力打造省内领先、国内具有一定影响力的工业视觉科研创新、成果转化与高水平人才培养基地。";

const stats = ref<CatalogStats>({ research_models: 0, papers: 0, updated_at: "" });
const models = ref<CatalogModel[]>([]);
const datasets = ref<CatalogDataset[]>([]);
const works = ref<CatalogWork[]>([]);
const funds = ref<CatalogFund[]>([]);
const isAdvisor = ref(false);
const loadError = ref("");
const catalogLoading = ref(true);
const catalogLoaded = ref(false);
const aboutEl = ref<HTMLDetailsElement | null>(null);
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
const sampleLoading = ref(true);
const sampleError = ref(false);
const sampleImageFailed = ref(false);

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

function openAbout() {
  if (aboutEl.value) aboutEl.value.open = true;
  scrollTo("about-lab");
}

async function reload() {
  loadError.value = "";
  catalogLoading.value = true;
  try {
    const data = await fetchCatalog();
    stats.value = data.stats;
    models.value = data.models;
    datasets.value = data.datasets;
    works.value = data.works ?? [];
    funds.value = data.funds ?? [];
    catalogLoaded.value = true;
  } catch (err) {
    loadError.value = formatError(err);
  } finally {
    catalogLoading.value = false;
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
    sampleError.value = true;
  } finally {
    sampleLoading.value = false;
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
.home-page {
  --home-blue: #2f6fd8;
  --home-ink: #193550;
  --home-muted: #415770;
  --home-line: #d6e1ef;
  --home-soft: #f3f7fd;
  color: var(--home-ink);
}
.hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(280px, 340px);
  align-items: start;
  gap: 32px;
  padding: 34px 36px;
  background: linear-gradient(115deg, #fff 34%, #f1f6ff);
  border: 1px solid var(--home-line);
  border-radius: 18px;
  box-shadow: 0 8px 30px #28528b04;
}
.hero-inner {
  min-width: 0;
}
.hero-overline {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 0 0 25px;
  color: #41678f;
  font-size: 14px;
  font-weight: 600;
  letter-spacing: .06em;
}
.lab-symbol {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  background: #e7f0ff;
  border-radius: 9px;
  color: var(--home-blue);
  font-size: 22px;
}
.overline-divider {
  width: 1px;
  height: 13px;
  background: #cbd9ec;
  margin: 0 2px;
}
.hero-title {
  margin: 0 0 18px;
  font-size: clamp(30px, 2.5vw, 42px);
  font-weight: 700;
  line-height: 1.35;
  letter-spacing: -.035em;
  color: #18385e;
}
.hero-subtitle {
  margin: 0 0 12px;
  font-size: 16px;
  color: var(--home-blue);
  letter-spacing: .06em;
}
.hero-desc {
  margin: 0;
  color: var(--home-muted);
  font-size: 17px;
  line-height: 1.95;
  overflow-wrap: anywhere;
  text-align: justify;
}
.hero-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 20px 0 28px;
}
.hero-tags span {
  padding: 5px 9px;
  color: #365e90;
  font-size: 14px;
  background: #f1f6fe;
  border: 1px solid #e3ecfa;
  border-radius: 5px;
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
  gap: 8px;
  min-height: 43px;
  padding: 10px 18px;
  border: 1px solid transparent;
  border-radius: 7px;
  font-size: 16px;
  font-weight: 500;
  text-decoration: none;
  box-sizing: border-box;
}
.btn .el-icon {
  font-size: 19px;
}
.btn-primary {
  color: #fff;
  border-color: var(--home-blue);
  background: var(--home-blue);
  box-shadow: 0 4px 9px #2f6fd81a;
}
.btn-primary:hover {
  background: #205ec6;
  border-color: #205ec6;
}
.btn-primary .action-arrow {
  margin-left: 5px;
  font-size: 15px;
}
.btn-secondary {
  color: #365a85;
  background: #fff;
  border-color: #ceddf0;
}
.btn-secondary:hover {
  border-color: #8aafe5;
  background: #f5f9ff;
}
.hero-footnote {
  display: flex;
  align-items: start;
  gap: 6px;
  margin: 15px 0 0;
  font-size: 14px;
  line-height: 1.7;
  color: #536880;
}
.hero-footnote .el-icon {
  flex: none;
  margin-top: 3px;
}
.stage {
  align-self: center;
  margin: 0;
  padding: 16px;
  min-width: 0;
  background: #fff;
  border: 1px solid #dce6f4;
  border-radius: 12px;
  box-shadow: 0 12px 24px #28528b09;
}
.stage-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  padding: 1px 1px 14px;
  font-size: 14px;
  color: #385b83;
}
.stage-meta > span:first-child {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.stage-meta .el-icon {
  font-size: 18px;
  color: #3d70ae;
}
.sample-badge {
  border: 1px solid #dfe9f8;
  border-radius: 4px;
  padding: 3px 7px;
  background: #f4f8ff;
  color: #40658e;
  font: 14px var(--lab-font-mono);
}
.stage-frame {
  position: relative;
  display: grid;
  place-items: center;
  min-height: 228px;
  padding: 22px 22px 31px;
  background-color: #243950;
  background-image: linear-gradient(#ffffff04 1px, transparent 1px), linear-gradient(90deg, #ffffff04 1px, transparent 1px);
  background-size: 22px 22px;
  border-radius: 6px;
  overflow: hidden;
}
.sample-image {
  display: grid;
  place-items: center;
  width: min(100%, 220px);
  aspect-ratio: 1;
  min-width: 0;
}
.sample-image img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  display: block;
  box-shadow: 0 8px 22px #11233625;
}
.sample-image img.image-failed {
  display: none;
}
.stage-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  gap: 12px;
  width: 100%;
  height: 100%;
  text-align: center;
  color: #a8bad0;
  border: 1px dashed #7891ad55;
  border-radius: 6px;
  box-sizing: border-box;
  padding: 16px;
}
.stage-empty > .el-icon {
  font-size: 38px;
  color: #8cadd3;
}
.stage-empty strong {
  font-size: 16px;
  font-weight: 500;
}
.stage-empty span {
  font-size: 14px;
  line-height: 1.8;
  color: #b5c9e1;
}
.frame-label {
  position: absolute;
  left: 13px;
  bottom: 10px;
  font: 12px var(--lab-font-mono);
  letter-spacing: .1em;
  color: #99b5d4;
}
.corner {
  position: absolute;
  width: 13px;
  height: 13px;
  border-color: #79a2d6;
  border-style: solid;
  pointer-events: none;
}
.corner.tl { top: 10px; left: 10px; border-width: 1px 0 0 1px; }
.corner.tr { top: 10px; right: 10px; border-width: 1px 1px 0 0; }
.corner.bl { bottom: 10px; left: 10px; border-width: 0 0 1px 1px; }
.corner.br { bottom: 10px; right: 10px; border-width: 0 1px 1px 0; }
.sample-caption {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  padding-top: 12px;
  font-size: 14px;
  color: #4b6687;
}
.mono {
  min-width: 0;
  overflow-wrap: anywhere;
  font-family: var(--lab-font-mono);
}
.stage-note {
  display: flex;
  align-items: start;
  gap: 5px;
  color: #536a85;
  font-size: 14px;
  line-height: 1.7;
  margin: 9px 0 0;
}
.stage-note .el-icon {
  flex: none;
  margin-top: 3px;
}
.overview-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 24px;
  padding: 22px 7px 25px;
}
.stats {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 28px;
}
.stat {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 135px;
}
.stat + .stat {
  padding-left: 28px;
  border-left: 1px solid #dce5f0;
}
.stat-icon {
  display: grid;
  place-items: center;
  width: 42px;
  height: 42px;
  border-radius: 12px;
  color: #396cb5;
  background: #edf4ff;
  border: 1px solid #e1eaf7;
  font-size: 24px;
}
.stat-icon.papers {
  color: #68589f;
  background: #f3f1fb;
  border-color: #e9e5f6;
}
.stat-value {
  font-family: var(--lab-font-mono);
  font-size: 29px;
  color: #314f76;
  line-height: 1.15;
}
.stat-label {
  color: #526b89;
  font-size: 14px;
  margin-top: 5px;
}
.edit-stats {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  background: #fff;
  color: #40648f;
  border: 1px solid #dce6f3;
  border-radius: 6px;
  padding: 7px 10px;
  font: inherit;
  font-size: 14px;
  cursor: pointer;
}
.overview-description {
  max-width: 430px;
  border-left: 2px solid #c8d9f1;
  padding-left: 15px;
}
.overview-description strong {
  font-size: 16px;
  font-weight: 500;
  color: #385577;
}
.overview-description p {
  margin: 6px 0 0;
  color: #536880;
  font-size: 14px;
  line-height: 1.8;
}
.section-nav {
  display: flex;
  gap: 7px;
  align-items: center;
  flex-wrap: wrap;
  padding: 8px;
  border: 1px solid var(--home-line);
  background: #fff;
  border-radius: 10px;
  margin-bottom: 32px;
}
.section-nav a {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 9px 15px;
  color: #435f82;
  font-size: 15px;
  text-decoration: none;
  border-radius: 6px;
}
.section-nav a:hover {
  color: var(--home-blue);
  background: #f0f6ff;
}
.section-nav a .el-icon {
  font-size: 18px;
  color: #4776b0;
}
.block {
  margin-bottom: 36px;
  scroll-margin-top: 24px;
}
.head-row {
  display: flex;
  justify-content: space-between;
  gap: 18px;
  align-items: center;
  margin-bottom: 20px;
}
.head-row > div {
  min-width: 0;
}
.head-row > .el-button {
  flex: none;
}
.section-heading {
  display: flex;
  align-items: center;
  gap: 11px;
}
.section-icon {
  display: grid;
  place-items: center;
  width: 35px;
  height: 35px;
  flex: none;
  background: #eaf2ff;
  border: 1px solid #dfe9f8;
  color: #3266a8;
  border-radius: 9px;
  font-size: 21px;
}
.section-icon.fund {
  color: #26745f;
  background: #edf7f3;
  border-color: #dfede6;
}
.section-icon.model {
  color: #635099;
  background: #f2effa;
  border-color: #e9e2f5;
}
.section-icon.dataset {
  color: #246e85;
  background: #edf6f9;
  border-color: #deedf3;
}
.section-heading h2 {
  margin: 0;
  font-size: 22px;
  font-weight: 600;
  letter-spacing: -.02em;
  color: #193b61;
}
.section-count {
  padding: 3px 7px;
  border: 1px solid #e0e8f4;
  background: #f7f9fd;
  color: #536a86;
  border-radius: 5px;
  font-size: 14px;
  white-space: nowrap;
}
.lead {
  color: #4b6584;
  line-height: 1.8;
  margin: 9px 0 0 46px;
  max-width: 840px;
  font-size: 16px;
}
.empty {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 19px;
  border: 1px solid var(--home-line);
  border-radius: 11px;
  padding: 32px 22px;
  background: #fff;
  min-height: 128px;
  box-sizing: border-box;
}
.empty > .el-icon {
  color: #bbccdf;
  font-size: 39px;
}
.empty strong {
  font-size: 16px;
  font-weight: 500;
  color: #42607f;
}
.empty p {
  font-size: 14px;
  color: #5b708a;
  margin: 8px 0 0;
  line-height: 1.8;
}
.filters {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
  margin-bottom: 17px;
}
.chip {
  background: #fff;
  color: #496486;
  border: 1px solid #e0e8f3;
  border-radius: 6px;
  padding: 6px 15px;
  font: inherit;
  font-size: 14px;
  cursor: pointer;
}
.chip:hover {
  color: #245bb0;
  border-color: #aac4e9;
}
.chip.on {
  background: #eaf2ff;
  border-color: #c8dcf8;
  color: #205eb5;
}
.cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 300px), 1fr));
  gap: 17px;
  align-items: stretch;
}
.load-error {
  display: flex;
  align-items: center;
  gap: 12px;
  border: 1px solid #edcaca;
  background: #fff7f7;
  border-radius: 10px;
  padding: 16px 18px;
  margin-bottom: 24px;
  color: #9b3636;
}
.load-error > .el-icon {
  flex: none;
  font-size: 22px;
}
.load-error strong {
  font-size: 16px;
  font-weight: 500;
}
.load-error p {
  font-size: 14px;
  line-height: 1.7;
  margin: 5px 0 0;
  overflow-wrap: anywhere;
}
.load-error > .el-button {
  margin-left: auto;
  flex: none;
}
.about-lab {
  border: 1px solid var(--home-line);
  border-radius: 12px;
  background: #fff;
  overflow: hidden;
  scroll-margin-top: 24px;
}
.about-lab > summary {
  display: flex;
  align-items: center;
  gap: 13px;
  padding: 20px 23px;
  cursor: pointer;
  list-style: none;
}
.about-lab > summary::-webkit-details-marker {
  display: none;
}
.about-lab summary strong {
  display: block;
  color: #2a507c;
  font-size: 17px;
  font-weight: 500;
}
.about-lab summary strong + span {
  display: block;
  margin-top: 6px;
  color: #506b8b;
  font-size: 14px;
}
.about-chevron {
  margin-left: auto;
  color: #5476a0;
  flex: none;
}
.about-lab[open] .about-chevron {
  transform: rotate(180deg);
}
.about-content {
  padding: 25px 30px 28px;
  border-top: 1px solid #e9eef5;
  background: #fcfdff;
}
.about-content h2 {
  color: #345a85;
  font-size: 19px;
  font-weight: 600;
  margin: 0 0 14px;
}
.lab-full-introduction {
  font-size: 16px;
  color: #435c78;
  line-height: 2.1;
  margin: 0;
}
button:focus-visible, a:focus-visible, summary:focus-visible {
  outline: 2px solid #3979ef;
  outline-offset: 3px;
}
@media (max-width: 1300px) {
  .hero { grid-template-columns: minmax(0, 1fr); }
  .stage { margin: 0; max-width: 560px; width: 100%; box-sizing: border-box; justify-self: center; }
  .hero { padding: 27px; gap: 28px; }
  .hero-title { font-size: 33px; }
  .hero-overline { font-size: 13px; gap: 8px; }
  .overview-description { display: none; }
}
@media (max-width: 850px) {
  .hero { grid-template-columns: 1fr; }
  .hero-inner { padding: 4px; }
  .hero-title { font-size: 36px; }
  .hero-overline { margin-bottom: 19px; }
  .stage { max-width: 560px; }
  .stage-frame { min-height: 210px; }
  .sample-image { width: min(100%, 220px); }
  .section-nav { gap: 3px; }
  .section-nav a { padding: 8px 11px; }
}
@media (max-width: 540px) {
  .hero { padding: 21px 17px; border-radius: 13px; gap: 25px; }
  .hero-title { font-size: 30px; }
  .hero-subtitle { font-size: 15px; }
  .hero-overline { font-size: 12px; gap: 7px; }
  .hero-tags { gap: 6px; margin: 16px 0 22px; }
  .hero-tags span { font-size: 13px; padding: 5px 7px; }
  .hero-actions { gap: 9px; }
  .btn { flex: 1; padding: 10px 9px; font-size: 15px; gap: 5px; }
  .btn-primary .action-arrow { display: none; }
  .hero-footnote { font-size: 14px; }
  .stage { padding: 12px; }
  .stage-frame { min-height: 190px; padding: 20px 20px 30px; }
  .sample-image { width: min(100%, 210px); }
  .stage-meta { font-size: 14px; }
  .sample-caption { font-size: 13px; }
  .overview-row { padding: 22px 3px; }
  .stats { gap: 18px; }
  .stat { min-width: 110px; gap: 10px; }
  .stat + .stat { padding-left: 18px; }
  .stat-icon { width: 34px; height: 37px; font-size: 21px; border-radius: 9px; }
  .stat-value { font-size: 26px; }
  .section-nav { padding: 6px; margin-bottom: 27px; }
  .section-nav a { font-size: 14px; padding: 8px 9px; gap: 5px; }
  .section-nav a .el-icon { font-size: 16px; }
  .head-row { align-items: start; gap: 12px; flex-wrap: wrap; }
  .section-heading { gap: 8px; flex-wrap: wrap; }
  .section-heading h2 { font-size: 20px; }
  .section-count { font-size: 13px; }
  .section-icon { width: 30px; height: 32px; font-size: 19px; }
  .lead { margin-left: 0; font-size: 15px; }
  .empty { justify-content: start; padding: 24px 18px; gap: 15px; }
  .empty > .el-icon { font-size: 32px; }
  .about-lab > summary { padding: 17px; gap: 10px; }
  .about-lab summary strong + span { font-size: 13px; line-height: 1.7; }
  .about-content { padding: 21px 18px; }
  .load-error { align-items: start; flex-wrap: wrap; }
}
</style>

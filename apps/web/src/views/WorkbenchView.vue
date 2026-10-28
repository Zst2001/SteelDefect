<template>
  <div class="dashboard">
    <header class="head dashboard-head">
      <div>
        <h1>工作台</h1>
        <p>钢铁表面缺陷分割实验，从图像对照到结果分析。</p>
      </div>
      <div class="head-actions">
        <router-link class="el-button el-button--primary" to="/inspect/steel/segmentation"><el-icon><Plus /></el-icon>新建分割对照</router-link>
        <router-link class="el-button" to="/models/import"><el-icon><UploadFilled /></el-icon>导入模型</router-link>
      </div>
    </header>
    <el-alert v-if="loadError" :title="loadError" type="error" :closable="false" show-icon>
      <el-button link @click="loadDashboard">重新加载</el-button>
    </el-alert>
    <el-alert v-for="notice in notices" :key="notice.id" :title="notice.text" type="info" show-icon class="notice" />
    <div v-if="loading" class="wb-panel">
      <el-skeleton :rows="5" animated aria-label="正在读取工作台" />
    </div>
    <template v-else-if="!loadError">
      <div class="summary-grid">
        <div class="summary-card blue">
          <span class="summary-icon"><el-icon><List /></el-icon></span>
          <div><span>近期活动任务</span><strong>{{ active.length }}<small>项</small></strong><small>最近 20 条中的排队与运行项</small></div>
        </div>
        <div class="summary-card green">
          <span class="summary-icon"><el-icon><Clock /></el-icon></span>
          <div><span>最近任务</span><strong>{{ tasks.length }}<small>条</small></strong><small>最近记录，最多展示 10 条</small></div>
        </div>
        <div class="summary-card violet">
          <span class="summary-icon"><el-icon><Box /></el-icon></span>
          <div><span>最近导入</span><strong>{{ models.length }}<small>个</small></strong><small>学生模型，最多展示 8 条</small></div>
        </div>
      </div>
      <div class="dashboard-columns">
        <div class="wb-stack">
          <section class="wb-panel entry-panel">
            <div class="wb-panel-heading">
              <div class="wb-panel-title"><span class="wb-section-icon"><Grid /></span><h2>开始实验</h2></div>
              <router-link to="/models/scatter" class="more-link">性能散点图<el-icon><ArrowRight /></el-icon></router-link>
            </div>
            <div class="shortcut-grid">
              <router-link v-for="item in shortcuts" :key="item.to" :to="item.to" class="shortcut" :class="item.color">
                <span class="shortcut-icon"><el-icon><component :is="item.icon" /></el-icon></span>
                <div><h3>{{ item.title }}</h3><p>{{ item.text }}</p></div><el-icon class="shortcut-arrow"><ArrowRight /></el-icon>
              </router-link>
            </div>
          </section>
          <section class="wb-panel recent-panel">
            <div class="wb-panel-heading">
              <div class="wb-panel-title"><span class="wb-section-icon"><Document /></span><h2>最近任务</h2></div>
              <router-link to="/records" class="more-link">全部记录<el-icon><ArrowRight /></el-icon></router-link>
            </div>
            <el-table v-if="tasks.length" :data="tasks">
              <el-table-column label="实验任务" min-width="170">
                <template #default="{ row }"><div class="task-cell" :title="row.id"><span class="task-symbol" :class="row.type"><el-icon><component :is="row.type === 'eval' ? DocumentChecked : row.type === 'demo' ? VideoPlay : Aim" /></el-icon></span><strong>{{ row.type_label }}</strong></div></template>
              </el-table-column>
              <el-table-column label="状态" width="100"><template #default="{ row }"><TaskStatus :status="row.status" /></template></el-table-column>
              <el-table-column label="指标条件" min-width="145"><template #default="{ row }"><span class="metric-note">{{ row.type === 'demo' ? '演示 · 不计算精度' : row.has_gt ? '有配对 GT' : '无 GT · 仅可视化' }}</span></template></el-table-column>
              <el-table-column label="操作" min-width="155">
                <template #default="{ row }"><div class="table-actions"><router-link class="text-link" :to="taskHref(row)">查看<el-icon><ArrowRight /></el-icon></router-link><el-button v-if="row.bundle_ready" link type="primary" @click="downloadBundle(row)">图层包</el-button><span v-else-if="['success', 'partial_success'].includes(row.status)" class="unavailable" :title="row.bundle_unavailable_reason">无图层包</span></div></template>
              </el-table-column>
            </el-table>
            <div v-else class="dashboard-empty"><span class="empty-icon"><el-icon><Document /></el-icon></span><strong>还没有任务，从新建分割对照开始。</strong><p>上传原图后，可与内置或已通过检查的学生模型进行对照。</p><router-link to="/inspect/steel/segmentation">创建第一次对照<el-icon><ArrowRight /></el-icon></router-link></div>
          </section>
        </div>
        <div class="wb-stack dashboard-rail">
          <section class="wb-panel attention-panel" :class="{ 'has-failures': failed.length }">
            <div class="wb-panel-heading"><div class="wb-panel-title"><span class="rail-icon amber"><el-icon><Warning /></el-icon></span><h2>需要处理</h2></div><span v-if="failed.length" class="count-badge">{{ failed.length }} 项</span></div>
            <p v-if="!failed.length" class="empty"><el-icon><CircleCheck /></el-icon>近期没有失败任务。</p>
            <router-link v-for="row in failed" :key="row.id" class="attention-item" :to="taskHref(row)"><strong>{{ row.type_label }}未完成</strong><p>{{ row.error_summary || '打开详情查看失败原因' }}</p><span>查看任务详情<el-icon><ArrowRight /></el-icon></span></router-link>
            <div class="rail-footnote">最近 20 条任务内，最多展示 8 条失败项。</div>
          </section>
          <section class="wb-panel">
            <div class="wb-panel-heading"><div class="wb-panel-title"><span class="rail-icon blue"><el-icon><Clock /></el-icon></span><h2>近期活动</h2></div><span class="section-hint">个人任务</span></div>
            <p v-if="!active.length" class="empty">暂无排队或运行中的任务。</p>
            <router-link v-for="row in active" :key="row.id" class="activity" :to="taskHref(row)"><div><strong>{{ row.type_label }}</strong><TaskStatus :status="row.status" /></div><code>{{ row.id.slice(0, 12) }}</code><span class="activity-open">打开<el-icon><ArrowRight /></el-icon></span></router-link>
          </section>
          <section class="wb-panel">
            <div class="wb-panel-heading"><div class="wb-panel-title"><span class="rail-icon green"><el-icon><Box /></el-icon></span><h2>最近导入</h2></div><router-link to="/models" class="more-link">模型库<el-icon><ArrowRight /></el-icon></router-link></div>
            <p v-if="!models.length" class="empty">导入训练好的源码与权重后，在这里查看模型检查状态。</p>
            <router-link v-for="model in models" :key="model.id" class="model-item" :to="`/models/${model.id}`"><span class="model-icon"><el-icon><Cpu /></el-icon></span><div><strong>{{ model.name }}</strong><p>{{ modelStatusLabel(model.status) }}<template v-if="model.fail_stage"> · {{ model.fail_stage }}</template></p></div><el-icon><ArrowRight /></el-icon></router-link>
            <router-link class="import-link" to="/models/import"><el-icon><Plus /></el-icon>导入新模型</router-link>
          </section>
        </div>
      </div>
      <div class="protocol-strip"><el-icon><InfoFilled /></el-icon><p><strong>实验口径</strong>公开演示不计算精度；对照需完整配对 GT 才报告本批指标；正式评测固定 NEU-20。<span>本站不做训练。</span></p></div>
    </template>
  </div>
</template>

<script setup lang="ts">
import TaskStatus from "../components/TaskStatus.vue";
import { Aim, UploadFilled, Cpu, DocumentChecked, ChatDotRound, Plus, List, Document, Box, Grid, ArrowRight, VideoPlay, Warning, CircleCheck, Clock, InfoFilled } from "@element-plus/icons-vue";
import { onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import { formatError, http } from "../api/http";
import { downloadAuthFile, modelStatusLabel, taskPath } from "../api/labels";

type DashTask = {
  id: string;
  type: string;
  type_label: string;
  status: string;
  has_gt: boolean;
  error_summary: string | null;
  bundle_ready: boolean;
  bundle_unavailable_reason?: string | null;
};
type DashModel = { id: string; name: string; status: string; fail_stage: string | null };
type Notice = { id: string; text: string };

const loading = ref(true);
const loadError = ref("");
const shortcuts = [
  { title: "缺陷分割", to: "/inspect/steel/segmentation", icon: Aim, color: "blue", text: "原图与模型预测对照；完整配对 GT 才计算本批指标。", action: "新建对照" },
  { title: "正式评测", to: "/eval/new", icon: DocumentChecked, color: "violet", text: "固定 NEU-20 协议，全量 20 张计分。", action: "提交评测" },
  { title: "模型测评", to: "/models/perf", icon: Cpu, color: "green", text: "测量参数量与 CPU 前向性能，不计算测试集精度。", action: "查看性能" },
  { title: "科研助手", to: "/assistant", icon: ChatDotRound, color: "blue", text: "选择学术、分割或模型专科，基于证据分析。", action: "开始对话" },
];
const notices = ref<Notice[]>([]);
const tasks = ref<DashTask[]>([]);
const active = ref<DashTask[]>([]);
const failed = ref<DashTask[]>([]);
const models = ref<DashModel[]>([]);

function taskHref(row: DashTask) {
  return taskPath(row.type, row.id);
}

async function downloadBundle(row: DashTask) {
  try {
    const path = row.type === "demo" ? `/demo/tasks/${row.id}/bundle` : `/tasks/${row.id}/bundle`;
    await downloadAuthFile(path, `${row.id}_bundle.zip`);
  } catch (error) {
    ElMessage.error(formatError(error));
  }
}

async function loadDashboard() {
  loading.value = true;
  loadError.value = "";
  try {
    const { data } = await http.get("/me/dashboard");
    notices.value = data.notices ?? [];
    tasks.value = data.recent_tasks ?? [];
    active.value = data.active_tasks ?? [];
    failed.value = data.failed_tasks ?? [];
    models.value = data.recent_models ?? [];
  } catch (error) {
    loadError.value = formatError(error);
  } finally {
    loading.value = false;
  }
}
onMounted(loadDashboard);
</script>

<style scoped>
.dashboard-head { display: flex; justify-content: space-between; gap: 20px; align-items: center; }
.dashboard-head > div:first-child { display: flex; align-items: center; gap: 18px; }
.dashboard-head h1 { margin: 0; }
.head-actions { display: flex; gap: 10px; flex-wrap: wrap; flex: none; }
.head-actions a { text-decoration: none; margin: 0; min-height: 38px; gap: 7px; }
.head p { margin: 0; color: var(--lab-muted); }
.notice { margin: 16px 0; }
.summary-grid { display: grid; grid-template-columns: repeat(3,minmax(0,1fr)); gap: 18px; margin: 0 0 22px; }
.summary-card { display: flex; align-items: center; gap: 16px; position: relative; padding: 18px 22px; background: white; border: 1px solid #e8eef7; border-radius: 12px; box-shadow: 0 3px 14px #233f6605; overflow: hidden; }
.summary-icon { display: grid; place-items: center; width: 56px; height: 56px; border-radius: 17px; font-size: 29px; background: var(--icon-bg); color: var(--icon-fg); flex: none; }
.blue { --icon-bg: #eaf2ff; --icon-fg: #3075ed; }
.violet { --icon-bg: #f1edff; --icon-fg: #8260dc; }
.green { --icon-bg: #e5f7f0; --icon-fg: #24a886; }
.summary-card > div { display: grid; gap: 5px; z-index: 1; }
.summary-card div > span { color: #536981; font-size: 16px; }
.summary-card strong { color: #142238; font-size: 30px; line-height: 1.1; font-weight: 700; font-family: "Segoe UI", sans-serif; display: flex; align-items: baseline; gap: 8px; }
.summary-card small { color: #526781; font-size: 14px; font-weight: 400; }
.summary-card strong small { font-size: 14px; }
.dashboard-columns { display: grid; grid-template-columns: minmax(0,1.8fr) minmax(300px,1fr); gap: 20px; align-items: start; }
.shortcut-grid { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 13px; }
.shortcut { display: grid; grid-template-columns: 48px minmax(0,1fr) 16px; align-items: center; gap: 14px; border: 1px solid #e4ebf5; border-radius: 10px; padding: 16px; text-decoration: none; transition: border-color .15s,box-shadow .15s; min-width: 0; }
.shortcut:hover { border-color: #9cbcf6; box-shadow: 0 4px 12px #246bfd0b; }
.shortcut-icon { display: grid; place-items: center; background: var(--icon-bg); color: var(--icon-fg); border-radius: 11px; flex: none; width: 48px; height: 52px; font-size: 29px; }
.shortcut h3 { margin: 0 0 7px; font-size: 18px; }
.shortcut p { margin: 0; font-size: 16px; color: #526781; line-height: 1.7; }
.shortcut-arrow { color: #7b9ac5; font-size: 17px; }
.section-hint { color: #657a96; font-size: 14px; }
.more-link { display: inline-flex; align-items: center; gap: 7px; white-space: nowrap; font-size: 14px !important; }
.task-cell { display: flex; align-items: center; gap: 10px; min-width: 0; }
.task-symbol { display: grid; place-items: center; flex: none; width: 34px; height: 36px; border: 1px solid #dfe9fa; border-radius: 6px; background: #eef4ff; color: #4580df; font-size: 20px; }
.task-symbol.eval { background: #f3effd; color: #8b6fca; border-color: #ebe3f8; }.task-symbol.demo { background: #eaf8f3; color: #32a989; border-color: #daf0e8; }
.task-cell strong { display: block; font-size: 16px; font-weight: 500; }
.metric-note { color: #526781; font-size: 15px; }
.table-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; }
.text-link { color: #3378ed; text-decoration: none; font-size: 14px; display: inline-flex; align-items: center; gap: 5px; }
.unavailable { color: #657a96; font-size: 14px; }
.dashboard-rail .wb-panel { padding: 19px 20px; }
.dashboard-rail h2 { font-size: 18px; }
.dashboard-rail .wb-panel-heading { margin-bottom: 13px; gap: 8px; }
.dashboard-rail .wb-panel-title { gap: 9px; }
.rail-icon { display: grid; place-items: center; width: 30px; height: 30px; border-radius: 8px; font-size: 20px; background: var(--icon-bg); color: var(--icon-fg); flex: none; }
.amber { --icon-bg: #fff1d9; --icon-fg: #d59729; }
.attention-panel.has-failures { background: linear-gradient(140deg, #fffcf6, #fff); border-color: #f1e6d1; }
.count-badge { background: #fff1d9; border-radius: 5px; padding: 3px 7px; color: #a87c2d; font-size: 14px; }
.attention-item { display: block; text-decoration: none; border-top: 1px solid #f0e7d7; padding: 14px 0 6px; }
.attention-item strong { font-size: 16px; color: #715329; }
.attention-item p { font-size: 15px; color: #8a785a; margin: 8px 0 12px; line-height: 1.8; overflow-wrap: anywhere; }
.attention-item > span { display: flex; align-items: center; gap: 6px; font-size: 14px; color: #a6803b; }
.rail-footnote { font-size: 14px; color: #9a917f; padding-top: 10px; line-height: 1.65; }
.activity { display: block; position: relative; padding: 14px 0; border-top: 1px solid #edf1f7; text-decoration: none; }
.activity > div { display: flex; justify-content: space-between; gap: 8px; align-items: center; }
.activity strong { font-size: 16px; font-weight: 500; }
.activity code { font-size: 14px; color: #8a99ac; line-height: 1.8; overflow-wrap: anywhere; margin-top: 7px; display: block; }
.activity-open { display: flex; align-items: center; gap: 4px; float: right; margin-top: -18px; font-size: 14px; color: #6e8db8; }
.model-item { display: flex; align-items: center; gap: 11px; padding: 14px 0; border-top: 1px solid #edf1f7; text-decoration: none; }
.model-item > div { flex: 1; min-width: 0; }.model-item > .el-icon { color: #9bb0cb; font-size: 15px; }
.model-icon { display: grid; place-items: center; width: 39px; height: 41px; flex: none; background: #ecf6f2; color: #50a88d; border: 1px solid #dceee6; border-radius: 7px; font-size: 24px; }
.model-item strong { display: block; font-size: 16px; font-weight: 500; overflow-wrap: anywhere; }
.model-item p { color: #526781; margin: 5px 0 0; font-size: 14px; }
.import-link { display: flex; justify-content: center; align-items: center; gap: 6px; padding: 10px; background: #f6f9fe; border: 1px solid #e7eef9; color: #5b7eab; font-size: 14px; border-radius: 6px; text-decoration: none; margin-top: 6px; }
.empty { font-size: 15px; color: #526781; line-height: 1.8; display: flex; align-items: center; gap: 8px; }
.dashboard-empty { display: flex; flex-direction: column; align-items: center; text-align: center; padding: 32px 14px; }
.empty-icon { display: grid; place-items: center; width: 54px; height: 54px; border: 1px solid #e4ecfa; border-radius: 15px; background: #f4f8ff; color: #7f9ac4; font-size: 28px; margin-bottom: 18px; }
.dashboard-empty strong { font-size: 16px; font-weight: 500; }.dashboard-empty p { font-size: 14px; color: #526781; line-height: 1.8; }.dashboard-empty a { display: inline-flex; align-items: center; gap: 6px; font-size: 15px; color: #3479ed; margin-top: 10px; text-decoration: none; }
.protocol-strip { display: flex; align-items: center; gap: 10px; color: #6882a5; background: #eaf1fd; border: 1px solid #dfe9fb; border-radius: 8px; padding: 11px 15px; margin-top: 20px; font-size: 14px; }
.protocol-strip > .el-icon { color: #5688cf; font-size: 19px; flex: none; }.protocol-strip p { margin: 0; line-height: 1.8; }.protocol-strip strong { font-weight: 500; color: #4f6e97; margin-right: 12px; }.protocol-strip p > span { margin-left: 10px; }
@media(max-width:1450px) { .dashboard-columns { grid-template-columns: minmax(0,1fr) 300px; gap: 16px; }.summary-card { padding: 18px; gap: 12px; }.shortcut { padding: 16px 13px; gap: 10px; }.shortcut-icon { width: 36px; height: 36px; font-size: 23px; }.dashboard-rail .wb-panel { padding: 18px 16px; } }
@media(max-width:1150px) { .dashboard-columns { grid-template-columns: minmax(0,1fr); }.dashboard-rail { grid-template-columns: repeat(3,minmax(0,1fr)); gap: 14px; align-items: start; }.dashboard-head { align-items: flex-start; flex-direction: column; }.summary-icon { width: 44px; height: 44px; border-radius: 13px; font-size: 25px; }.summary-card small { font-size: 14px; } }
@media(max-width:700px) { .summary-grid { gap: 10px; }.summary-card { display: block; padding: 16px 13px; }.summary-icon { margin-bottom: 12px; width: 34px; height: 34px; font-size: 21px; border-radius: 10px; }.summary-card strong { font-size: 27px; }.summary-card div > span { font-size: 14px; }.summary-card small { line-height: 1.7; }.summary-card strong small { font-size: 14px; }.dashboard-rail { grid-template-columns: minmax(0,1fr); }.shortcut-grid { grid-template-columns: minmax(0,1fr); }.shortcut-icon { width: 36px; height: 36px; }.shortcut { gap: 14px; padding: 18px; }.head-actions { width: 100%; }.head-actions a { flex: 1; font-size: 15px; }.dashboard-empty { padding: 24px 0; } }
@media(max-width:1450px) { .dashboard-head > div:first-child { display: block; } .dashboard-head h1 { margin: 0 0 7px; } .shortcut { grid-template-columns: 36px minmax(0,1fr) 12px; } .shortcut h3 { font-size: 16px; } .shortcut p { font-size: 15px; } }
.recent-panel :deep(.el-table .el-table__cell) { padding: 9px 0; }
</style>

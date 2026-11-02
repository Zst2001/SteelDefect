<template>
  <div class="records-page">
    <header class="head">
      <p class="eyebrow">本人空间</p>
      <h1>结果记录</h1>
      <p>
        查看分割对照、分类、评测与公开演示档案。学生可将实验记录提交给导师；同学之间互不可见。演示不能提交，也不展示精度。
      </p>
    </header>

    <section class="wb-panel filter-panel" aria-label="筛选记录">
    <div class="filters">
      <el-radio-group v-if="role === 'advisor'" v-model="scope" @change="resetAndReload">
        <el-radio-button label="mine">我的任务</el-radio-button>
        <el-radio-button label="inbox">学生提交</el-radio-button>
      </el-radio-group>
      <label class="filter-field"><span>任务类型</span><el-select v-model="type" placeholder="全部类型" aria-label="任务类型" clearable @change="resetAndReload">
        <el-option v-if="scope !== 'inbox'" label="公开演示" value="demo" />
        <el-option label="快速对比" value="compare" />
        <el-option label="正式评测" value="eval" />
        <el-option label="缺陷分类" value="classification" />
        <el-option label="PCB 表面分割" value="pcb_segmentation" />
        <el-option label="PCB 缺陷分类" value="pcb_classify" />
      </el-select></label>
      <label class="filter-field"><span>运行状态</span><el-select v-model="status" placeholder="全部状态" aria-label="运行状态" clearable @change="resetAndReload">
        <el-option label="排队中" value="queued" />
        <el-option label="运行中" value="running" />
        <el-option label="成功" value="success" />
        <el-option label="部分成功" value="partial_success" />
        <el-option label="失败" value="failed" />
      </el-select></label>
      <el-select v-if="scope === 'inbox'" v-model="inboxState" placeholder="审阅" clearable @change="resetAndReload">
        <el-option label="待看" value="pending" />
        <el-option label="已看" value="seen" />
      </el-select>
      <el-checkbox v-if="scope !== 'inbox'" v-model="archived" @change="resetAndReload">已归档</el-checkbox>
      <span class="filter-hint"><el-icon><Filter /></el-icon>按任务类型与状态查找实验</span>
      <el-button v-if="type || status || inboxState || archived" class="reset-filters" @click="clearFilters">重置筛选</el-button>
    </div>
    </section>

    <section class="wb-panel records-panel">
    <div class="section-head">
      <span class="section-icon"><el-icon><Tickets /></el-icon></span>
      <div><h2>{{ scope === 'inbox' ? '学生提交记录' : '实验记录' }}</h2><p>追溯配置、查看结果与管理实验档案</p></div>
      <span class="record-count">共 <strong>{{ loading || error ? '—' : total }}</strong> 条记录</span>
    </div>
    <div v-if="loading" class="records-loading" role="status" aria-live="polite"><el-skeleton :rows="4" /><p>正在读取实验记录…</p></div>
    <div v-else-if="error" class="error-state" role="alert"><div><h3>记录暂时无法加载</h3><p class="err">{{ error }}</p></div><el-button @click="reload">重试</el-button></div>
    <el-table v-else :data="items" size="small" class="table">
      <el-table-column prop="type_label" label="任务类型 / 编号" min-width="180">
        <template #default="{ row }">
          <div class="task-identity">
            <span class="type-icon" :class="row.type"><el-icon><VideoPlay v-if="row.type === 'demo'" /><DataAnalysis v-else-if="row.type === 'eval'" /><Picture v-else /></el-icon></span>
            <div><strong>{{ row.type_label }}</strong><span class="task-id" :title="row.id">#{{ row.id.slice(0, 8) }}</span></div>
          </div>
        </template>
      </el-table-column>
      <el-table-column v-if="scope === 'inbox'" prop="creator_username" label="学生" width="120" />
      <el-table-column label="状态" width="110">
        <template #default="{ row }"><TaskStatus :status="row.status" /></template>
      </el-table-column>
      <el-table-column label="提交导师" width="110">
        <template #default="{ row }"><span class="submission-state" :class="{ submitted: row.submitted_to_advisor_at }">{{ submitLabel(row) }}</span></template>
      </el-table-column>
      <el-table-column prop="note" label="备注" min-width="140" show-overflow-tooltip>
        <template #default="{ row }"><span :class="{ 'no-note': !row.note }">{{ row.note || '—' }}</span></template>
      </el-table-column>
      <el-table-column label="创建时间" width="155">
        <template #default="{ row }"><time class="created-time">{{ row.created_at?.replace("T", " ").slice(0, 16) }}</time></template>
      </el-table-column>
      <el-table-column label="操作" min-width="280">
        <template #default="{ row }">
          <div class="row-actions">
          <router-link class="view-link" :to="row.open_path"><el-icon><View /></el-icon>查看</router-link>
          <el-button v-if="row.bundle_ready" link type="primary" @click="download(row)"><el-icon><Download /></el-icon>图层包</el-button>
          <span v-else-if="!['classification', 'pcb_segmentation', 'pcb_classify'].includes(row.type) && ['success', 'partial_success'].includes(row.status)" class="unavailable" :title="row.bundle_unavailable_reason">图层包不可用</span>
          <el-dropdown v-if="row.can_rerun || row.can_submit || row.can_withdraw || row.can_analyze || row.can_note || row.can_archive" trigger="click">
            <el-button link type="primary" aria-label="更多记录操作">更多 ▾</el-button>
            <template #dropdown><el-dropdown-menu>
              <el-dropdown-item v-if="row.can_rerun" @click="rerun(row)">再跑</el-dropdown-item>
              <el-dropdown-item v-if="row.can_submit" @click="submit(row)">提交导师</el-dropdown-item>
              <el-dropdown-item v-if="row.can_withdraw" @click="withdraw(row)">撤回</el-dropdown-item>
              <el-dropdown-item v-if="row.can_analyze" @click="router.push({ path: '/assistant', query: { taskId: row.id } })">用科研助手分析</el-dropdown-item>
              <el-dropdown-item v-if="row.can_note" @click="editNote(row)">备注</el-dropdown-item>
              <el-dropdown-item v-if="row.can_archive" @click="toggleArchive(row)">{{ archived ? '取消归档' : '归档' }}</el-dropdown-item>
            </el-dropdown-menu></template>
          </el-dropdown>
          </div>
        </template>
      </el-table-column>
      <template #empty>
        <div class="empty-state"><span class="empty-icon"><el-icon><FolderOpened /></el-icon></span><h3>暂无符合筛选的记录</h3><p>试试调整类型或状态，或开始一次新的缺陷分割对照。</p><router-link to="/inspect/steel/segmentation">前往钢铁分割 →</router-link></div>
      </template>
    </el-table>
    <div v-if="!loading && !error && (items.length || total > pageSize)" class="table-footer">
      <span v-if="items.length">显示 {{ (page - 1) * pageSize + 1 }}–{{ Math.min(page * pageSize, total) }} 条，共 {{ total }} 条</span>
      <span v-else>当前页暂无记录，共 {{ total }} 条</span>
      <div v-if="total > pageSize" class="pager">
        <el-button :disabled="page <= 1" @click="page -= 1; reload()">上一页</el-button>
        <span>{{ page }} / {{ pages }}</span>
        <el-button :disabled="page >= pages" @click="page += 1; reload()">下一页</el-button>
      </div>
    </div>
    </section>
    <aside class="records-note"><el-icon><InfoFilled /></el-icon><div><strong>记录与提交说明</strong><p>分割对照、分类与正式评测可按记录权限提交导师。分类结果在详情中查看；公开演示不可提交、永不报告精度。下载状态以实际产物为准。</p></div></aside>
  </div>
</template>

<script setup lang="ts">
import TaskStatus from "../../components/TaskStatus.vue";
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { DataAnalysis, Download, Filter, FolderOpened, InfoFilled, Picture, Tickets, VideoPlay, View } from "@element-plus/icons-vue";
import { formatError, http } from "../../api/http";
import { downloadAuthFile, taskPath, taskStatusLabel } from "../../api/labels";

type RecordRow = {
  id: string;
  type: string;
  type_label: string;
  status: string;
  note: string;
  archived: boolean;
  bundle_ready: boolean;
  bundle_unavailable_reason?: string | null;
  created_at: string;
  creator_username: string | null;
  submitted_to_advisor_at: string | null;
  advisor_seen_at: string | null;
  open_path: string;
  can_submit: boolean;
  can_withdraw: boolean;
  can_rerun: boolean;
  can_archive: boolean;
  can_note: boolean;
  can_analyze?: boolean;
};

const role = ref<"student" | "advisor">("student");
const router = useRouter();
const route = useRoute();
const scope = ref<"mine" | "inbox">("mine");
const type = ref<string>(["compare", "eval", "demo", "classification", "pcb_segmentation", "pcb_classify"].includes(String(route.query.type)) ? String(route.query.type) : "");
const status = ref<string>("");
const inboxState = ref<string>("");
const archived = ref(false);
const items = ref<RecordRow[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = 20;
const error = ref("");
const loading = ref(true);
let listRequest = 0;
onBeforeUnmount(() => { listRequest += 1; });
const pages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)));

function submitLabel(row: RecordRow) {
  if (row.type === "demo") return "不可提交";
  if (!row.submitted_to_advisor_at) return "未提交";
  return row.advisor_seen_at ? "导师已看" : "已提交";
}

function clearFilters() {
  type.value = "";
  status.value = "";
  inboxState.value = "";
  archived.value = false;
  resetAndReload();
}

function resetAndReload() {
  page.value = 1;
  if (scope.value === "inbox" && type.value === "demo") type.value = "";
  void reload();
}

async function reload() {
  const request = ++listRequest;
  loading.value = true;
  error.value = "";
  try {
    const { data } = await http.get("/records", {
      params: {
        scope: scope.value,
        type: type.value || undefined,
        status: status.value || undefined,
        archived: archived.value,
        inbox_state: scope.value === "inbox" && inboxState.value ? inboxState.value : undefined,
        page: page.value,
        page_size: pageSize,
      },
    });
    if (request !== listRequest) return;
    items.value = data.items ?? [];
    total.value = data.total ?? 0;
  } catch (err) {
    if (request === listRequest) error.value = formatError(err);
  } finally {
    if (request === listRequest) loading.value = false;
  }
}

async function download(row: RecordRow) {
  try {
    const path = row.type === "demo" ? `/demo/tasks/${row.id}/bundle` : `/tasks/${row.id}/bundle`;
    await downloadAuthFile(path, `${row.id}_bundle.zip`);
  } catch (err) {
    ElMessage.error(formatError(err));
  }
}

async function rerun(row: RecordRow) {
  try {
    const { data } = await http.post(`/records/${row.id}/rerun`);
    ElMessage.success("已按原配置重新入队");
    await router.push(taskPath(data.type, data.id));
  } catch (err) {
    ElMessage.error(formatError(err));
  }
}

async function submit(row: RecordRow) {
  try {
    await http.post(`/records/${row.id}/submit`);
    ElMessage.success("已提交导师");
    await reload();
  } catch (err) {
    ElMessage.error(formatError(err));
  }
}

async function withdraw(row: RecordRow) {
  try {
    await http.post(`/records/${row.id}/withdraw`);
    ElMessage.success("已撤回");
    await reload();
  } catch (err) {
    ElMessage.error(formatError(err));
  }
}

async function editNote(row: RecordRow) {
  try {
    const { value } = await ElMessageBox.prompt("备注只自己和导师可见", "编辑备注", {
      confirmButtonText: "保存",
      cancelButtonText: "取消",
      inputValue: row.note || "",
      inputPlaceholder: "最多 255 字",
    });
    await http.patch(`/records/${row.id}`, { note: String(value ?? "").trim() });
    await reload();
  } catch (err) {
    if (err === "cancel" || err === "close") return;
    ElMessage.error(formatError(err));
  }
}

async function toggleArchive(row: RecordRow) {
  try {
    await http.patch(`/records/${row.id}`, { archived: !archived.value });
    await reload();
  } catch (err) {
    ElMessage.error(formatError(err));
  }
}

onMounted(async () => {
  try {
    const { data } = await http.get("/auth/me");
    role.value = data.role;
  } catch {
    role.value = "student";
  }
  await reload();
});
</script>

<style scoped>
.eyebrow { color: var(--lab-accent-2); letter-spacing: .16em; font-size: 14px; margin: 0 0 8px; }
.head h1 { margin: 0 0 10px; }
.head > p:last-child { color: var(--lab-muted); max-width: 850px; line-height: 1.7; margin: 0; }
.filter-panel { padding: 17px 22px; margin-top: 24px; }
.filters { display: flex; align-items: center; flex-wrap: wrap; gap: 22px; }
.filter-field { display: flex; align-items: center; gap: 11px; }
.filter-field > span { font-size: 15px; color: #62748c; white-space: nowrap; }
.filters .el-select { width: 150px; }
.filter-hint { margin-left: auto; display: flex; align-items: center; gap: 7px; font-size: 14px; color: #61758e; }
.records-panel { margin-top: 20px; padding: 0; overflow: hidden; }
.section-head { display: flex; align-items: center; gap: 12px; padding: 22px 24px; }
.section-icon { width: 38px; height: 38px; display: grid; place-items: center; flex: none; background: #ecf3ff; color: #3978e2; border-radius: 10px; font-size: 23px; }
.section-head h2 { margin: 0 0 5px; font-size: 19px; }
.section-head p { margin: 0; font-size: 15px; color: var(--lab-muted); }
.record-count { margin-left: auto; font-size: 15px; color: var(--lab-muted); white-space: nowrap; }
.record-count strong { font: 600 15px var(--lab-font-mono); color: var(--lab-text); margin: 0 4px; }
.records-loading { padding: 26px; border-top: 1px solid var(--lab-line); color: var(--lab-muted); font-size: 14px; }
.records-loading p { margin-bottom: 0; }
.error-state h3 { margin: 0 0 8px; color: var(--lab-text); }
.table { width: 100%; }
.table :deep(th.el-table__cell) { background: #f5f8fc; font-size: 14px; color: #4f627b; font-weight: 600; height: 43px; border-top: 1px solid #edf1f7; }
.table :deep(td.el-table__cell) { padding-top: 17px; padding-bottom: 17px; }
.table :deep(.cell) { padding-left: 18px; padding-right: 12px; }
.task-identity { display: flex; align-items: center; gap: 10px; }
.type-icon { display: grid; place-items: center; width: 36px; height: 40px; background: #edf4ff; color: #4d83d8; border: 1px solid #dfebfc; border-radius: 7px; font-size: 21px; flex: none; }
.type-icon.demo { color: #2baeb2; background: #ebf8f8; border-color: #d9f0f0; }
.type-icon.eval { color: #8a77d0; background: #f2effc; border-color: #e7e0f8; }
.task-identity strong { display: block; font-size: 15px; font-weight: 500; color: #354c6b; }
.task-id { display: block; font: 14px var(--lab-font-mono); color: #61758e; margin-top: 4px; }
.submission-state { font-size: 14px; color: #61758e; }
.submission-state.submitted { color: #4d7aab; }
.no-note { color: #b2bdca; }
.created-time { font-size: 14px; color: #718097; }
.row-actions { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; }
.view-link { display: inline-flex; align-items: center; gap: 5px; color: #4e78b6; border: 1px solid #d9e5f5; padding: 3px 9px; border-radius: 5px; text-decoration: none; font-size: 14px; background: #fbfdff; }
.view-link:hover { border-color: #6396e8; background: #f0f6ff; }
.row-actions :deep(.el-button) { font-size: 14px; }
.row-actions :deep(.el-icon) { margin-right: 3px; }
.unavailable { color: #9aa6b5; font-size: 14px; }
.table-footer { display: flex; justify-content: space-between; align-items: center; padding: 18px 24px; gap: 15px; font-size: 14px; color: #8898ad; }
.pager { display: flex; align-items: center; gap: 12px; }
.pager .el-button { font-size: 14px; padding: 0 12px; height: 28px; }
.records-note { display: flex; align-items: start; gap: 10px; margin-top: 20px; padding: 17px 20px; background: #edf4ff; border: 1px solid #dce8f8; border-radius: 10px; color: #5e7b9f; }
.records-note > .el-icon { color: #5c8bd0; flex: none; margin-top: 1px; }
.records-note strong { font-size: 15px; font-weight: 500; color: #4f739e; }
.records-note p { margin: 5px 0 0; line-height: 1.8; font-size: 14px; }
.empty-state { padding: 45px 20px; line-height: 1.6; }
.empty-icon { display: grid; place-items: center; width: 65px; height: 65px; margin: 0 auto 16px; background: #f0f5fc; color: #b5c9e2; border-radius: 20px; font-size: 35px; }
.empty-state h3 { font-size: 16px; font-weight: 500; color: #526883; margin: 0 0 7px; }
.empty-state p { color: #8a9ab0; font-size: 15px; }
.empty-state a { color: var(--lab-accent-2); text-decoration: none; font-size: 15px; }
.error-state { display: flex; align-items: center; justify-content: space-between; gap: 18px; padding: 24px; background: #fffaf7; border-top: 1px solid #f0dfd2; }.error-state > div { min-width: 0; }.error-state .err { overflow-wrap: anywhere; margin-bottom: 0; }
.err { color: var(--lab-danger); line-height: 1.6; }
@media (max-width: 700px) { .filter-hint { display: none; } .filters { gap: 14px; } .filter-field { flex: 1 1 100%; } .filter-field .el-select { flex: 1; } .section-head { padding: 18px; } .section-head p { display: none; } .section-head h2 { margin-bottom: 0; } .table-footer { align-items: start; flex-direction: column; } }
</style>

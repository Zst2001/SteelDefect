<template>
  <div>
    <header class="head">
      <p class="eyebrow">本人空间</p>
      <h1>结果记录</h1>
      <p>
        查看对比、评测与公开演示档案。学生可将对比/评测提交给导师；同学之间互不可见。演示不能提交，也不展示精度。
      </p>
    </header>

    <div class="filters">
      <el-radio-group v-if="role === 'advisor'" v-model="scope" @change="resetAndReload">
        <el-radio-button label="mine">我的任务</el-radio-button>
        <el-radio-button label="inbox">学生提交</el-radio-button>
      </el-radio-group>
      <el-select v-model="type" placeholder="类型" clearable @change="resetAndReload">
        <el-option v-if="scope !== 'inbox'" label="公开演示" value="demo" />
        <el-option label="快速对比" value="compare" />
        <el-option label="正式评测" value="eval" />
      </el-select>
      <el-select v-model="status" placeholder="状态" clearable @change="resetAndReload">
        <el-option label="排队中" value="queued" />
        <el-option label="运行中" value="running" />
        <el-option label="成功" value="success" />
        <el-option label="部分成功" value="partial_success" />
        <el-option label="失败" value="failed" />
      </el-select>
      <el-select v-if="scope === 'inbox'" v-model="inboxState" placeholder="审阅" clearable @change="resetAndReload">
        <el-option label="待看" value="pending" />
        <el-option label="已看" value="seen" />
      </el-select>
      <el-checkbox v-if="scope !== 'inbox'" v-model="archived" @change="resetAndReload">已归档</el-checkbox>
    </div>

    <p v-if="error" class="err">{{ error }}</p>
    <el-table v-else :data="items" size="small" class="table">
      <el-table-column prop="type_label" label="类型" width="110" />
      <el-table-column v-if="scope === 'inbox'" prop="creator_username" label="学生" width="120" />
      <el-table-column label="状态" width="110">
        <template #default="{ row }">{{ taskStatusLabel(row.status) }}</template>
      </el-table-column>
      <el-table-column label="提交导师" width="110">
        <template #default="{ row }">{{ submitLabel(row) }}</template>
      </el-table-column>
      <el-table-column prop="note" label="备注" min-width="140" show-overflow-tooltip />
      <el-table-column label="时间" width="170">
        <template #default="{ row }">{{ row.created_at?.replace("T", " ").slice(0, 19) }}</template>
      </el-table-column>
      <el-table-column label="操作" min-width="280">
        <template #default="{ row }">
          <router-link :to="row.open_path">查看</router-link>
          <el-button v-if="row.bundle_ready" link type="primary" @click="download(row)">图层包</el-button>
          <el-button v-if="row.can_rerun" link type="primary" @click="rerun(row)">再跑</el-button>
          <el-button v-if="row.can_submit" link type="primary" @click="submit(row)">提交导师</el-button>
          <el-button v-if="row.can_withdraw" link type="primary" @click="withdraw(row)">撤回</el-button>
          <router-link v-if="row.can_analyze" :to="{ path: '/assistant', query: { taskId: row.id } }">用科研助手分析</router-link>
          <el-button v-if="row.can_note" link type="primary" @click="editNote(row)">备注</el-button>
          <el-button v-if="row.can_archive" link type="primary" @click="toggleArchive(row)">
            {{ archived ? "取消归档" : "归档" }}
          </el-button>
        </template>
      </el-table-column>
    </el-table>
    <p v-if="!items.length && !error" class="empty">没有符合筛选的记录。</p>
    <div v-if="total > pageSize" class="pager">
      <el-button :disabled="page <= 1" @click="page -= 1; reload()">上一页</el-button>
      <span>{{ page }} / {{ pages }}</span>
      <el-button :disabled="page >= pages" @click="page += 1; reload()">下一页</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
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
const scope = ref<"mine" | "inbox">("mine");
const type = ref<string>("");
const status = ref<string>("");
const inboxState = ref<string>("");
const archived = ref(false);
const items = ref<RecordRow[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = 20;
const error = ref("");
const pages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)));

function submitLabel(row: RecordRow) {
  if (row.type === "demo") return "不可提交";
  if (!row.submitted_to_advisor_at) return "未提交";
  return row.advisor_seen_at ? "导师已看" : "已提交";
}

function resetAndReload() {
  page.value = 1;
  if (scope.value === "inbox" && type.value === "demo") type.value = "";
  void reload();
}

async function reload() {
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
    items.value = data.items ?? [];
    total.value = data.total ?? 0;
  } catch (err) {
    error.value = formatError(err);
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
.eyebrow {
  color: var(--lab-accent-2);
  letter-spacing: 0.16em;
  font-size: 12px;
}
.head h1 {
  margin: 0 0 8px;
}
.head p,
.empty,
.err {
  color: var(--lab-muted);
  max-width: 720px;
  line-height: 1.7;
}
.err {
  color: var(--lab-danger);
}
.filters {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  margin: 20px 0 16px;
}
.table {
  width: 100%;
}
.table a {
  color: var(--lab-accent-2);
  margin-right: 8px;
  text-decoration: none;
}
.pager {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-top: 16px;
}
</style>

<template>
  <div>
    <header class="head">
      <p class="eyebrow">仅导师</p>
      <h1>系统管理</h1>
      <p>公开注册已关闭。在此开通或启停学生账号；操作会留下操作者、时间、对象与原因。</p>
    </header>

    <section class="panel">
      <h2>开通学生</h2>
      <el-form class="form" label-position="top" @submit.prevent="createStudent">
        <el-form-item label="用户名">
          <el-input v-model="username" maxlength="32" placeholder="2–32 位，中文 / 字母 / 数字" />
        </el-form-item>
        <el-form-item label="初始密码">
          <el-input v-model="password" type="password" show-password placeholder="至少 8 位" />
        </el-form-item>
        <el-form-item label="原因">
          <el-input v-model="reason" maxlength="200" placeholder="例如：2026 级新生入组" />
        </el-form-item>
        <el-button type="primary" native-type="submit" :loading="saving" class="go">开通并允许登录</el-button>
      </el-form>
      <p v-if="formError" class="err">{{ formError }}</p>
    </section>

    <section class="panel">
      <h2>首页统计</h2>
      <p class="muted">显示在首页 Hero 下方，与条目数量独立，可按实际成果填写。</p>
      <el-form class="form" label-position="top" @submit.prevent="saveStats">
        <el-form-item label="研究模型">
          <el-input-number v-model="statsForm.research_models" :min="0" :max="99999" />
        </el-form-item>
        <el-form-item label="论文成果">
          <el-input-number v-model="statsForm.papers" :min="0" :max="99999" />
        </el-form-item>
        <el-button type="primary" native-type="submit" :loading="savingStats" class="go">保存统计</el-button>
      </el-form>
      <p class="muted">模型、成果、基金与数据集的上传 / 编辑 / 删除也可在首页以导师身份直接操作。</p>
    </section>

    <section class="block">
      <h2>账号</h2>
      <el-table v-if="users.length" :data="users" size="small">
        <el-table-column prop="username" label="用户名" min-width="140" />
        <el-table-column prop="role_label" label="角色" width="90" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }">{{ row.status === "active" ? "启用" : "停用" }}</template>
        </el-table-column>
        <el-table-column label="操作" width="120">
          <template #default="{ row }">
            <el-button
              v-if="row.role === 'student'"
              link
              type="primary"
              @click="toggleStatus(row)"
            >
              {{ row.status === "active" ? "停用" : "启用" }}
            </el-button>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
      </el-table>
      <p v-else class="muted">正在读取账号列表。</p>
      <p v-if="listError" class="err">{{ listError }}</p>
    </section>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { fetchCatalog } from "../../api/catalog";
import { formatError, http } from "../../api/http";

type LabUser = {
  id: string;
  username: string;
  role: "student" | "advisor";
  role_label: string;
  status: "active" | "disabled";
};

const users = ref<LabUser[]>([]);
const username = ref("");
const password = ref("");
const reason = ref("开通学生账号");
const saving = ref(false);
const savingStats = ref(false);
const formError = ref("");
const listError = ref("");
const statsForm = reactive({ research_models: 0, papers: 0 });

async function loadUsers() {
  listError.value = "";
  try {
    const { data } = await http.get("/admin/users");
    users.value = data.items ?? [];
  } catch (err) {
    listError.value = formatError(err);
  }
}

async function createStudent() {
  saving.value = true;
  formError.value = "";
  try {
    await http.post("/admin/users", {
      username: username.value.trim(),
      password: password.value,
      reason: reason.value.trim() || "开通学生账号",
    });
    ElMessage.success(`已开通 ${username.value.trim()}，该学生可登录实验台`);
    username.value = "";
    password.value = "";
    await loadUsers();
  } catch (err) {
    formError.value = formatError(err);
  } finally {
    saving.value = false;
  }
}

async function toggleStatus(row: LabUser) {
  const next = row.status === "active" ? "disabled" : "active";
  const action = next === "disabled" ? "停用" : "启用";
  try {
    const { value } = await ElMessageBox.prompt(`请填写${action}原因`, `${action} ${row.username}`, {
      confirmButtonText: action,
      cancelButtonText: "取消",
      inputPlaceholder: "原因将写入审计",
      inputPattern: /\S+/,
      inputErrorMessage: "原因不能为空",
    });
    await http.patch(`/admin/users/${row.id}`, { status: next, reason: String(value).trim() });
    ElMessage.success(`已${action} ${row.username}`);
    await loadUsers();
  } catch (err) {
    if (err === "cancel" || err === "close") {
      return;
    }
    ElMessage.error(formatError(err));
  }
}

async function saveStats() {
  savingStats.value = true;
  try {
    await http.put("/catalog/stats", {
      research_models: statsForm.research_models,
      papers: statsForm.papers,
    });
    ElMessage.success("首页统计已更新");
  } catch (err) {
    ElMessage.error(formatError(err));
  } finally {
    savingStats.value = false;
  }
}

onMounted(async () => {
  await loadUsers();
  try {
    const data = await fetchCatalog();
    statsForm.research_models = data.stats.research_models;
    statsForm.papers = data.stats.papers;
  } catch {
    /* 统计加载失败时保留 0，保存仍可重试 */
  }
});
</script>

<style scoped>
.head h1 {
  margin: 0 0 8px;
}
.eyebrow {
  color: var(--lab-accent-2);
  letter-spacing: 0.16em;
  font-size: 12px;
  margin: 0 0 8px;
}
.head p,
.muted {
  color: var(--lab-muted);
  line-height: 1.7;
  max-width: 640px;
}
.panel {
  margin: 28px 0;
  max-width: 480px;
  background: var(--lab-panel);
  border: 1px solid var(--lab-line);
  padding: 20px 20px 8px;
}
.panel h2,
.block h2 {
  margin: 0 0 12px;
  font-size: 18px;
}
.go {
  margin-bottom: 12px;
  background: var(--lab-accent);
  border-color: var(--lab-accent);
}
.block {
  margin-top: 12px;
}
.err {
  color: var(--lab-danger);
}
</style>

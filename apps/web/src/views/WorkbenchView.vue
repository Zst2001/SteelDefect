<template>
  <div>
    <header class="head">
      <p class="eyebrow">本人空间</p>
      <h1>工作台</h1>
      <p>在 AutoDL 训完后导入模型，于同一批图上对照内置 baseline。本站不做训练。</p>
    </header>

    <el-alert
      v-for="notice in notices"
      :key="notice.id"
      :title="notice.text"
      type="info"
      show-icon
      class="notice"
    />

    <div class="grid">
      <router-link class="card" to="/compare/new">
        <h2>缺陷分割</h2>
        <p>同一批图对照。上传 1–50 张图，可选配对掩码。全部配对后给出本批参考指标（不代表完整测试集）。</p>
      </router-link>
      <router-link class="card" to="/models/import">
        <h2>导入模型</h2>
        <p>单文件 .py + .pth 自动检查。通过后为可运行，失败为不能启动并显示阶段。</p>
      </router-link>
      <router-link class="card" to="/models/perf">
        <h2>模型测评</h2>
        <p>对学生已导入模型测量参数量与本机 FPS，可选内置 baseline 对照。不是正式评测，不算 mIoU。</p>
      </router-link>
      <router-link class="card" to="/models/scatter">
        <h2>性能散点图</h2>
        <p>手填横纵坐标与参数量，生成论文风格气泡图。主模型红色，可导出 PNG 或 PDF。</p>
      </router-link>
      <router-link class="card" to="/eval/new">
        <h2>正式评测</h2>
        <p>在预置 NEU-20 上计算全量指标（不是论文完整 test split）。无掩码数据不能进入正式评测。</p>
      </router-link>
      <router-link class="card" to="/assistant">
        <h2>科研助手</h2>
        <p>对话里连续追问。分割可分析已完成的对比或评测，也可确认后封装快速对比。模型专科测参并给出建议文本。学术专科按审定语料检索。无密钥时证据仍开，不编造指标。</p>
      </router-link>
    </div>

    <section v-if="active.length" class="block">
      <h3>运行中</h3>
      <el-table :data="active" size="small">
        <el-table-column prop="type_label" label="类型" width="120" />
        <el-table-column label="状态" width="120">
          <template #default="{ row }">{{ taskStatusLabel(row.status) }}</template>
        </el-table-column>
        <el-table-column label="打开" width="100">
          <template #default="{ row }">
            <router-link :to="taskHref(row)">查看</router-link>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <section v-if="failed.length" class="block">
      <h3>失败任务</h3>
      <el-table :data="failed" size="small">
        <el-table-column prop="type_label" label="类型" width="120" />
        <el-table-column prop="error_summary" label="原因" />
        <el-table-column label="打开" width="100">
          <template #default="{ row }">
            <router-link :to="taskHref(row)">查看</router-link>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <section class="block">
      <h3>最近任务</h3>
      <el-table v-if="tasks.length" :data="tasks" size="small">
        <el-table-column prop="type_label" label="类型" width="120" />
        <el-table-column label="状态" width="120">
          <template #default="{ row }">{{ taskStatusLabel(row.status) }}</template>
        </el-table-column>
        <el-table-column label="有 GT" width="90">
          <template #default="{ row }">{{ row.has_gt ? "是" : "否" }}</template>
        </el-table-column>
        <el-table-column label="操作" width="220">
          <template #default="{ row }">
            <router-link :to="taskHref(row)">查看</router-link>
            <el-button
              v-if="row.bundle_ready"
              link
              type="primary"
              @click="downloadBundle(row)"
            >
              下载图层包
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <p v-else class="empty">还没有任务。从缺陷分割开始。</p>
    </section>

    <section class="block">
      <h3>最近导入</h3>
      <p v-if="!models.length" class="empty">还没有学生模型。从导入入口提交 .py 与 .pth。</p>
      <ul v-else class="model-list">
        <li v-for="model in models" :key="model.id">
          <router-link :to="`/models/${model.id}`">{{ model.name }}</router-link>
          · {{ modelStatusLabel(model.status) }}
          <template v-if="model.fail_stage"> · {{ model.fail_stage }}</template>
        </li>
      </ul>
    </section>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import { formatError, http } from "../api/http";
import { downloadAuthFile, modelStatusLabel, taskPath, taskStatusLabel } from "../api/labels";

type DashTask = {
  id: string;
  type: string;
  type_label: string;
  status: string;
  has_gt: boolean;
  error_summary: string | null;
  bundle_ready: boolean;
};
type DashModel = { id: string; name: string; status: string; fail_stage: string | null };
type Notice = { id: string; text: string };

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

onMounted(async () => {
  const { data } = await http.get("/me/dashboard");
  notices.value = data.notices ?? [];
  tasks.value = data.recent_tasks ?? [];
  active.value = data.active_tasks ?? [];
  failed.value = data.failed_tasks ?? [];
  models.value = data.recent_models ?? [];
});
</script>

<style scoped>
.eyebrow {
  color: var(--lab-fiducial);
  font-family: var(--lab-font-mono);
  letter-spacing: 0.16em;
  font-size: 11px;
  margin: 0 0 8px;
}
.head h1 {
  margin: 0 0 8px;
}
.head p,
.empty {
  color: var(--lab-muted);
  line-height: 1.6;
}
.notice {
  margin: 16px 0;
}
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 16px;
  margin: 28px 0 36px;
}
.card {
  display: block;
  text-decoration: none;
  background: var(--lab-panel);
  border: 1px solid var(--lab-line);
  padding: 24px 22px;
  min-height: 168px;
  transition: border-color 180ms ease;
}
.card:hover {
  border-color: var(--lab-fiducial);
}
.card.muted {
  opacity: 0.72;
}
.block {
  margin-bottom: 32px;
}
.block h3 {
  margin: 0 0 12px;
}
.model-list {
  color: var(--lab-muted);
  line-height: 1.8;
}
</style>

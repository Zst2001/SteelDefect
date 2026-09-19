<template>
  <div>
    <header class="head">
      <p class="eyebrow">展示面</p>
      <h1>公开演示</h1>
      <p class="disclaimer">{{ disclaimer }}</p>
      <p>
        点选 1–5 张预备样例，勾选 1–3 个内置模型。访客 24 小时内可成功入队 3 次；登录后不计这 3 次。本页无上传、无学生模型、不展示精度。
      </p>
    </header>

    <el-alert
      v-if="quotaHit"
      type="warning"
      show-icon
      :closable="false"
      class="mb"
      :title="quotaText"
    >
      <el-button class="login-link" link type="warning" @click="goLogin">登录后继续</el-button>
    </el-alert>
    <p v-else-if="error" class="err">{{ error }}</p>

    <h2>预备样例（{{ selectedKeys.length }} / 5）</h2>
    <p v-if="!samples.length" class="meta">正在读取样例目录…</p>
    <div class="tray" role="group" aria-label="预备样例">
      <button
        v-for="sample in samples"
        :key="sample.sample_key"
        type="button"
        class="coupon"
        :class="{ on: selectedKeys.includes(sample.sample_key), full: selectedKeys.length >= 5 && !selectedKeys.includes(sample.sample_key) }"
        :aria-pressed="selectedKeys.includes(sample.sample_key)"
        @click="toggleSample(sample.sample_key)"
      >
        <img :src="sample.preview_url" :alt="sample.sample_key" />
        <span>{{ sample.sample_key }}</span>
      </button>
    </div>
    <div class="legend">
      <span v-for="item in legend" :key="item.id" class="chip">
        <i :style="{ background: item.color }"></i>{{ item.name }}
      </span>
    </div>

    <h2>内置模型（{{ selectedModels.length }} / 3）</h2>
    <el-checkbox-group v-model="selectedModels">
      <el-checkbox v-for="model in models" :key="model.id" :label="model.id" :disabled="selectedModels.length >= 3 && !selectedModels.includes(model.id)">
        {{ model.name }}
        <span class="meta">{{ model.slug }} · CPU</span>
      </el-checkbox>
    </el-checkbox-group>

    <div class="actions">
      <el-button type="primary" :loading="submitting" :disabled="!canSubmit" @click="submit">开始演示</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { asApiError, formatError, http } from "../../api/http";

type Sample = { sample_key: string; width: number; height: number; preview_url: string };
type ModelCard = { id: string; name: string; slug: string };
type Legend = { id: number; name: string; color: string };

const router = useRouter();
const samples = ref<Sample[]>([]);
const models = ref<ModelCard[]>([]);
const legend = ref<Legend[]>([]);
const disclaimer = ref("公开演示 / 预备样例 / 不代表测试集性能");
const selectedKeys = ref<string[]>([]);
const selectedModels = ref<string[]>([]);
const submitting = ref(false);
const error = ref("");
const quotaHit = ref(false);
const quotaText = ref("");

const canSubmit = computed(
  () =>
    selectedKeys.value.length >= 1 &&
    selectedKeys.value.length <= 5 &&
    selectedModels.value.length >= 1 &&
    selectedModels.value.length <= 3,
);

function toggleSample(key: string) {
  const idx = selectedKeys.value.indexOf(key);
  if (idx >= 0) {
    selectedKeys.value.splice(idx, 1);
    return;
  }
  if (selectedKeys.value.length >= 5) return;
  selectedKeys.value.push(key);
}

function goLogin() {
  void router.push({ path: "/login", query: { redirect: "/demo" } });
}

onMounted(async () => {
  try {
    const catalog = await http.get("/demo/samples");
    samples.value = catalog.data.items ?? [];
    legend.value = catalog.data.legend ?? [];
    if (catalog.data.disclaimer) disclaimer.value = catalog.data.disclaimer;
    const listed = await http.get("/demo/models");
    models.value = listed.data.items ?? [];
  } catch (err) {
    error.value = formatError(err);
  }
});

async function submit() {
  submitting.value = true;
  error.value = "";
  quotaHit.value = false;
  try {
    const created = await http.post("/demo/tasks", {
      sample_keys: selectedKeys.value,
      baseline_version_ids: selectedModels.value,
    });
    await router.push(`/demo/${created.data.id}`);
  } catch (err) {
    const parsed = asApiError(err);
    if (parsed.code === "DEMO_QUOTA") {
      quotaHit.value = true;
      quotaText.value = parsed.message;
    } else {
      error.value = formatError(err);
    }
  } finally {
    submitting.value = false;
  }
}
</script>

<style scoped>
.eyebrow {
  color: var(--lab-accent-2);
  letter-spacing: 0.16em;
  font-size: 12px;
}
.head p,
.meta {
  color: var(--lab-muted);
}
.disclaimer {
  border-left: 3px solid var(--lab-accent-2);
  padding-left: 12px;
  color: var(--lab-accent-2) !important;
}
.tray {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 10px;
  margin: 12px 0 16px;
}
.coupon {
  background: #0f1318;
  border: 1px solid var(--lab-line);
  color: var(--lab-muted);
  padding: 0;
  text-align: left;
}
.coupon img {
  display: block;
  width: 100%;
  aspect-ratio: 1;
  object-fit: cover;
  filter: contrast(1.05) saturate(0.85);
}
.coupon span {
  display: block;
  padding: 6px 8px 8px;
  font-size: 12px;
  letter-spacing: 0.04em;
}
.coupon.on {
  border-color: var(--lab-accent);
  color: var(--lab-text);
  box-shadow: inset 0 0 0 1px var(--lab-accent);
}
.coupon.full {
  opacity: 0.45;
}
.legend {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
  margin: 0 0 24px;
}
.chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--lab-muted);
  font-size: 13px;
}
.chip i {
  width: 12px;
  height: 12px;
  display: inline-block;
}
.actions {
  margin-top: 24px;
}
.mb {
  margin-bottom: 16px;
}
.login-link {
  color: var(--lab-accent-2);
  margin-left: 8px;
}
.err {
  color: var(--lab-danger);
}
:deep(.el-checkbox) {
  display: flex;
  margin: 8px 0;
}
</style>

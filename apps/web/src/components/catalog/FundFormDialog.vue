<template>
  <el-dialog v-model="visible" :title="form.id ? '编辑基金' : '新增基金'" width="560px" destroy-on-close>
    <el-form label-position="top">
      <el-form-item label="项目名称" required>
        <el-input v-model="form.name" maxlength="255" />
      </el-form-item>
      <el-form-item label="基金类别" required>
        <el-select v-model="form.source">
          <el-option v-for="(label, value) in FUND_SOURCE_LABELS" :key="value" :label="label" :value="value" />
        </el-select>
      </el-form-item>
      <el-form-item label="批准号">
        <el-input v-model="form.number" maxlength="128" placeholder="没有真实批准号则留空" />
      </el-form-item>
      <el-form-item label="承担角色" required>
        <el-select v-model="form.role">
          <el-option v-for="(label, value) in FUND_ROLE_LABELS" :key="value" :label="label" :value="value" />
        </el-select>
      </el-form-item>
      <el-form-item label="起止年份">
        <div class="years">
          <el-input-number v-model="form.start_year" :min="1990" :max="2100" controls-position="right" placeholder="起始" />
          <span class="sep">–</span>
          <el-input-number v-model="form.end_year" :min="1990" :max="2100" controls-position="right" placeholder="结束" />
        </div>
      </el-form-item>
      <el-form-item label="状态" required>
        <el-select v-model="form.status">
          <el-option v-for="(label, value) in FUND_STATUS_LABELS" :key="value" :label="label" :value="value" />
        </el-select>
      </el-form-item>
      <el-form-item label="经费说明">
        <el-input v-model="form.amount_text" maxlength="64" placeholder="没有公开金额则留空，不要编造" />
      </el-form-item>
      <el-form-item label="简介">
        <el-input v-model="form.detail" type="textarea" :rows="3" maxlength="4000" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="saving" @click="save">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { formatError, http } from "../../api/http";
import {
  FUND_ROLE_LABELS,
  FUND_SOURCE_LABELS,
  FUND_STATUS_LABELS,
  type CatalogFund,
  type FundRole,
  type FundSource,
  type FundStatus,
} from "../../api/catalog";

const props = defineProps<{
  fund: CatalogFund | null;
  create: boolean;
}>();

const emit = defineEmits<{
  close: [];
  saved: [];
}>();

const visible = ref(false);
const saving = ref(false);
const form = reactive({
  id: "",
  name: "",
  source: "nsfc" as FundSource,
  number: "",
  role: "pi" as FundRole,
  start_year: undefined as number | undefined,
  end_year: undefined as number | undefined,
  status: "ongoing" as FundStatus,
  amount_text: "",
  detail: "",
});

watch(
  () => [props.fund, props.create] as const,
  ([fund, create]) => {
    visible.value = Boolean(fund) || create;
    if (fund) {
      form.id = fund.id;
      form.name = fund.name;
      form.source = fund.source;
      form.number = fund.number ?? "";
      form.role = fund.role;
      form.start_year = fund.start_year ?? undefined;
      form.end_year = fund.end_year ?? undefined;
      form.status = fund.status;
      form.amount_text = fund.amount_text ?? "";
      form.detail = fund.detail ?? "";
    } else if (create) {
      form.id = "";
      form.name = "";
      form.source = "nsfc";
      form.number = "";
      form.role = "pi";
      form.start_year = undefined;
      form.end_year = undefined;
      form.status = "ongoing";
      form.amount_text = "";
      form.detail = "";
    }
  },
  { immediate: true },
);

watch(visible, (value) => {
  if (!value) {
    emit("close");
  }
});

async function save() {
  if (!form.name.trim()) {
    ElMessage.warning("请填写项目名称");
    return;
  }
  saving.value = true;
  const payload = {
    name: form.name.trim(),
    source: form.source,
    number: form.number.trim() || null,
    role: form.role,
    start_year: form.start_year ?? null,
    end_year: form.end_year ?? null,
    status: form.status,
    amount_text: form.amount_text.trim() || null,
    detail: form.detail.trim() || null,
  };
  try {
    if (form.id) {
      await http.patch(`/catalog/funds/${form.id}`, payload);
    } else {
      await http.post("/catalog/funds", payload);
    }
    ElMessage.success("已保存");
    emit("saved");
    visible.value = false;
  } catch (err) {
    ElMessage.error(formatError(err));
  } finally {
    saving.value = false;
  }
}
</script>

<style scoped>
.years {
  display: flex;
  align-items: center;
  gap: 8px;
}
.sep {
  color: var(--lab-muted);
}
</style>

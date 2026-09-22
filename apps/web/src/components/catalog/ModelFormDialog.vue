<template>
  <el-dialog v-model="visible" :title="form.id ? '编辑模型' : '新增模型'" width="560px" destroy-on-close>
    <el-form label-position="top">
      <el-form-item label="名称" required>
        <el-input v-model="form.name" maxlength="128" />
      </el-form-item>
      <el-form-item label="年份">
        <el-input-number v-model="form.year" :min="1990" :max="2100" controls-position="right" />
      </el-form-item>
      <el-form-item label="任务类型" required>
        <el-select v-model="form.task_type">
          <el-option label="分类" value="classification" />
          <el-option label="检测" value="detection" />
          <el-option label="分割" value="segmentation" />
        </el-select>
      </el-form-item>
      <el-form-item label="Backbone">
        <el-input v-model="form.backbone" maxlength="128" placeholder="没有则留空" />
      </el-form-item>
      <el-form-item label="核心方法 / 关键词">
        <el-input v-model="form.keywords" maxlength="512" placeholder="用分号分隔，例如 multi-level feature; edge" />
      </el-form-item>
      <el-form-item label="数据集">
        <el-input v-model="form.dataset" maxlength="255" placeholder="没有真实数据则留空" />
      </el-form-item>
      <el-form-item label="论文链接">
        <el-input v-model="form.paper_url" maxlength="512" placeholder="没有则留空，不会显示论文按钮" />
      </el-form-item>
      <el-form-item label="代码链接">
        <el-input v-model="form.code_url" maxlength="512" />
      </el-form-item>
      <el-form-item label="详情说明">
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
import type { CatalogModel, TaskType } from "../../api/catalog";

const props = defineProps<{
  model: CatalogModel | null;
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
  year: undefined as number | undefined,
  task_type: "segmentation" as TaskType,
  backbone: "",
  keywords: "",
  dataset: "",
  paper_url: "",
  code_url: "",
  detail: "",
  is_group_work: false,
});

watch(
  () => [props.model, props.create] as const,
  ([model, create]) => {
    visible.value = Boolean(model) || create;
    if (model) {
      form.id = model.id;
      form.name = model.name;
      form.year = model.year ?? undefined;
      form.task_type = model.task_type;
      form.backbone = model.backbone ?? "";
      form.keywords = model.keywords ?? "";
      form.dataset = model.dataset ?? "";
      form.paper_url = model.paper_url ?? "";
      form.code_url = model.code_url ?? "";
      form.detail = model.detail ?? "";
      form.is_group_work = model.is_group_work;
    } else if (create) {
      form.id = "";
      form.name = "";
      form.year = undefined;
      form.task_type = "segmentation";
      form.backbone = "";
      form.keywords = "";
      form.dataset = "";
      form.paper_url = "";
      form.code_url = "";
      form.detail = "";
      form.is_group_work = false;
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
    ElMessage.warning("请填写名称");
    return;
  }
  saving.value = true;
  const payload = {
    name: form.name.trim(),
    year: form.year ?? null,
    task_type: form.task_type,
    backbone: form.backbone.trim() || null,
    keywords: form.keywords.trim() || null,
    dataset: form.dataset.trim() || null,
    paper_url: form.paper_url.trim() || null,
    code_url: form.code_url.trim() || null,
    detail: form.detail.trim() || null,
    is_group_work: form.is_group_work,
  };
  try {
    if (form.id) {
      await http.patch(`/catalog/models/${form.id}`, payload);
    } else {
      await http.post("/catalog/models", payload);
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

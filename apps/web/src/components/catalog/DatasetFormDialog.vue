<template>
  <el-dialog v-model="visible" :title="form.id ? '编辑数据集' : '新增数据集'" width="560px" destroy-on-close>
    <el-form label-position="top">
      <el-form-item label="名称" required>
        <el-input v-model="form.name" maxlength="128" />
      </el-form-item>
      <el-form-item label="任务类型" required>
        <el-select v-model="form.task_type">
          <el-option label="分类" value="classification" />
          <el-option label="检测" value="detection" />
          <el-option label="分割" value="segmentation" />
        </el-select>
      </el-form-item>
      <el-form-item label="来源 / 对象">
        <el-input v-model="form.source_object" maxlength="255" />
      </el-form-item>
      <el-form-item label="规模说明">
        <el-input v-model="form.numbers_text" maxlength="512" placeholder="原文规模描述，没有结构化数字时使用" />
      </el-form-item>
      <el-form-item label="图像数量">
        <el-input-number v-model="form.image_count" :min="0" :max="10000000" controls-position="right" />
      </el-form-item>
      <el-form-item label="缺陷类别数量">
        <el-input-number v-model="form.class_count" :min="0" :max="1000" controls-position="right" />
      </el-form-item>
      <el-form-item label="缺陷类别">
        <el-input v-model="form.defect_types" maxlength="512" placeholder="没有类别名单则留空" />
      </el-form-item>
      <el-form-item label="尺寸">
        <el-input v-model="form.size" maxlength="128" />
      </el-form-item>
      <el-form-item label="下载 / 外部链接">
        <el-input v-model="form.url" maxlength="512" />
      </el-form-item>
      <el-form-item label="访问说明">
        <el-input v-model="form.access_note" maxlength="128" placeholder="例如提取码" />
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
import type { CatalogDataset, TaskType } from "../../api/catalog";

const props = defineProps<{
  dataset: CatalogDataset | null;
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
  task_type: "segmentation" as TaskType,
  source_object: "",
  numbers_text: "",
  image_count: undefined as number | undefined,
  class_count: undefined as number | undefined,
  defect_types: "",
  size: "",
  url: "",
  access_note: "",
  detail: "",
});

watch(
  () => [props.dataset, props.create] as const,
  ([dataset, create]) => {
    visible.value = Boolean(dataset) || create;
    if (dataset) {
      form.id = dataset.id;
      form.name = dataset.name;
      form.task_type = dataset.task_type;
      form.source_object = dataset.source_object ?? "";
      form.numbers_text = dataset.numbers_text ?? "";
      form.image_count = dataset.image_count ?? undefined;
      form.class_count = dataset.class_count ?? undefined;
      form.defect_types = dataset.defect_types ?? "";
      form.size = dataset.size ?? "";
      form.url = dataset.url ?? "";
      form.access_note = dataset.access_note ?? "";
      form.detail = dataset.detail ?? "";
    } else if (create) {
      form.id = "";
      form.name = "";
      form.task_type = "segmentation";
      form.source_object = "";
      form.numbers_text = "";
      form.image_count = undefined;
      form.class_count = undefined;
      form.defect_types = "";
      form.size = "";
      form.url = "";
      form.access_note = "";
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
    ElMessage.warning("请填写名称");
    return;
  }
  saving.value = true;
  const payload = {
    name: form.name.trim(),
    task_type: form.task_type,
    source_object: form.source_object.trim() || null,
    numbers_text: form.numbers_text.trim() || null,
    image_count: form.image_count ?? null,
    class_count: form.class_count ?? null,
    defect_types: form.defect_types.trim() || null,
    size: form.size.trim() || null,
    url: form.url.trim() || null,
    access_note: form.access_note.trim() || null,
    detail: form.detail.trim() || null,
  };
  try {
    if (form.id) {
      await http.patch(`/catalog/datasets/${form.id}`, payload);
    } else {
      await http.post("/catalog/datasets", payload);
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

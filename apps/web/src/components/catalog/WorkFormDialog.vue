<template>
  <el-dialog v-model="visible" :title="form.id ? '编辑成果' : '新增成果'" width="560px" destroy-on-close>
    <el-form label-position="top">
      <el-form-item label="名称" required>
        <el-input v-model="form.name" maxlength="255" placeholder="论文、专利、软著或奖项名称" />
      </el-form-item>
      <el-form-item label="成果类型" required>
        <el-select v-model="form.kind">
          <el-option v-for="(label, value) in WORK_KIND_LABELS" :key="value" :label="label" :value="value" />
        </el-select>
      </el-form-item>
      <el-form-item label="年份">
        <el-input-number v-model="form.year" :min="1990" :max="2100" controls-position="right" />
      </el-form-item>
      <el-form-item label="发表 / 授权载体">
        <el-input v-model="form.venue" maxlength="255" placeholder="期刊、会议、专利局或颁奖单位，没有则留空" />
      </el-form-item>
      <el-form-item label="作者 / 完成人">
        <el-input v-model="form.authors" maxlength="512" />
      </el-form-item>
      <el-form-item label="简介">
        <el-input v-model="form.summary" type="textarea" :rows="3" maxlength="4000" placeholder="简要说明这项成果是什么，不填写代码仓库" />
      </el-form-item>
      <el-form-item label="原文 / 公示链接">
        <el-input v-model="form.link_url" maxlength="512" placeholder="没有则留空，不填写代码仓库" />
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
import { WORK_KIND_LABELS, type CatalogWork, type WorkKind } from "../../api/catalog";

const props = defineProps<{
  work: CatalogWork | null;
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
  kind: "paper" as WorkKind,
  year: undefined as number | undefined,
  venue: "",
  authors: "",
  summary: "",
  link_url: "",
});

watch(
  () => [props.work, props.create] as const,
  ([work, create]) => {
    visible.value = Boolean(work) || create;
    if (work) {
      form.id = work.id;
      form.name = work.name;
      form.kind = work.kind;
      form.year = work.year ?? undefined;
      form.venue = work.venue ?? "";
      form.authors = work.authors ?? "";
      form.summary = work.summary ?? "";
      form.link_url = work.link_url ?? "";
    } else if (create) {
      form.id = "";
      form.name = "";
      form.kind = "paper";
      form.year = undefined;
      form.venue = "";
      form.authors = "";
      form.summary = "";
      form.link_url = "";
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
    kind: form.kind,
    year: form.year ?? null,
    venue: form.venue.trim() || null,
    authors: form.authors.trim() || null,
    summary: form.summary.trim() || null,
    link_url: form.link_url.trim() || null,
  };
  try {
    if (form.id) {
      await http.patch(`/catalog/works/${form.id}`, payload);
    } else {
      await http.post("/catalog/works", payload);
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

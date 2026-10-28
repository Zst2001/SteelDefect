<template>
  <div class="preview-region" aria-label="已选原图预览">
    <div class="preview-heading"><span>原图预览</span><small>{{ files.length ? `已选 ${files.length} 张` : '等待选择图像' }}</small></div>
    <div v-if="previews.length" class="selected-images">
      <figure v-for="item in previews" :key="item.url">
        <img v-if="!item.failed" :src="item.url" :alt="item.name" @error="item.failed = true" />
        <div v-else class="unavailable"><el-icon><Picture /></el-icon><span>浏览器无法预览</span></div>
        <figcaption :title="item.name">{{ item.name }}</figcaption>
      </figure>
    </div>
    <div v-else class="preview-empty">
      <div class="empty-frames" aria-hidden="true"><el-icon><Picture /></el-icon></div>
      <strong>{{ files.length ? '图像已选择' : '在这里查看你的钢铁表面图像' }}</strong>
      <p>{{ files.length ? '当前格式无法在浏览器内预览，仍可提交。' : '上传后自动显示缩略图，便于检查是否选对原图。' }}</p>
    </div>
    <p v-if="files.length > previews.length && previews.length" class="more">另有 {{ files.length - previews.length }} 张，见文件列表；TIFF 预览受浏览器支持限制。</p>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from "vue";
import { Picture } from "@element-plus/icons-vue";
const props = defineProps<{ files: File[] }>();
const previews = ref<Array<{ name: string; url: string; failed: boolean }>>([]);
function release() { previews.value.forEach(item => URL.revokeObjectURL(item.url)); }
watch(() => props.files, files => {
  release();
  // TIFF remains uploadable; browsers cannot consistently decode it for previews.
  previews.value = files.filter(file => /\.(png|jpe?g)$/i.test(file.name)).slice(0, 6).map(file => ({ name: file.name, url: URL.createObjectURL(file), failed: false }));
}, { immediate: true });
onBeforeUnmount(release);
</script>
<style scoped>
.preview-region {
  min-width: 0;
}
.preview-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin: 0 0 8px;
  font-size: 15px;
  font-weight: 600;
}
.preview-heading small {
  color: var(--lab-muted);
  font-weight: 400;
}
.selected-images {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}
figure {
  min-width: 0;
  margin: 0;
}
img, .unavailable {
  width: 100%;
  height: 88px;
  object-fit: contain;
  display: block;
  background: #eaf0f7;
  border-radius: 7px;
}
.unavailable {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: var(--lab-muted);
  font-size: 14px;
}
figcaption {
  font-size: 14px;
  color: var(--lab-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-top: 6px;
}
.preview-empty {
  box-sizing: border-box;
  height: 116px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  text-align: center;
  border: 1px solid #e7edf5;
  border-radius: 9px;
  background: linear-gradient(135deg, #f8fbff, #f0f5fb);
  padding: 10px 12px;
}
.empty-frames {
  width: 37px;
  height: 30px;
  border: 1px solid #cbdaf0;
  background: #fff;
  border-radius: 7px;
  display: grid;
  place-items: center;
  color: #7295c6;
  box-shadow: -7px 5px 0 #e5edf8;
  margin: 0 0 10px;
  font-size: 23px;
  transform: rotate(4deg);
}
.preview-empty strong {
  font-size: 15px;
  font-weight: 500;
}
.preview-empty p, .more {
  font-size: 15px;
  line-height: 1.5;
  color: var(--lab-muted);
  margin: 5px 0 0;
}
@media (max-width: 480px) {
  .selected-images {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>

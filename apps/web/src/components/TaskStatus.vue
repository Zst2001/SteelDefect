<template>
  <span class="task-status" :class="tone">
    <i aria-hidden="true">
    </i>{{ taskStatusLabel(status) }}</span>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { taskStatusLabel } from "../api/labels";
const props = defineProps<{ status: string }>();
const tones: Record<string, string> = { success: 'ok', partial_success: 'warning', failed: 'bad', running: 'active', queued: 'waiting' };
const tone = computed(() => tones[props.status] ?? 'waiting');
</script>
<style scoped>
.task-status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  border-radius: 5px;
  background: #edf2f8;
  color: #52657d;
  font-size: 12px;
  white-space: nowrap;
}
i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
}
.ok {
  color: #167448;
  background: #e9f7f0;
}
.bad {
  color: #b73530;
  background: #fff0ee;
}
.active {
  color: #225ed0;
  background: #eaf1ff;
}
.warning {
  color: #8c5d0b;
  background: #fff5dd;
}
</style>

<template><nav class="pcb-tabs" aria-label="PCB 任务类型"><router-link to="/inspect/pcb" :class="{ active: !classification }" :aria-current="!classification ? 'page' : undefined">缺陷分割</router-link><router-link to="/inspect/pcb/classification" :class="{ active: classification }" :aria-current="classification ? 'page' : undefined">缺陷分类</router-link></nav></template>
<script setup lang="ts">defineProps<{ classification?: boolean }>();</script>
<style scoped>
.pcb-tabs { display:flex; gap:8px; padding:5px; width:fit-content; max-width:100%; border:1px solid #dce6f2; border-radius:9px; background:#fff; margin-bottom:24px; }
.pcb-tabs a { padding:9px 22px; border-radius:6px; font-size:15px; color:#476483; text-decoration:none; }
.pcb-tabs a.active { background:#eaf2ff; color:#235aa3; font-weight:600; }
</style>

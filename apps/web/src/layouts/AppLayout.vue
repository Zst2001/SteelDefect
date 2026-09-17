<template>
  <div class="shell">
    <aside class="side">
      <router-link class="brand" to="/">
        <span class="mark"></span>
        <div>
          <div class="title">对照台</div>
          <div class="sub">工业缺陷分割 · CPU</div>
        </div>
      </router-link>
      <el-menu :router="true" :default-active="active" background-color="#1c232b" text-color="#ece7dc" active-text-color="#d9a441">
        <el-menu-item index="/">首页</el-menu-item>
        <el-menu-item index="/workbench">工作台</el-menu-item>
        <el-menu-item index="/compare/new">快速对比</el-menu-item>
        <el-menu-item index="/datasets">数据集</el-menu-item>
        <el-menu-item index="/models">模型中心</el-menu-item>
        <el-menu-item index="/eval/new">正式评测</el-menu-item>
        <el-menu-item index="/records">结果记录</el-menu-item>
        <el-menu-item index="/assistant">科研助手</el-menu-item>
        <el-menu-item index="/detection">目标检测</el-menu-item>
        <el-menu-item index="/classification">缺陷分类</el-menu-item>
        <el-menu-item v-if="role === 'advisor'" index="/admin">系统管理</el-menu-item>
      </el-menu>
      <div class="account">
        <div class="who">{{ username }}</div>
        <div class="role">{{ role === "advisor" ? "导师" : "学生" }}</div>
        <button class="logout" type="button" @click="logout">退出</button>
      </div>
    </aside>
    <main class="main">
      <router-view />
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { http } from "../api/http";

const route = useRoute();
const router = useRouter();
const role = ref<"student" | "advisor">("student");
const username = ref("");

const active = computed(() => {
  if (route.path.startsWith("/models")) return "/models";
  if (route.path.startsWith("/compare")) return "/compare/new";
  if (route.path.startsWith("/datasets")) return "/datasets";
  if (route.path.startsWith("/eval")) return "/eval/new";
  return route.path;
});

onMounted(async () => {
  const { data } = await http.get("/auth/me");
  role.value = data.role;
  username.value = data.username;
});

async function logout() {
  await http.post("/auth/logout");
  await router.push("/login");
}
</script>

<style scoped>
.shell {
  display: grid;
  grid-template-columns: 232px 1fr;
  min-height: 100vh;
}
.side {
  background: var(--lab-panel);
  border-right: 1px solid var(--lab-line);
  display: flex;
  flex-direction: column;
  padding: 20px 0 16px;
}
.brand {
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 0 20px 18px;
  text-decoration: none;
}
.mark {
  width: 14px;
  height: 36px;
  background: linear-gradient(180deg, var(--lab-accent), var(--lab-accent-2));
}
.title {
  font-weight: 700;
  letter-spacing: 0.08em;
}
.sub {
  color: var(--lab-muted);
  font-size: 12px;
  margin-top: 2px;
}
.main {
  padding: 28px 32px 48px;
}
.account {
  margin: auto 20px 0;
  padding-top: 16px;
  border-top: 1px solid var(--lab-line);
}
.who {
  font-weight: 600;
}
.role {
  color: var(--lab-muted);
  font-size: 12px;
  margin: 4px 0 12px;
}
.logout {
  width: 100%;
  background: transparent;
  color: var(--lab-muted);
  border: 1px solid var(--lab-line);
  padding: 8px 12px;
}
.logout:hover {
  color: var(--lab-text);
  border-color: var(--lab-accent);
}
:deep(.el-menu) {
  border-right: none;
}
</style>

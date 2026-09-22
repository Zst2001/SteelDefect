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
      <el-menu
        :router="true"
        :default-active="active"
        :default-openeds="openedMenus"
        :key="openedMenus.join('|') || 'root'"
        background-color="#1c232b"
        text-color="#ece7dc"
        active-text-color="#d9a441"
      >
        <el-menu-item index="/">首页</el-menu-item>
        <el-menu-item index="/demo">公开演示</el-menu-item>
        <el-menu-item index="/workbench">工作台</el-menu-item>
        <el-sub-menu index="defect">
          <template #title>缺陷检测</template>
          <el-menu-item index="/compare/new">缺陷分割</el-menu-item>
          <el-menu-item index="/eval/new">正式评测</el-menu-item>
          <el-menu-item index="/detection">目标检测</el-menu-item>
          <el-menu-item index="/classification">缺陷分类</el-menu-item>
        </el-sub-menu>
        <el-menu-item index="/datasets">数据集</el-menu-item>
        <el-sub-menu
          index="models"
          class="models-hub"
          :class="{ 'hub-current': modelsHubActive }"
        >
          <template #title>模型中心</template>
          <el-menu-item index="/models/import">导入模型</el-menu-item>
          <el-menu-item index="/models/perf">模型测评</el-menu-item>
          <el-menu-item index="/models/scatter">性能散点图</el-menu-item>
        </el-sub-menu>
        <el-menu-item index="/records">结果记录</el-menu-item>
        <el-menu-item index="/assistant">科研助手</el-menu-item>
        <el-menu-item v-if="signedIn && role === 'advisor'" index="/admin">系统管理</el-menu-item>
      </el-menu>
      <div class="account" v-if="signedIn">
        <div class="who">{{ username }}</div>
        <div class="role">{{ role === "advisor" ? "导师" : "学生" }}</div>
        <button class="logout" type="button" @click="logout">退出</button>
      </div>
      <div class="account" v-else>
        <div class="who">访客</div>
        <div class="role">首页与公开演示可直接浏览</div>
        <router-link class="logout" to="/login">登录</router-link>
      </div>
    </aside>
    <main class="main">
      <router-view />
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { http } from "../api/http";

const route = useRoute();
const router = useRouter();
const signedIn = ref(false);
const role = ref<"student" | "advisor">("student");
const username = ref("");

const active = computed(() => {
  if (route.path.startsWith("/demo")) return "/demo";
  if (route.path.startsWith("/models/import")) return "/models/import";
  if (route.path.startsWith("/models/perf")) return "/models/perf";
  if (route.path.startsWith("/models/scatter")) return "/models/scatter";
  if (route.path.startsWith("/models")) return "/models";
  if (route.path.startsWith("/compare")) return "/compare/new";
  if (route.path.startsWith("/datasets")) return "/datasets";
  if (route.path.startsWith("/eval")) return "/eval/new";
  return route.path;
});

const modelsHubActive = computed(
  () =>
    route.path.startsWith("/models") &&
    !route.path.startsWith("/models/import") &&
    !route.path.startsWith("/models/perf") &&
    !route.path.startsWith("/models/scatter"),
);

function isModelHubPath(path: string) {
  return path === "/models" || path === "/models/";
}

function onModelHubTitleClick(event: Event) {
  if ((event.target as HTMLElement | null)?.closest(".el-menu-item")) return;
  if (isModelHubPath(route.path)) return;
  event.preventDefault();
  event.stopImmediatePropagation();
  void router.push("/models");
}

let modelsTitleEl: HTMLElement | null = null;

function unbindModelHubTitle() {
  modelsTitleEl?.removeEventListener("click", onModelHubTitleClick, true);
  modelsTitleEl = null;
}

function bindModelHubTitle() {
  unbindModelHubTitle();
  const hub = document.querySelector(".el-sub-menu.models-hub");
  if (!(hub instanceof HTMLElement)) return;
  hub.addEventListener("click", onModelHubTitleClick, true);
  modelsTitleEl = hub;
}

const openedMenus = computed(() => {
  const item = active.value;
  if (
    item === "/compare/new" ||
    item === "/eval/new" ||
    item === "/detection" ||
    item === "/classification"
  ) {
    return ["defect"];
  }
  if (
    item === "/models" ||
    item === "/models/import" ||
    item === "/models/perf" ||
    item === "/models/scatter"
  ) {
    return ["models"];
  }
  return [];
});

onMounted(async () => {
  void nextTick(bindModelHubTitle);
  try {
    const { data } = await http.get("/auth/me");
    signedIn.value = true;
    role.value = data.role;
    username.value = data.username;
  } catch {
    signedIn.value = false;
  }
});

watch(
  () => route.fullPath,
  () => {
    void nextTick(bindModelHubTitle);
  },
);

onBeforeUnmount(unbindModelHubTitle);

async function logout() {
  try {
    await http.post("/auth/logout");
  } finally {
    signedIn.value = false;
    username.value = "";
    await router.push("/");
  }
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
  display: block;
  box-sizing: border-box;
  text-align: center;
  text-decoration: none;
  background: transparent;
  color: var(--lab-muted);
  border: 1px solid var(--lab-line);
  padding: 8px 12px;
}
.logout:hover {
  color: var(--lab-text);
  border-color: var(--lab-accent);
}
:deep(.el-sub-menu.models-hub > .el-sub-menu__title) {
  cursor: pointer;
}
:deep(.el-sub-menu .el-menu) {
  background-color: #1c232b !important;
}
:deep(.el-sub-menu__title) {
  color: #ece7dc !important;
}
:deep(.el-sub-menu__title:hover) {
  background-color: transparent !important;
  color: var(--lab-text) !important;
}
:deep(.el-sub-menu.is-active > .el-sub-menu__title),
:deep(.el-sub-menu.hub-current > .el-sub-menu__title) {
  color: var(--lab-accent-2) !important;
}
</style>

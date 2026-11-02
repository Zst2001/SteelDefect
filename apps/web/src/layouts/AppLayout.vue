<template>
  <div class="shell" :class="{ 'light-shell': isLight, 'nav-open': navOpen }">
    <button v-if="isLight" class="mobile-toggle" type="button" :aria-expanded="navOpen" aria-controls="app-navigation" @click="navOpen = !navOpen">{{ navOpen ? "收起导航" : "菜单 / 对照台" }}</button>
    <aside id="app-navigation" class="side">
      <router-link class="brand" to="/">
        <svg v-if="isLight" class="mark light-mark" viewBox="0 0 40 44" aria-hidden="true">
          <path d="M20 1 38 11 20 22 2 11Z" fill="#63c6ff" />
          <path d="m2 11 18 11 18-11v9L20 31 2 20Z" fill="#3897f5" />
          <path d="m2 28 18 11 18-11-8-5-10 6-10-6Z" fill="#2b65f5" />
          <path d="m20 8 8 4.5-8 4.5-8-4.5Z" fill="#17304a" />
        </svg>
        <svg v-else class="mark" viewBox="0 0 32 32" aria-hidden="true">
          <circle cx="16" cy="16" r="11" fill="none" stroke="currentColor" stroke-width="1.4" />
          <circle cx="16" cy="16" r="3.2" fill="none" stroke="currentColor" stroke-width="1.4" />
          <path d="M16 2.5v5.5M16 24v5.5M2.5 16h5.5M24 16h5.5" stroke="currentColor" stroke-width="1.4" />
        </svg>
        <div class="brand-copy">
          <div class="title">IPPI LAB</div>
          <div class="sub">智能感知与精密工业检测实验室</div>
        </div>
      </router-link>
      <el-menu
        :router="true"
        :default-active="active"
        :default-openeds="openedMenus"
        :key="openedMenus.join('|') || 'root'"
        background-color="var(--lab-rail)"
        text-color="#e8edf1"
        active-text-color="#3ec7d8"
      >
        <el-menu-item index="/"><el-icon v-if="isLight"><House /></el-icon>首页</el-menu-item>
        <el-menu-item index="/demo"><el-icon v-if="isLight"><VideoPlay /></el-icon>公开演示</el-menu-item>
        <el-menu-item index="/workbench"><el-icon v-if="isLight"><Grid /></el-icon>工作台</el-menu-item>
        <el-sub-menu index="defect">
          <template #title><el-icon v-if="isLight"><Aim /></el-icon>缺陷检测</template>
          <el-menu-item index="/inspect/steel/segmentation"><span v-if="isLight" class="nav-dot" />钢铁检测</el-menu-item>
          <el-menu-item index="/inspect/pcb"><span v-if="isLight" class="nav-dot" />PCB板检测</el-menu-item>
          <el-menu-item index="/inspect/solar"><span v-if="isLight" class="nav-dot" />太阳能电池板检测<span v-if="isLight" class="nav-badge">待接入</span></el-menu-item>
        </el-sub-menu>
        <el-menu-item index="/datasets"><el-icon v-if="isLight"><Files /></el-icon>数据集</el-menu-item>
        <el-sub-menu
          index="models"
          class="models-hub"
          :class="{ 'hub-current': modelsHubActive }"
        >
          <template #title><el-icon v-if="isLight"><Cpu /></el-icon>模型中心</template>
          <el-menu-item index="/models/import">导入模型</el-menu-item>
          <el-menu-item index="/models/perf">模型测评</el-menu-item>
          <el-menu-item index="/models/scatter">性能散点图</el-menu-item>
        </el-sub-menu>
        <el-menu-item index="/records"><el-icon v-if="isLight"><Document /></el-icon>结果记录</el-menu-item>
        <el-menu-item index="/assistant"><el-icon v-if="isLight"><ChatDotRound /></el-icon>科研助手</el-menu-item>
        <el-menu-item v-if="signedIn && role === 'advisor'" index="/admin"><el-icon v-if="isLight"><Setting /></el-icon>系统管理</el-menu-item>
      </el-menu>
      <div class="account" v-if="signedIn">
        <div class="who"><span v-if="isLight" class="side-avatar">{{ username.slice(0, 1) }}</span>{{ username }}</div>
        <div class="role">{{ role === "advisor" ? "导师" : "学生" }}</div>
        <button class="logout" type="button" @click="logout">退出</button>
      </div>
      <div class="account" v-else>
        <div class="who">访客</div>
        <div class="role">首页与公开演示可直接浏览</div>
        <router-link class="logout" to="/login">登录</router-link>
      </div>
      <p class="bench-status"><el-icon v-if="isLight"><Cpu /></el-icon> CPU 常驻 · 本站不做训练</p>
    </aside>
    <main class="main" :class="{ flush: route.path.startsWith('/assistant') }">
      <div v-if="isLight && !route.path.startsWith('/assistant')" class="workspace-bar">
        <span class="breadcrumb"><el-icon><Grid /></el-icon> {{ route.name === 'home' ? 'IPPI Lab' : '实验工作空间' }} <span class="bar-divider">/</span><strong>{{ sectionLabel }}</strong></span>
        <div class="bar-account"><span class="cpu-label"><el-icon><Cpu /></el-icon> CPU 部署</span><span class="bar-avatar">{{ signedIn ? username.slice(0, 1) : '访' }}</span><span class="bar-identity"><strong>{{ signedIn ? username : '访客' }}</strong><small>{{ signedIn ? (role === 'advisor' ? '导师' : '学生') : '公开浏览' }}</small></span></div>
      </div>
      <router-view />
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { House, VideoPlay, Grid, Files, Document, ChatDotRound, Setting, Cpu, Aim } from "@element-plus/icons-vue";
import { http } from "../api/http";

const route = useRoute();
const router = useRouter();
// The public homepage is included in the light shell at the user's request.
const isLight = true;
const navOpen = ref(false);
const sectionLabel = computed(() => {
  const path = route.path;
  if (path === "/") return "实验室概览";
  if (path.startsWith("/inspect") || path.startsWith("/compare") || path.startsWith("/eval") || path.startsWith("/classification/")) return "缺陷检测";
  if (path.startsWith("/models")) return "模型中心";
  if (path.startsWith("/demo")) return "公开演示";
  if (path.startsWith("/records")) return "结果记录";
  if (path.startsWith("/datasets")) return "数据集";
  if (path.startsWith("/admin")) return "系统管理";
  return "工作台";
});
const signedIn = ref(false);
const role = ref<"student" | "advisor">("student");
const username = ref("");

const active = computed(() => {
  if (route.path.startsWith("/demo")) return "/demo";
  if (route.path.startsWith("/models/import")) return "/models/import";
  if (route.path.startsWith("/models/perf")) return "/models/perf";
  if (route.path.startsWith("/models/scatter")) return "/models/scatter";
  if (route.path.startsWith("/models")) return "/models";
  if (route.path.startsWith("/inspect/pcb") || route.path.startsWith("/pcb/")) return "/inspect/pcb";
  if (route.path.startsWith("/inspect/solar") || route.path.startsWith("/solar/")) return "/inspect/solar";
  if (
    route.path.startsWith("/inspect/steel") ||
    route.path.startsWith("/compare") ||
    route.path.startsWith("/eval") ||
    route.path === "/detection" ||
    route.path === "/classification" ||
    route.path.startsWith("/classification/")
  ) {
    return "/inspect/steel/segmentation";
  }
  if (route.path.startsWith("/datasets")) return "/datasets";
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
    item === "/inspect/steel/segmentation" ||
    item === "/inspect/pcb" ||
    item === "/inspect/solar"
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
    navOpen.value = false;
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
  grid-template-columns: 248px 1fr;
  min-height: 100vh;
}
.side {
  background: var(--lab-rail);
  border-right: 1px solid var(--lab-line);
  box-shadow: inset -1px 0 0 color-mix(in srgb, var(--lab-fiducial) 35%, transparent);
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
  width: 34px;
  height: 34px;
  flex: none;
  color: var(--lab-fiducial);
}
.title {
  font-family: var(--lab-font-display);
  font-weight: 700;
  letter-spacing: 0.12em;
}
.sub {
  color: var(--lab-muted);
  font-size: 12px;
  margin-top: 2px;
}
.main {
  min-height: 100vh;
  background: var(--lab-canvas);
  padding: 32px 40px 56px;
}
.main.flush {
  padding: 0;
  height: 100vh;
  overflow: hidden;
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
  border-color: var(--lab-fiducial);
}
.bench-status {
  margin: 10px 20px 0;
  color: var(--lab-muted);
  font-family: var(--lab-font-mono);
  font-size: 11px;
  letter-spacing: 0.04em;
}
:deep(.el-sub-menu.models-hub > .el-sub-menu__title) {
  cursor: pointer;
}
:deep(.el-menu) {
  border-right: none !important;
}
:deep(.el-menu-item),
:deep(.el-sub-menu__title) {
  border-left: 2px solid transparent;
}
:deep(.el-menu-item:hover),
:deep(.el-sub-menu__title:hover) {
  background-color: transparent !important;
  color: var(--lab-text) !important;
}
:deep(.el-menu-item.is-active) {
  background-color: var(--lab-nav-active) !important;
  border-left-color: var(--lab-fiducial);
  color: var(--lab-fiducial) !important;
}
:deep(.el-sub-menu .el-menu) {
  background-color: var(--lab-rail) !important;
}
:deep(.el-sub-menu__title) {
  color: #e8edf1 !important;
}
:deep(.el-sub-menu.is-active > .el-sub-menu__title),
:deep(.el-sub-menu.hub-current > .el-sub-menu__title) {
  background-color: var(--lab-nav-active) !important;
  border-left-color: var(--lab-fiducial);
  color: var(--lab-accent-2) !important;
}
/* Shared light shell for the public portal and authenticated workspace. */
.light-shell {
  grid-template-columns: 238px minmax(0, 1fr);
}
.light-shell .side {
  position: sticky;
  top: 0;
  height: 100dvh;
  box-sizing: border-box;
  overflow-y: auto;
  border: 0;
  background: linear-gradient(168deg, #20364d 0%, #14283e 68%, #102238 100%);
  box-shadow: 3px 0 18px #14283e0a;
  padding-top: 0;
  --lab-text: #e8edf1;
  --lab-muted: #b1c1d3;
  --lab-line: #30465e;
  --lab-fiducial: #8bb7ff;
  --lab-accent-2: #8bb7ff;
  --lab-nav-active: #246bfd;
  color: #e8edf1;
}
.light-shell .brand {
  display: grid;
  grid-template-columns: 36px minmax(0, 1fr);
  padding: 24px 20px;
  align-items: center;
  border-bottom: 1px solid #ffffff0e;
  margin-bottom: 16px;
  gap: 6px 12px;
}
.light-shell .title {
  font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
  font-size: 26px;
  letter-spacing: .025em;
  line-height: 1.2;
}
.light-shell .sub {
  grid-column: 1 / -1;
  margin-top: 0;
  font-size: 12px;
  line-height: 1.75;
  letter-spacing: .15px;
  color: #cad9e9;
}
.brand-copy { display: contents; }
.light-shell .light-mark {
  width: 36px;
  height: 42px;
}
.light-shell .main {
  padding: 0 28px 32px;
  box-sizing: border-box;
}
.light-shell .main.flush {
  padding: 0;
}
.light-shell :deep(.el-menu-item), .light-shell :deep(.el-sub-menu__title) {
  margin: 5px 12px;
  border: 0;
  border-radius: 8px;
  height: 48px;
  font-size: 16px;
  padding-left: 19px !important;
  color: #c3d0df;
}
.light-shell :deep(.el-menu), .light-shell :deep(.el-sub-menu .el-menu) {
  background: transparent !important;
}
.light-shell :deep(.el-menu-item .el-icon), .light-shell :deep(.el-sub-menu__title > .el-icon:not(.el-sub-menu__icon-arrow)) {
  font-size: 20px;
  margin-right: 12px;
}
.light-shell :deep(.el-sub-menu .el-menu-item) {
  margin: 3px 12px 3px 24px;
  padding: 0 10px 0 22px !important;
  height: 41px;
  font-size: 14px;
  min-width: 0;
}
.light-shell :deep(.el-sub-menu.is-active > .el-sub-menu__title), .light-shell :deep(.el-sub-menu.hub-current > .el-sub-menu__title) {
  background: #ffffff0a !important;
  color: #e7f0ff !important;
}
.light-shell :deep(.el-menu-item.is-active) {
  color: #fff !important;
  background: linear-gradient(100deg, #347bff, #2566ee) !important;
  box-shadow: 0 4px 12px #07172b38;
  font-weight: 600;
}
.light-shell :deep(.el-menu-item:hover), .light-shell :deep(.el-sub-menu__title:hover) {
  background: #ffffff0c !important;
}
.light-shell .logout {
  border-radius: 7px;
  padding: 7px;
  font-size: 12px;
}
.light-shell .account {
  margin: auto 18px 0;
  padding-top: 18px;
}
.light-shell .who {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 14px;
}
.light-shell .role { margin: -3px 0 12px 42px; }
.side-avatar {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: #324f71;
  font-size: 14px;
}
.light-shell .bench-status {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  font-size: 10px;
  color: #9eb3ca;
  margin: 15px 12px 0;
}
.nav-dot { width: 5px; height: 5px; border: 1px solid currentColor; border-radius: 50%; margin-right: 11px; flex: none; opacity: .8; }
.nav-badge { font-size: 10px; line-height: 18px; padding: 0 4px; border: 1px solid #ffffff24; border-radius: 4px; margin-left: auto; color: #b6c5d5; }
.bar-account { flex-shrink: 0; }
.bar-avatar { display: grid; place-items: center; width: 34px; height: 34px; border-radius: 50%; color: white; background: #183b70; font-size: 16px; }
.bar-identity { display: grid; gap: 4px; min-width: 58px; }
.bar-identity strong { color: var(--lab-text); font-size: 14px; font-weight: 600; }
.bar-identity small { font-size: 10px; color: #71849d; }
.breadcrumb { display: flex; align-items: center; gap: 8px; }
.breadcrumb > .el-icon { font-size: 16px; color: #95a7bc; }
.breadcrumb strong { font-weight: 500; color: #3d526f; }
.light-shell .workspace-bar {
  margin: 0 -28px 24px;
  padding: 0 28px;
  background: #fff;
  border-bottom: 1px solid #e6edf5;
}
.workspace-bar {
  min-height: 66px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  border-bottom: 1px solid var(--lab-line);
  color: var(--lab-muted);
  font-size: 12px;
}
.workspace-bar > div {
  display: flex;
  align-items: center;
  gap: 16px;
}
.bar-divider {
  margin: 0 6px;
  color: #97a9bf;
}
.cpu-label {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 6px 9px;
  border: 1px solid #dce8f8;
  border-radius: 6px;
  background: #f4f8ff;
  color: #50749e;
  font-size: 11px;
}
.mobile-toggle {
  display: none;
}
@media (max-width: 800px) {
  .light-shell {
    display: block;
  }
  .light-shell .mobile-toggle {
    display: block;
    width: 100%;
    padding: 14px 20px;
    text-align: left;
    border: 0;
    background: #14283e;
    color: white;
    font: inherit;
  }
  .light-shell .side {
    display: none;
    position: static;
    height: auto;
  }
  .light-shell.nav-open .side {
    display: flex;
  }
  .light-shell .main {
    padding: 0 16px 28px;
    min-height: calc(100dvh - 50px);
  }
  .light-shell .workspace-bar {
    min-height: 58px;
    margin: 0 -16px 20px;
    padding: 0 16px;
  }
  .light-shell .main.flush {
    height: calc(100dvh - 50px);
    min-height: 0;
  }
}
@media (max-width: 520px) {
  .bar-identity, .cpu-label, .breadcrumb > .el-icon { display: none; }
  .workspace-bar { font-size: 11px; }
  .workspace-bar > div { gap: 8px; }
}
</style>

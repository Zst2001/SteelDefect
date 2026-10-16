<template>
  <div class="login">
    <section class="panel">
      <svg class="mark" viewBox="0 0 32 32" aria-hidden="true">
        <circle cx="16" cy="16" r="11" fill="none" stroke="currentColor" stroke-width="1.4" />
        <circle cx="16" cy="16" r="3.2" fill="none" stroke="currentColor" stroke-width="1.4" />
        <path d="M16 2.5v5.5M16 24v5.5M2.5 16h5.5M24 16h5.5" stroke="currentColor" stroke-width="1.4" />
      </svg>
      <p class="eyebrow">智能感知与精密工业检测实验室</p>
      <h1>对照台</h1>
      <p class="lead">在 AutoDL 训完后导入权重，于同一批图上对照内置 baseline。本站不做训练。</p>
      <el-form @submit.prevent="submitLogin">
        <el-form-item label="用户名">
          <el-input v-model="username" autocomplete="username" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="password" type="password" autocomplete="current-password" show-password />
        </el-form-item>
        <el-button type="primary" native-type="submit" :loading="loading" class="go">登录</el-button>
      </el-form>
      <p v-if="error" class="err">{{ error }}</p>
      <p class="hint">学生账号由导师开通，本站不提供自助注册。</p>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { formatError, http } from "../api/http";
import { safeAppRedirect } from "../api/redirect";

const username = ref("");
const password = ref("");
const loading = ref(false);
const error = ref("");
const router = useRouter();
const route = useRoute();

async function goHome() {
  await router.push(safeAppRedirect(route.query.redirect, "/"));
}

async function submitLogin() {
  loading.value = true;
  error.value = "";
  try {
    await http.post("/auth/login", { username: username.value.trim(), password: password.value });
    await goHome();
  } catch (err) {
    error.value = formatError(err);
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped>
.login {
  min-height: 100vh;
  display: grid;
  place-items: center;
  background: var(--lab-rail);
}
.panel {
  width: min(460px, 92vw);
  background: var(--lab-panel);
  border: 1px solid var(--lab-line);
  padding: 44px 40px;
}
.mark {
  width: 36px;
  height: 36px;
  color: var(--lab-fiducial);
  margin-bottom: 16px;
}
.eyebrow {
  color: var(--lab-fiducial);
  letter-spacing: 0.18em;
  font-size: 12px;
  margin: 0 0 8px;
  font-family: var(--lab-font-mono);
}
h1 {
  margin: 0 0 12px;
  font-size: 28px;
}
.lead,
.hint {
  color: var(--lab-muted);
  line-height: 1.6;
}
.go {
  width: 100%;
  background: var(--lab-accent);
  border-color: var(--lab-accent);
}
.err {
  color: var(--lab-danger);
}
</style>

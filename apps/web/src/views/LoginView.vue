<template>
  <div class="login">
    <section class="panel">
      <p class="eyebrow">课题组科研网站</p>
      <h1>钢铁缺陷分割对照台</h1>
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
  background:
    radial-gradient(circle at 20% 20%, rgba(196, 92, 38, 0.18), transparent 32%),
    var(--lab-bg);
}
.panel {
  width: min(440px, 92vw);
  background: var(--lab-panel);
  border: 1px solid var(--lab-line);
  padding: 36px 32px;
}
.eyebrow {
  color: var(--lab-accent-2);
  letter-spacing: 0.18em;
  text-transform: uppercase;
  font-size: 12px;
  margin: 0 0 8px;
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

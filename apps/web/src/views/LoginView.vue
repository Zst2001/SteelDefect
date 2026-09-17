<template>
  <div class="login">
    <section class="panel">
      <p class="eyebrow">课题组科研网站</p>
      <h1>钢铁缺陷分割对照台</h1>
      <p class="lead">在 AutoDL 训完后导入权重，于同一批图上对照内置 baseline。本站不做训练。</p>
      <el-tabs v-model="tab">
        <el-tab-pane label="登录" name="login">
          <el-form @submit.prevent="submitLogin">
            <el-form-item label="用户名">
              <el-input v-model="username" autocomplete="username" />
            </el-form-item>
            <el-form-item label="密码">
              <el-input v-model="password" type="password" autocomplete="current-password" show-password />
            </el-form-item>
            <el-button type="primary" native-type="submit" :loading="loading" class="go">登录</el-button>
          </el-form>
        </el-tab-pane>
        <el-tab-pane label="注册" name="register">
          <el-form @submit.prevent="submitRegister">
            <el-form-item label="用户名">
              <el-input v-model="username" autocomplete="username" placeholder="2–32 位，中文 / 字母 / 数字" />
            </el-form-item>
            <el-form-item label="密码">
              <el-input v-model="password" type="password" autocomplete="new-password" show-password placeholder="至少 8 位" />
            </el-form-item>
            <el-form-item label="确认密码">
              <el-input v-model="confirm" type="password" autocomplete="new-password" show-password />
            </el-form-item>
            <el-button type="primary" native-type="submit" :loading="loading" class="go">注册并进入</el-button>
          </el-form>
        </el-tab-pane>
      </el-tabs>
      <p v-if="error" class="err">{{ error }}</p>
      <p class="hint">注册后为学生账号。没有账号请先注册；已有账号切到登录。</p>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { formatError, http } from "../api/http";

const tab = ref("register");
const username = ref("");
const password = ref("");
const confirm = ref("");
const loading = ref(false);
const error = ref("");
const router = useRouter();
const route = useRoute();

async function goHome() {
  const redirect = typeof route.query.redirect === "string" ? route.query.redirect : "/";
  await router.push(redirect);
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

async function submitRegister() {
  loading.value = true;
  error.value = "";
  try {
    if (password.value !== confirm.value) {
      error.value = "两次输入的密码不一致";
      return;
    }
    await http.post("/auth/register", { username: username.value.trim(), password: password.value });
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
:deep(.el-tabs__active-bar) {
  background-color: var(--lab-accent);
}
:deep(.el-tabs__item.is-active),
:deep(.el-tabs__item:hover) {
  color: var(--lab-accent-2);
}
</style>

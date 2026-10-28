<template>
  <div class="login">
    <router-link class="back-link" to="/"><el-icon><ArrowLeft /></el-icon>返回实验室首页</router-link>
    <div class="login-card">
      <aside class="login-intro">
        <div class="login-brand"><svg viewBox="0 0 40 44" aria-hidden="true"><path d="M20 1 38 11 20 22 2 11Z" fill="#63c6ff"/><path d="m2 11 18 11 18-11v9L20 31 2 20Z" fill="#3897f5"/><path d="m2 28 18 11 18-11-8-5-10 6-10-6Z" fill="#2b65f5"/><path d="m20 8 8 4.5-8 4.5-8-4.5Z" fill="#17304a"/></svg><strong>IPPI LAB</strong></div>
        <p class="eyebrow">IPPI LAB · 工业视觉</p>
        <h2>钢铁表面缺陷<br />分割研究平台</h2>
        <p class="intro-copy">在同一批图像上对照模型，检查预测结果，保存实验记录。</p>
        <ul class="capabilities"><li><el-icon><Picture /></el-icon><span>原图与分割结果可视化对照</span></li><li><el-icon><DocumentChecked /></el-icon><span>固定 NEU-20 协议评测</span></li><li><el-icon><Box /></el-icon><span>学生模型隔离导入与检查</span></li></ul>
        <div class="deployment"><el-icon><Cpu /></el-icon>CPU 部署 · 本站不做训练</div>
      </aside>
      <section class="panel">
        <p class="panel-label">欢迎回来</p>
        <h1>登录实验台</h1>
        <p class="lead">使用课题组账号，继续你的实验与分析。</p>
        <el-form label-position="top" @submit.prevent="submitLogin">
          <el-form-item label="用户名"><el-input v-model="username" aria-label="用户名" autocomplete="username" placeholder="请输入用户名" /></el-form-item>
          <el-form-item label="密码"><el-input v-model="password" aria-label="密码" type="password" autocomplete="current-password" show-password placeholder="请输入密码" /></el-form-item>
          <el-button type="primary" native-type="submit" :loading="loading" class="go">登录</el-button>
        </el-form>
        <p v-if="error" class="err" role="alert">{{ error }}</p>
        <p class="hint">学生账号由导师开通，本站不提供自助注册。</p>
        <div class="guest-link"><span>先了解平台？</span><router-link to="/demo">体验公开演示 →</router-link></div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { ArrowLeft, Box, Cpu, DocumentChecked, Picture } from "@element-plus/icons-vue";
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
.login { min-height: 100dvh; box-sizing: border-box; display: flex; flex-direction: column; justify-content: center; align-items: center; padding: 40px 24px; background: radial-gradient(ellipse at 20% 10%, #e3edff, transparent 60%), #f3f6fc; }
.back-link { display: inline-flex; align-items: center; gap: 8px; width: min(920px, 100%); margin-bottom: 20px; color: #58708e; text-decoration: none; font-size: 15px; }
.login-card { display: grid; grid-template-columns: .95fr 1.05fr; width: min(920px, 100%); border: 1px solid #dce6f3; border-radius: 20px; overflow: hidden; background: #fff; box-shadow: 0 16px 60px #1d3e6b0b; }
.login-intro { padding: 42px 36px; background: linear-gradient(155deg, #203c5d, #122a43); color: #fff; display: flex; flex-direction: column; min-width: 0; }
.login-brand { display: flex; align-items: center; gap: 12px; margin-bottom: 48px; }.login-brand svg { width: 33px; height: 38px; }.login-brand strong { font-size: 28px; letter-spacing: -.6px; }
.eyebrow { margin: 0 0 15px; color: #87b4ec; font-size: 14px; letter-spacing: .14em; }
.login-intro h2 { margin: 0 0 18px; font-size: 29px; font-weight: 600; line-height: 1.55; }
.intro-copy { margin: 0; color: #bfd0e4; font-size: 16px; line-height: 1.9; }
.capabilities { list-style: none; margin: 27px 0 35px; padding: 0; display: grid; gap: 17px; font-size: 15px; color: #cad9ea; }.capabilities li { display: flex; gap: 10px; align-items: center; }.capabilities .el-icon { color: #8fbaff; font-size: 21px; }
.deployment { display: flex; gap: 8px; align-items: center; margin-top: auto; padding-top: 22px; border-top: 1px solid #ffffff18; color: #a9bfd8; font-size: 14px; }
.panel { box-sizing: border-box; min-width: 0; padding: 57px 42px 36px; }.panel-label { font-size: 15px; color: #526781; margin: 0 0 10px; }.panel h1 { margin: 0 0 12px; color: #142c47; font-size: 29px; font-weight: 650; }.lead { margin: 0 0 32px; color: #526781; line-height: 1.8; font-size: 16px; }
.panel :deep(.el-form-item) { margin-bottom: 22px; }.panel :deep(.el-form-item__label) { font-size: 16px; color: #354d6c; }.panel :deep(.el-input__wrapper) { min-height: 40px; box-sizing: border-box; padding: 0 13px; }
.go { width: 100%; min-height: 42px; margin-top: 3px; font-size: 17px; }
.hint { color: #526781; font-size: 14px; line-height: 1.8; margin: 20px 0; }.err { color: var(--lab-danger); font-size: 15px; line-height: 1.7; overflow-wrap: anywhere; }
.guest-link { display: flex; gap: 10px; flex-wrap: wrap; font-size: 15px; margin-top: 28px; padding-top: 22px; border-top: 1px solid #edf1f7; color: #526781; }.guest-link a { color: #2a69ce; text-decoration: none; }
@media(max-width:700px) { .login { padding: 24px 18px; justify-content: flex-start; }.login-card { grid-template-columns: minmax(0,1fr); border-radius: 14px; }.login-intro { padding: 22px 24px; }.login-brand { margin-bottom: 13px; }.login-brand strong { font-size: 25px; }.login-intro h2 { font-size: 25px; margin-bottom: 10px; }.login-intro h2 br { display: none; }.eyebrow, .intro-copy, .capabilities { display: none; }.deployment { padding-top: 14px; margin-top: 5px; }.panel { padding: 28px 24px; }.panel h1 { font-size: 28px; }.lead { margin-bottom: 24px; } }
</style>

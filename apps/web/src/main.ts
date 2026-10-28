import { createApp } from "vue";
import ElementPlus from "element-plus";
import zhCn from "element-plus/es/locale/lang/zh-cn";
import "element-plus/dist/index.css";
import "element-plus/theme-chalk/dark/css-vars.css";
import App from "./App.vue";
import router from "./router";
import "./styles/tokens.css";
import "./styles/workbench.css";

// The public portal and workbench now share one light theme, including teleported dialogs.
// Keep the original metallurgy and NEU class tokens in tokens.css intact.
router.afterEach((_to, _from, failure) => {
  if (failure) return;
  document.documentElement.classList.remove("dark");
  document.documentElement.classList.add("workbench-light");
});

const app = createApp(App);
app.use(router);
app.use(ElementPlus, { locale: zhCn });
app.mount("#app");

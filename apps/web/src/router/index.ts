import { createRouter, createWebHistory } from "vue-router";
import { http } from "../api/http";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/login", name: "login", component: () => import("../views/LoginView.vue"), meta: { public: true } },
    {
      path: "/",
      component: () => import("../layouts/AppLayout.vue"),
      children: [
        { path: "", name: "workbench", component: () => import("../views/WorkbenchView.vue") },
        { path: "compare/new", name: "compare-new", component: () => import("../views/compare/CompareNewView.vue") },
        { path: "compare/:taskId", name: "compare-task", component: () => import("../views/compare/CompareTaskView.vue") },
        { path: "datasets", name: "datasets", component: () => import("../views/PlaceholderView.vue"), meta: { title: "数据集", hint: "数据集中心将在后续切片完善。" } },
        { path: "datasets/:id", name: "dataset-detail", component: () => import("../views/PlaceholderView.vue"), meta: { title: "数据详情", hint: "数据版本与校验报告将在后续切片开放。" } },
        { path: "models", name: "models", component: () => import("../views/models/ModelsListView.vue") },
        { path: "models/import", name: "models-import", component: () => import("../views/models/ModelImportView.vue") },
        { path: "models/:id", name: "model-detail", component: () => import("../views/models/ModelCardView.vue") },
        { path: "eval/new", name: "eval-new", component: () => import("../views/eval/EvalNewView.vue") },
        { path: "eval/:taskId", name: "eval-task", component: () => import("../views/compare/CompareTaskView.vue") },
        { path: "records", name: "records", component: () => import("../views/PlaceholderView.vue"), meta: { title: "结果记录", hint: "记录、再跑与分享将在 Slice G 开放。" } },
        { path: "assistant", name: "assistant", component: () => import("../views/AssistantView.vue") },
        { path: "detection", name: "detection", component: () => import("../views/PlaceholderDisabledView.vue"), meta: { title: "目标检测", kind: "detection" } },
        { path: "classification", name: "classification", component: () => import("../views/PlaceholderDisabledView.vue"), meta: { title: "缺陷分类", kind: "classification" } },
        { path: "admin", name: "admin", component: () => import("../views/admin/AdminView.vue"), meta: { advisor: true } },
      ],
    },
  ],
});

router.beforeEach(async (to) => {
  if (to.meta.public) {
    return true;
  }
  try {
    const { data } = await http.get("/auth/me");
    if (to.meta.advisor && data.role !== "advisor") {
      return { name: "workbench" };
    }
    return true;
  } catch {
    return { name: "login", query: { redirect: to.fullPath } };
  }
});

export default router;

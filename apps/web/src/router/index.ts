import { createRouter, createWebHistory } from "vue-router";
import { http } from "../api/http";
import { safeAppRedirect } from "../api/redirect";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/login", name: "login", component: () => import("../views/LoginView.vue"), meta: { public: true } },
    {
      path: "/",
      component: () => import("../layouts/AppLayout.vue"),
      children: [
        { path: "", name: "home", component: () => import("../views/HomeView.vue"), meta: { public: true } },
        { path: "demo", name: "demo", component: () => import("../views/demo/DemoNewView.vue"), meta: { public: true } },
        { path: "demo/:taskId", name: "demo-task", component: () => import("../views/demo/DemoTaskView.vue"), meta: { public: true } },
        { path: "workbench", name: "workbench", component: () => import("../views/WorkbenchView.vue") },
        { path: "compare/new", redirect: "/inspect/steel/segmentation" },
        { path: "inspect/steel", redirect: "/inspect/steel/segmentation" },
        { path: "inspect/steel/:task", name: "steel-inspect", component: () => import("../views/inspect/SteelInspectView.vue") },
        { path: "inspect/pcb", name: "pcb-inspect", component: () => import("../views/PlaceholderDisabledView.vue"), meta: { title: "PCB板缺陷检测", kind: "scene-detection" } },
        { path: "inspect/solar", name: "solar-inspect", component: () => import("../views/PlaceholderDisabledView.vue"), meta: { title: "太阳能电池板缺陷检测", kind: "scene-detection" } },
        { path: "compare/:taskId", name: "compare-task", component: () => import("../views/compare/CompareTaskView.vue") },
        { path: "datasets", name: "datasets", component: () => import("../views/datasets/DatasetsListView.vue") },
        { path: "datasets/:id", name: "dataset-detail", component: () => import("../views/datasets/DatasetDetailView.vue") },
        { path: "models", name: "models", component: () => import("../views/models/ModelsListView.vue") },
        { path: "models/import", name: "models-import", component: () => import("../views/models/ModelImportView.vue") },
        { path: "models/perf", name: "models-perf", component: () => import("../views/models/ModelPerfView.vue") },
        { path: "models/scatter", name: "models-scatter", component: () => import("../views/models/ModelScatterView.vue") },
        { path: "models/:id", name: "model-detail", component: () => import("../views/models/ModelCardView.vue") },
        { path: "eval/new", name: "eval-new", component: () => import("../views/eval/EvalNewView.vue") },
        { path: "eval/:taskId", name: "eval-task", component: () => import("../views/compare/CompareTaskView.vue") },
        { path: "records", name: "records", component: () => import("../views/records/RecordsView.vue") },
        { path: "assistant", name: "assistant", component: () => import("../views/AssistantView.vue") },
        { path: "detection", redirect: "/inspect/steel/detection" },
        { path: "classification", redirect: "/inspect/steel/classification" },
        { path: "pcb/detection", redirect: "/inspect/pcb" },
        { path: "solar/detection", redirect: "/inspect/solar" },
        { path: "admin", name: "admin", component: () => import("../views/admin/AdminView.vue"), meta: { advisor: true } },
      ],
    },
  ],
});

function isPublic(to: { matched: { meta: { public?: boolean } }[] }) {
  return to.matched.some((record) => record.meta.public);
}

router.beforeEach(async (to) => {
  if (isPublic(to)) {
    if (to.name === "login") {
      try {
        await http.get("/auth/me");
        const dest = safeAppRedirect(to.query.redirect, "");
        return dest || { name: "home" };
      } catch {
        return true;
      }
    }
    return true;
  }
  try {
    const { data } = await http.get("/auth/me");
    if (to.meta.advisor && data.role !== "advisor") {
      return { name: "home" };
    }
    return true;
  } catch {
    return { name: "login", query: { redirect: to.fullPath } };
  }
});

export default router;

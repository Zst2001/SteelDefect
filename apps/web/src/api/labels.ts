import axios from "axios";
import { http } from "./http";

export function roleLabel(role: string): string {
  return role === "advisor" ? "导师" : "学生";
}

export function taskPath(type: string, id: string): string {
  if (type === "eval") return `/eval/${id}`;
  if (type === "demo") return `/demo/${id}`;
  return `/compare/${id}`;
}

export function taskStatusLabel(status: string): string {
  const map: Record<string, string> = {
    queued: "排队中",
    running: "运行中",
    success: "成功",
    failed: "失败",
    partial_success: "部分成功",
  };
  return map[status] ?? status;
}

export function failStageLabel(stage: string | null | undefined): string {
  if (!stage) return "";
  const map: Record<string, string> = {
    file: "文件",
    static: "静态扫描",
    import: "导入",
    build: "构建",
    load: "加载权重",
    forward: "前向",
    shape: "输出形状",
    resource: "资源/环境",
  };
  return map[stage] ?? stage;
}

export function modelStatusLabel(status: string): string {
  const map: Record<string, string> = {
    uploaded: "已上传",
    checking: "检查中",
    runnable: "可运行",
    cannot_start: "不能启动",
    retired: "已下架",
  };
  return map[status] ?? status;
}

async function messageFromBlob(data: Blob): Promise<string> {
  const text = await data.text();
  try {
    const parsed = JSON.parse(text) as { message?: string; stage?: string; code?: string };
    return [parsed.stage, parsed.code, parsed.message].filter(Boolean).join(" / ") || text;
  } catch {
    return text;
  }
}

export async function downloadAuthFile(path: string, filename: string): Promise<void> {
  try {
    const response = await http.get(path, { responseType: "blob" });
    const type = String(response.headers["content-type"] ?? "");
    if (type.includes("application/json")) {
      throw new Error((await messageFromBlob(response.data as Blob)) || "下载失败");
    }
    const url = URL.createObjectURL(response.data);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(url);
  } catch (error) {
    if (axios.isAxiosError(error) && error.response?.data instanceof Blob) {
      throw new Error((await messageFromBlob(error.response.data)) || error.message);
    }
    throw error;
  }
}

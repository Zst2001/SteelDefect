import axios from "axios";
import { http } from "./http";

export function roleLabel(role: string): string {
  return role === "advisor" ? "导师" : "学生";
}

export function taskPath(type: string, id: string): string {
  if (type === "classification") return `/classification/${id}`;
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

export function perfStatusLabel(status: string | null | undefined): string {
  const map: Record<string, string> = {
    unmeasured: "未测量",
    queued: "排队中",
    measuring: "测量中",
    success: "已完成",
    failed: "失败",
  };
  return map[status ?? ""] ?? status ?? "未测量";
}

export function formatParamCount(n: number | null | undefined): string {
  if (n == null) return "未测量";
  return `${(n / 1_000_000).toFixed(2)} M`;
}

export function formatBytes(n: number | null | undefined): string {
  if (n == null) return "未测量";
  if (n >= 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(1)} MB（${n.toLocaleString("en-US")} B）`;
  if (n >= 1024) return `${(n / 1024).toFixed(1)} KB（${n.toLocaleString("en-US")} B）`;
  return `${n} B`;
}

export function formatLatencyMs(ms: number | null | undefined): string {
  if (ms == null) return "未测量";
  return `${ms.toFixed(1)} ms/图`;
}

export function formatFps(n: number | null | undefined): string {
  if (n == null) return "未测量";
  return `${n.toFixed(2)} 图/秒`;
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

export async function fetchAuthBlob(url: string): Promise<Blob> {
  const path = url.replace(/^\/api/, "");
  const response = await http.get(path, { responseType: "blob" });
  const type = String(response.headers["content-type"] ?? "");
  if (type.includes("application/json")) {
    throw new Error((await messageFromBlob(response.data as Blob)) || "加载失败");
  }
  return response.data as Blob;
}

export async function postAuthBlob(path: string, body: unknown): Promise<Blob> {
  try {
    const response = await http.post(path, body, { responseType: "blob" });
    const type = String(response.headers["content-type"] ?? "");
    if (type.includes("application/json")) {
      throw new Error((await messageFromBlob(response.data as Blob)) || "生成失败");
    }
    return response.data as Blob;
  } catch (error) {
    if (axios.isAxiosError(error) && error.response?.data instanceof Blob) {
      throw new Error((await messageFromBlob(error.response.data)) || error.message);
    }
    throw error;
  }
}

export function saveBlobFile(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export function toApiPath(path: string): string {
  return path.replace(/^\/api/, "");
}

export async function openAuthFile(path: string): Promise<void> {
  const response = await http.get(toApiPath(path), { responseType: "blob" });
  const type = String(response.headers["content-type"] ?? "");
  if (type.includes("application/json")) {
    throw new Error((await messageFromBlob(response.data as Blob)) || "打开失败");
  }
  const url = URL.createObjectURL(response.data);
  const opened = window.open(url, "_blank", "noopener");
  if (!opened) {
    saveBlobFile(response.data as Blob, path.split("/").pop() || "artifact");
  }
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
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

import axios, { AxiosError } from "axios";

export type ApiError = {
  stage?: string;
  code?: string;
  message: string;
};

export const http = axios.create({
  baseURL: "/api",
  withCredentials: true,
  timeout: 120000,
});

// Keep the same key across concurrent submits or a network-error retry of the
// same request body. A successful resource response ends that submission.
const pendingSubmissions = new Map<string, string>();
function submissionSignature(url: string, data: unknown): string {
  const body = data instanceof FormData
    ? Array.from(data.entries()).map(([key, value]) => [key, value instanceof File
      ? [value.name, value.size, value.lastModified, value.type] : value])
    : data;
  return `${url}:${JSON.stringify(body)}`;
}
http.interceptors.request.use((config) => {
  const url = config.url ?? "";
  if (config.method !== "post" || !(/^\/tasks\/(compare|eval)$/.test(url)
    || url === "/demo/tasks" || url === "/classification/tasks" || url === "/models/import" || /^\/models\/[^/]+\/perf$/.test(url))) return config;
  const signature = submissionSignature(url, config.data);
  const key = pendingSubmissions.get(signature) ?? Array.from(
    crypto.getRandomValues(new Uint8Array(16)), (byte) => byte.toString(16).padStart(2, "0"),
  ).join("");
  pendingSubmissions.set(signature, key);
  config.headers.set("Idempotency-Key", config.headers.get("Idempotency-Key") ?? key);
  // Local-only metadata, never serialized into the request body or headers.
  (config as typeof config & { submissionSignature?: string }).submissionSignature = signature;
  return config;
});
http.interceptors.response.use((response) => {
  const signature = (response.config as typeof response.config & { submissionSignature?: string }).submissionSignature;
  if (signature) pendingSubmissions.delete(signature);
  return response;
}, (error: AxiosError) => {
  const signature = (error.config as (typeof error.config & { submissionSignature?: string }))?.submissionSignature;
  if (signature && error.response && error.response.status < 500) pendingSubmissions.delete(signature);
  return Promise.reject(error);
});

export function asApiError(error: unknown): ApiError {
  if (axios.isAxiosError(error)) {
    const ax = error as AxiosError<ApiError>;
    const data = ax.response?.data;
    if (data && typeof data === "object" && "message" in data) {
      return {
        stage: data.stage,
        code: data.code,
        message: data.message,
      };
    }
    return { message: ax.message, code: "HTTP", stage: "resource" };
  }
  return { message: error instanceof Error ? error.message : "未知错误", code: "UNKNOWN", stage: "resource" };
}

export function formatError(error: unknown): string {
  const parsed = asApiError(error);
  const bits = [parsed.stage, parsed.code, parsed.message].filter(Boolean);
  return bits.join(" / ");
}

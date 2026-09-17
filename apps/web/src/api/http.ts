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

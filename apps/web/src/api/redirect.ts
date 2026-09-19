export function safeAppRedirect(value: unknown, fallback = "/"): string {
  if (typeof value !== "string") return fallback;
  const trimmed = value.trim();
  if (!trimmed.startsWith("/") || trimmed.startsWith("//") || trimmed.includes("\\")) {
    return fallback;
  }
  if (trimmed.includes("://")) {
    return fallback;
  }
  return trimmed;
}

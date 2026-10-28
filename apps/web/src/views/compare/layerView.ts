export type LayerView = "mask" | "overlay" | "cam" | "error";

export function camLayers(
  artifacts: readonly { kind: string; sample_key?: string | null; url: string }[],
  sampleKey: string | undefined,
  classIds: readonly number[],
): { id: number; url: string }[] {
  if (!sampleKey) return [];
  return classIds.flatMap((id) => {
    const artifact = artifacts.find((item) => item.sample_key === sampleKey && item.kind === "montage"
      && item.url.split(/[?#]/, 1)[0].endsWith(`__cam_c${id}.png`));
    return artifact ? [{ id, url: artifact.url }] : [];
  });
}

// Availability comes exclusively from authorized artifact URLs, never has_gt.
export function chooseLayerView(requested: LayerView, available: Record<LayerView, boolean>): LayerView | null {
  if (available[requested]) return requested;
  return (["mask", "overlay", "cam", "error"] as const).find((name) => available[name]) ?? null;
}

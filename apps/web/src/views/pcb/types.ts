export const PCB_MODELS = ["unet", "unet_resnet18", "unetpp_resnet18"] as const;
export const PCB_CANCEL_NOTICE = "任务取消本期延期，当前不支持主动中止已提交任务";
export type PcbArtifactKind = "origin" | "pred_mask" | "mask_visual" | "overlay" | "boundary" | "probability" | "cam" | "gt" | "error";
export type PcbModel = { slug: string; id?: string; name: string; available: boolean; reason?: string; param_count?: number; weight_sha256?: string; protocol_hash?: string };
export type PcbCatalog = { enabled: boolean; available: boolean; models: PcbModel[]; default_model: string; max_image_bytes: number; reason?: string; input: { width: number; height: number; mode: string; formats: string[] } };
export type PcbArtifact = { kind: PcbArtifactKind; url: string; rel_path: string; sample_key: string; model_version_id?: string };
export type PcbTask = {
  id: string; type: string; scene: string; task_kind: string; status: string; has_gt: boolean; include_cam: boolean;
  model: { id: string; model_version_id?: string; name: string; weight_sha256?: string | null; protocol_hash?: string | null } | null;
  samples: { sample_key: string; filename: string; sha256?: string }[]; artifacts: PcbArtifact[];
  metrics: { available: boolean; defect_dice?: number | null; iou?: number | null; precision?: number | null; recall?: number | null; tp?: number; fp?: number; fn?: number; tn?: number };
  cam: { status: string; reason?: string | null; layer?: string | null }; error_summary?: string | null; result_download_url?: string | null;
};

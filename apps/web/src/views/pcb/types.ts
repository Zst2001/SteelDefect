export const PCB_MODELS = ["unet", "unet_resnet18", "unetpp_resnet18"] as const;
export const PCB_CANCEL_NOTICE = "任务取消本期延期，当前不支持主动中止已提交任务";
export type PcbArtifactKind = "origin" | "pred_mask" | "mask_visual" | "overlay" | "boundary" | "probability" | "cam" | "gt" | "error";
export type PcbModel = { slug: string; id?: string; name: string; available: boolean; reason?: string; param_count?: number; weight_sha256?: string; protocol_hash?: string };
export type PcbLimits = {max_images:number;max_image_bytes:number;max_batch_bytes:number;max_side:number;max_pixels:number;max_total_windows:number;tile_size:number;stride:number};
export type PcbCatalog = { enabled: boolean; available: boolean; models: PcbModel[]; default_model: string; max_image_bytes: number; reason?: string; limits?:PcbLimits; input: { width: number; height: number; mode: string; formats: string[] } };
export type PcbArtifact = { kind: PcbArtifactKind; url: string; rel_path: string; sample_key: string; model_version_id?: string };
export type PcbTask = {
  id: string; type: string; scene: string; task_kind: string; status: string; has_gt: boolean; include_cam: boolean;
  model: { id: string; model_version_id?: string; name: string; weight_sha256?: string | null; protocol_hash?: string | null } | null;
  samples: { sample_key: string; filename: string; sha256?: string; width?:number; height?:number }[]; artifacts: PcbArtifact[];
  parent_batch_id?:string; input_plan?:{width:number;height:number;window_count:number;input_adaptation:string;gray_to_rgb?:boolean;cam_supported?:boolean};
  metrics: { available: boolean; defect_dice?: number | null; iou?: number | null; precision?: number | null; recall?: number | null; tp?: number; fp?: number; fn?: number; tn?: number };
  cam: { status: string; reason?: string | null; layer?: string | null }; error_summary?: string | null; result_download_url?: string | null;
};
export type PcbBatchSample = {sample_id:string;client_file_id:string;filename:string;width:number;height:number;has_gt:boolean;windows:number;input_plan:{window_count:number;input_adaptation:string;cam_supported?:boolean};tasks:PcbTask[]};
export type PcbBatch = {batch_id:string;status:string;counts:{total:number;success:number;failed:number;queued:number;running:number};image_count:number;total_windows:number;selected_model_ids:string[];include_cam:boolean;samples:PcbBatchSample[];open_path:string;pagination?:{page:number;page_size:number;total:number;has_more:boolean}};

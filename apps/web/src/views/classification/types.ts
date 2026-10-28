export type ClassLabel = { id: number; key: string; display_zh: string };
export type ClassificationModel = {
  slug: string; name: string; available: boolean; status: string; reason: string | null;
  param_count: number | null; classes: ClassLabel[]; protocol_hash?: string; weight_sha256?: string;
};
export type ClassificationCatalog = {
  models: ClassificationModel[]; default_model: string; max_images: number; max_models: number; max_image_bytes: number;
};
export type Score = { class_id: number; key: string; display_zh: string; score: number };
export type Prediction = Score & { sample_key: string; model_version_id: string; model_slug: string; topk: Score[]; scores: number[] };
export type ClassificationTask = {
  id: string; type: "classification"; status: string; has_gt: boolean; n: number; error_summary: string | null;
  classes: ClassLabel[];
  models: Array<{ model_version_id: string; slug: string; name: string; status: string; fail_message?: string | null }>;
  samples: Array<{ sample_key: string; filename: string; preview_url?: string | null; class_id?: number | null }>;
  predictions: Prediction[];
  metrics: { available: boolean; n?: number; models?: Array<{ model_version_id: string; accuracy: number; macro_f1: number; confusion_matrix: number[][] }> };
  result_download_url?: string | null;
};

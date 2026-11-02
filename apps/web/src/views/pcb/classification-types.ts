export type RoiClass = { class_id:number; label_en:string; label_zh:string };
export type RoiCatalog = { enabled:boolean; available:boolean; models:{model_id:string; name:string; params:number; available:boolean; default:boolean}[]; default_model:string; classes:RoiClass[]; max_image_bytes:number; message:string };
export const ROI_PROTOCOL = "pcb_cls_deeppcb_roi_v0";
export type RoiPrediction = RoiClass & {
  task_id:string; model_id:string; protocol_id:string;
  confidence:number; probabilities:number[]; input_adapted:boolean;
  adaptation_notice?:string; sample_sha256:string;
};
export type RoiTask = { id:string; type:string; scene:string; task_kind:string; status:string; error_summary?:string; model?:{id:string;name:string}; classes:RoiClass[]; input:{width:number;height:number;input_adapted:boolean;adaptation_notice?:string}; protocol_id:string; result?:RoiPrediction | null; artifacts:{kind:string;url:string}[]; result_download_url?:string };

// Both the rendered summary and the separately downloaded artifact must belong
// to this task. TypeScript annotations do not validate JSON received over HTTP.
export function checkedRoiResult(task:RoiTask | null, prediction:unknown = task?.result):RoiPrediction | null {
  if (!task || !prediction || typeof prediction !== "object") return null;
  const r = prediction as RoiPrediction, labels = task.classes;
  if (task.protocol_id !== ROI_PROTOCOL || r.protocol_id !== task.protocol_id ||
      r.task_id !== task.id || !task.model?.id || r.model_id !== task.model.id ||
      !Array.isArray(labels) || labels.length !== 6 ||
      !labels.every((c,i) => c && c.class_id === i && typeof c.label_en === "string" && !!c.label_en && typeof c.label_zh === "string" && !!c.label_zh) ||
      !Array.isArray(r.probabilities) || r.probabilities.length !== 6 ||
      !r.probabilities.every(v => Number.isFinite(v) && v >= 0 && v <= 1) ||
      Math.abs(r.probabilities.reduce((a,b) => a+b,0)-1) > .00001 ||
      !Number.isInteger(r.class_id) || r.class_id < 0 || r.class_id > 5 ||
      r.probabilities.indexOf(Math.max(...r.probabilities)) !== r.class_id ||
      r.confidence !== r.probabilities[r.class_id] ||
      labels[r.class_id].label_en !== r.label_en || labels[r.class_id].label_zh !== r.label_zh ||
      typeof r.input_adapted !== "boolean" || typeof r.sample_sha256 !== "string" || !/^[a-f0-9]{64}$/.test(r.sample_sha256)) return null;
  return r;
}

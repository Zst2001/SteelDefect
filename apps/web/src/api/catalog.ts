import { http } from "./http";

export type TaskType = "classification" | "detection" | "segmentation";

export type CatalogStats = {
  research_models: number;
  papers: number;
  updated_at: string;
};

export type CatalogModel = {
  id: string;
  name: string;
  year: number | null;
  task_type: TaskType;
  backbone: string | null;
  keywords: string | null;
  paper_url: string | null;
  code_url: string | null;
  dataset: string | null;
  detail: string | null;
  is_group_work: boolean;
  sort_order: number;
};

export type CatalogDataset = {
  id: string;
  name: string;
  task_type: TaskType;
  source_object: string | null;
  numbers_text: string | null;
  image_count: number | null;
  class_count: number | null;
  defect_types: string | null;
  size: string | null;
  url: string | null;
  access_note: string | null;
  detail: string | null;
  sort_order: number;
};

export type CatalogPayload = {
  stats: CatalogStats;
  models: CatalogModel[];
  datasets: CatalogDataset[];
  works: CatalogWork[];
  funds: CatalogFund[];
};

export type WorkKind = "paper" | "patent" | "software" | "award" | "other";
export type FundSource = "nsfc" | "provincial" | "ministry" | "horizontal" | "other";
export type FundRole = "pi" | "participant";
export type FundStatus = "ongoing" | "completed";

export type CatalogWork = {
  id: string;
  name: string;
  kind: WorkKind;
  year: number | null;
  venue: string | null;
  authors: string | null;
  summary: string | null;
  link_url: string | null;
  sort_order: number;
};

export type CatalogFund = {
  id: string;
  name: string;
  source: FundSource;
  number: string | null;
  role: FundRole;
  start_year: number | null;
  end_year: number | null;
  status: FundStatus;
  amount_text: string | null;
  detail: string | null;
  sort_order: number;
};

export const TASK_LABELS: Record<TaskType | "all", string> = {
  all: "全部",
  classification: "分类",
  detection: "检测",
  segmentation: "分割",
};

export const WORK_KIND_LABELS: Record<WorkKind, string> = {
  paper: "论文",
  patent: "专利",
  software: "软件著作权",
  award: "奖项",
  other: "其他成果",
};

export const FUND_SOURCE_LABELS: Record<FundSource, string> = {
  nsfc: "国家自然科学基金",
  provincial: "省部级基金",
  ministry: "部委项目",
  horizontal: "横向课题",
  other: "其他项目",
};

export const FUND_ROLE_LABELS: Record<FundRole, string> = {
  pi: "主持人",
  participant: "参与",
};

export const FUND_STATUS_LABELS: Record<FundStatus, string> = {
  ongoing: "在研",
  completed: "已结题",
};

export const TASK_FILTERS: Array<TaskType | "all"> = ["all", "classification", "detection", "segmentation"];

export function keywordTags(keywords: string | null | undefined): string[] {
  if (!keywords) {
    return [];
  }
  return keywords
    .split(/[;；,，]/)
    .map((part) => part.trim())
    .filter(Boolean);
}

export function taskLabel(task: TaskType): string {
  return TASK_LABELS[task];
}

export function filterByTask<T extends { task_type: TaskType }>(items: T[], task: TaskType | "all"): T[] {
  if (task === "all") {
    return items;
  }
  return items.filter((item) => item.task_type === task);
}

export async function fetchCatalog(): Promise<CatalogPayload> {
  const { data } = await http.get("/catalog");
  return data;
}

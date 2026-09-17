export type OpenModel = {
  name: string;
  year: number;
  backbone: string;
  keywords: string;
  codeUrl: string;
};

export type OpenDataset = {
  name: string;
  object: string;
  numbers: string;
  size: string;
  url: string;
  accessNote?: string;
};

const NEU_LINK = "http://faculty.neu.edu.cn/songkc/en/zdylm/263265";
const MVIT_LINK = "https://github.com/clovermini/MVIT_metal_datasets";

export const segmentationModels: OpenModel[] = [
  {
    name: "EAMINet",
    year: 2021,
    backbone: "ResNet-34",
    keywords: "multi-level feature; fusion, edge",
    codeUrl: "https://github.com/zxforchid/Edge-Aware-Multi-Level-Interactive-Network",
  },
  {
    name: "DACNet",
    year: 2022,
    backbone: "ResNet-34",
    keywords: "Cascaded network; dense attention",
    codeUrl: "https://github.com/zxforchid/DACNet",
  },
  {
    name: "CPANet",
    year: 2023,
    backbone: "ResNet-50",
    keywords: "few-shot learning; cross position Aggregation network",
    codeUrl: "https://github.com/VDT-2048/CPANet",
  },
  {
    name: "Benchmark",
    year: 2024,
    backbone: "Transformer; CNN",
    keywords: "Machine vision; Automated inspection",
    codeUrl: "https://github.com/djene-mengistu/dseg_models",
  },
  {
    name: "DMRAN",
    year: 2024,
    backbone: "U2Net",
    keywords: "Attention mechanism",
    codeUrl: "https://github.com/zz-ux/Metal-surface-defect-detection",
  },
  {
    name: "DDFNet",
    year: 2025,
    backbone: "MPARNet",
    keywords: "Dual-branch decoder; Multi-scale attention fusion",
    codeUrl: "https://github.com/13140W/DDFNet",
  },
  {
    name: "MINet",
    year: 2024,
    backbone: "-",
    keywords: "computational cost; multi-scale",
    codeUrl: "https://github.com/Kunye-Shen/MINet",
  },
  {
    name: "DFPANet",
    year: 2025,
    backbone: "ResNet34",
    keywords: "edge-guided; multiscale fusion",
    codeUrl: "https://github.com/hpguo1982/DFPANet",
  },
  {
    name: "SME-DeepLabV3+",
    year: 2025,
    backbone: "StarNet",
    keywords: "Multi-scale attention; Star operation",
    codeUrl: "https://github.com/Eric-863/SME-main/tree/main",
  },
];

export const classificationDatasets: OpenDataset[] = [
  {
    name: "NEU-CLS",
    object: "Hot rolled steel strip",
    numbers: "1800 images (6 defect types, 300 samples each)",
    size: "200×200 pixels",
    url: NEU_LINK,
  },
  {
    name: "NEU-CLS-64",
    object: "Hot rolled steel strip",
    numbers: "9 defect types",
    size: "64×64 pixels",
    url: NEU_LINK,
  },
  {
    name: "X-SSD",
    object: "Hot rolled steel strip",
    numbers: "7 typical defects, 1360 defect images",
    size: "640×640 pixels",
    url: "https://github.com/Fighter20092392/X-SDD-A-New-benchmark",
  },
  {
    name: "SteelBlastQC",
    object: "Sandblasted steel surface",
    numbers: "1654 images",
    size: "512×512 pixels",
    url: "https://www.selectdataset.com/dataset/82d51b3d89d46f589afda3aa1600de21",
  },
  {
    name: "MSD-CLS",
    object: "Steel",
    numbers: "500 images (10 defect types, 50 samples each)",
    size: "224×224 pixels",
    url: "https://github.com/successhaha/Gtnet",
  },
];

export const detectionDatasets: OpenDataset[] = [
  {
    name: "NEU-DET",
    object: "Hot rolled steel strip",
    numbers: "1800 images (6 defect types, 300 samples each)",
    size: "200×200 pixels",
    url: NEU_LINK,
  },
  {
    name: "GC10-DET",
    object: "Steel strip",
    numbers: "3570 images with 10 defect types",
    size: "2048×1000 pixels",
    url: "https://github.com/lvxiaoming2019/GC10-DET-Metallic-Surface-Defect-Datasets",
  },
  {
    name: "Severstal-steel-defect",
    object: "Steel strip",
    numbers: "6666 grayscale images (4 defect types)",
    size: "800×128 pixels",
    url: "https://www.kaggle.com/c/severstal-steel-defect-detection/data",
  },
  {
    name: "MHPSDS",
    object: "Medium and Heavy Plate",
    numbers: "4 typical defects, 680 images",
    size: "256×256 pixels",
    url: MVIT_LINK,
  },
  {
    name: "Casting Billet Dataset",
    object: "Casting Billet",
    numbers: "6 typical defects, 1060 images",
    size: "96×106 to 3228×492",
    url: MVIT_LINK,
  },
  {
    name: "Steel Pipe Dataset",
    object: "Steel Pipe",
    numbers: "4 typical defects, 1,227 images",
    size: "728×544 pixels",
    url: MVIT_LINK,
  },
];

export const segmentationDatasets: OpenDataset[] = [
  {
    name: "NEU_Seg",
    object: "Hot rolled steel strip",
    numbers: "4470 images (3 defect types)",
    size: "200×200 pixels",
    url: NEU_LINK,
  },
  {
    name: "KolektorSDD2",
    object: "Multiple types",
    numbers: "Training: 2,085; Test: 1,004",
    size: "230×630 pixels",
    url: "https://modelscope.cn/datasets/OpenDataLab/KolektorSDD2",
  },
  {
    name: "BSData",
    object: "Ball Screw",
    numbers: "1104 three-channel images",
    size: "multiple pixels",
    url: "https://hf-mirror.com/datasets/Gssmc/BSData",
  },
  {
    name: "RSDDs dataset",
    object: "Rail surface",
    numbers: "2 types (67 images; 128 images)",
    size: "multiple pixels",
    url: "https://aistudio.baidu.com/dataset/detail/97732/file",
  },
  {
    name: "SD-saliency-900",
    object: "Bar Steel",
    numbers: "900 images",
    size: "200×200 pixels",
    url: "https://github.com/SongGuorong/MCITF/tree/master/SD-saliency-900",
  },
  {
    name: "FSSD-12",
    object: "Steel strip",
    numbers: "12 typical defects, 50 samples each",
    size: "200×200 pixels",
    url: "https://pan.baidu.com/s/15k5QQXX8Ha7yXNcdWQvV5Q?pwd=pfnc",
    accessNote: "提取码 pfnc",
  },
  {
    name: "Severstal Steel Defect",
    object: "Steel strip",
    numbers: "Training: 5280; Test: 5506",
    size: "1600×256 pixels",
    url: "https://pan.baidu.com/s/1U9KIqbNx9F1Sv7MTH_PzXQ?pwd=ydc3",
    accessNote: "提取码 ydc3",
  },
];

export const classificationPrivatePaths = [
  'assets/PCB_fenlei/pcb_cls_deeppcb_roi_v0_formal_v1.zip',
  'assets/PCB_fenlei/pcb_cls_deeppcb_roi_v0_formal_v1.zip.sha256',
  ...['models/efficientnet_b0.pth','models/mobilenet_v3_small.pth','MANIFEST.json',
      'config/classes.json','config/preprocess.json','config/model_spec.json',
      'runtime/inference.py','runtime/model_factory.py','runtime/preprocess.py',
      'runtime/smoke_test.py','validation/cpu_smoke_results.json','validation/inference_consistency.json',
      '.windows-admission.json'].map(p=>'assets/pcb_classification/deeppcb_roi_v0_formal_v1/'+p),
  'packages/infer/pcb_classification/runtime.py',
];

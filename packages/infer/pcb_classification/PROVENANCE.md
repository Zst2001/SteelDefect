# PCB 单缺陷 ROI 六分类部署代码

来源：用户提供的 `pcb_cls_deeppcb_roi_v0_formal_v1.zip`，固定 ZIP SHA-256 为
`bfb1c0ce379a47b5ac9acaa11c990042b1d75eddc99dfd55479a0f619316d8ba`。
原始包与 sidecar 保存在本机私有 `assets/PCB_fenlei/`；解包文件保存在
`assets/pcb_classification/deeppcb_roi_v0_formal_v1/`，均不加入 Git 或前端产物。

已审阅原包四个 runtime 模块。部署模块固定构造 torchvision EfficientNet-B0
与 MobileNetV3-Small 的六分类头，保持原始灰度 / 双线性 / float32 标准化 / softmax。
`images.py` 额外实施上传字节、像素、格式、MIME、EXIF 与单帧约束；`runtime.py`
改为单模型进程缓存，不执行上传脚本，不动态导入包内 Python，不下载预训练权重。
`catalog.py` 可供 API 使用，不导入 Torch；冻结清单校验、私有 Windows CPU 回执和
文件身份共同决定可用性。文件身份改变时重新核验，代码改变需重启并重新准入。

类别顺序与 mean/std 从已通过冻结哈希验证的原包配置读取。正式任务不生成 Accuracy、
Macro-F1 或无缺陷概率，预览是 224×224 灰度 ROI，不是检测框、分割或解释图层。
缓存依据本机文件 stat 和哈希，防止意外替换与过期准入，不声称抵御恶意操作系统管理员。

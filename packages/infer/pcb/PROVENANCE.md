# PCB trusted inference source

Source: private `pcb_seg_meiwei_v2_formal_v1.zip`, SHA-256 `7c93a1f299f7e2b998ee1c8473ce9f3b6b700487247d4c069a69ec0240549c1d`.
The source archive and metadata remain unchanged. This directory is reviewed project code, never dynamically imported from an uploaded or asset path.

| Source file | SHA-256 | Deployment changes |
|---|---|---|
| trusted_models.py | `f36e2b509030b607ea621cb80be6a424cc88b66f4003ec8b710d67a02c9b0a7b` | Removed unused pretrained encoder loader (including unsafe pickle fallback), hash helper and training-only constants/imports. Constructors and forward operations unchanged. |
| pcb_preprocess.py | `6bbc7c6560a33353c8816c67fc64de48c43e5662e2133b2191e3894cbbc45a18` | Byte-identical copy. |
| pcb_postprocess.py | `6912b6d45ff0752c58ac4894ca9e1e1a88b09cda7fe69bf769e33bcad405a338` | Byte-identical copy. |
| pcb_visualize.py | `4ffa0d0d68467bb2f1761c29eaf412e395acca01595c159723adb54b55acffd0` | Package-relative imports; per-call CAM hooks and gradient state cleaned in finally. Numerical target and operations unchanged. |

Admission is not website enablement. License notes restrict redistribution of weights and data.

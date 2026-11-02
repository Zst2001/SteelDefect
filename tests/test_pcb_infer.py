"""Synthetic-only PCB contract tests; no private weights, DB or services.

Run directly: .venv/Scripts/python.exe -B tests/test_pcb_infer.py
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages"))
import numpy as np
import torch
from infer.pcb import runtime
from infer.pcb import catalog as admission
from infer.pcb.preprocess import ContractError as InputError, prepare_canvas
from infer.pcb.postprocess import ContractError as OutputError, mask_and_probability
from infer.pcb.visualize import ContractError as VisualError, SegmentationGradCAM, error_map, predict_layers

torch.set_num_threads(2)


class TinyModel(torch.nn.Module):
    """Differentiable controlled foreground; no real weights or dataset."""
    def __init__(self, empty=False):
        super().__init__()
        self.dec1 = torch.nn.Conv2d(3, 2, 1)
        self.cam_layer_name = "dec1"
        self.empty = empty
        with torch.no_grad():
            self.dec1.weight.fill_(1)
            self.dec1.bias[0] = 2 if empty else 0
            self.dec1.bias[1] = 0 if empty else 2

    def forward(self, x):
        return self.dec1(x)


class PcbInferenceTests(unittest.TestCase):
    def test_preprocess_zero_padding_color_and_scale(self):
        image = np.zeros((220, 220, 3), dtype=np.uint8)
        image[:] = (255, 128, 1)
        t = prepare_canvas(image)
        self.assertEqual(tuple(t.shape), (1, 3, 256, 256))
        self.assertEqual(t.dtype, torch.float32)
        self.assertTrue(torch.equal(t[0, :, 18, 18], torch.tensor([255, 128, 1]) / 255))
        self.assertEqual(int(torch.count_nonzero(t[:, :, :18, :])), 0)
        self.assertEqual(int(torch.count_nonzero(t[:, :, 238:, :])), 0)
        self.assertEqual(int(torch.count_nonzero(t[:, :, :, :18])), 0)
        self.assertEqual(int(torch.count_nonzero(t[:, :, :, 238:])), 0)

    def test_input_rejects_other_size_channel_dtype(self):
        for image in (np.zeros((200, 200, 3), np.uint8), np.zeros((220, 220, 4), np.uint8),
                      np.zeros((220, 220), np.uint8), np.zeros((220, 220, 3), np.float32)):
            with self.subTest(shape=image.shape, dtype=image.dtype), self.assertRaises(InputError):
                prepare_canvas(image)

    def test_crop_excludes_padding_and_preserves_coordinates(self):
        logits = torch.zeros((1, 2, 256, 256))
        logits[:, 1] = 10  # artificial padding foreground
        logits[:, 1, 18:238, 18:238] = -10
        logits[:, 1, 21, 25] = 10
        mask, prob = mask_and_probability(logits)
        self.assertEqual(int(mask.sum()), 1)
        self.assertEqual(int(mask[3, 7]), 1)
        self.assertGreater(float(prob[3, 7]), .99)

    def test_invalid_logits_shape(self):
        for shape in ((1, 4, 256, 256), (1, 2, 220, 220), (2, 256, 256)):
            with self.subTest(shape=shape), self.assertRaises(OutputError):
                mask_and_probability(torch.zeros(shape))

    def test_no_gt_has_no_error_or_metric_and_images_aligned(self):
        layers = predict_layers(TinyModel().eval(), np.full((220, 220, 3), 80, np.uint8))
        self.assertEqual(set(layers), {"logits", "pred_mask", "probability", "probability_heatmap", "overlay", "boundary"})
        self.assertEqual(layers["pred_mask"].dtype, np.uint8)
        self.assertEqual(layers["probability"].dtype, np.float32)
        for key in ("overlay", "boundary", "probability_heatmap"):
            self.assertEqual(layers[key].shape, (220, 220, 3))
            self.assertEqual(layers[key].dtype, np.uint8)

    def test_error_map_requires_binary_gt_and_exact_colors(self):
        gt = np.zeros((220, 220), np.uint8)
        pred = gt.copy()
        gt[0, 0] = pred[0, 0] = 1
        gt[0, 1] = pred[0, 2] = 1
        error = error_map(gt, pred)
        self.assertEqual(error[0, 0].tolist(), [40, 180, 70])
        self.assertEqual(error[0, 1].tolist(), [40, 90, 220])
        self.assertEqual(error[0, 2].tolist(), [220, 40, 40])
        for bad in (np.zeros((200, 200), np.uint8), np.full((220, 220), 2, np.uint8)):
            with self.assertRaises(VisualError):
                error_map(bad, pred)

    def test_nonfinite_logits_fail_before_layers(self):
        model = TinyModel()
        with patch.object(model, "forward", return_value=torch.full((1, 2, 256, 256), float("nan"))):
            with self.assertRaises(VisualError):
                predict_layers(model, np.zeros((220, 220, 3), np.uint8))

    def test_cam_no_foreground_and_hooks_released(self):
        model = TinyModel(empty=True)
        cam = SegmentationGradCAM(model)
        for _ in range(3):
            answer = cam(np.zeros((220, 220, 3), np.uint8))
            self.assertEqual(answer["status"], "unavailable")
            self.assertNotIn("map", answer)
            self.assertFalse(model.dec1._forward_hooks)
            self.assertFalse(model.dec1._backward_hooks)
            self.assertIsNone(cam.fmap)

    def test_cam_hooks_and_grad_state_cleaned_on_exception(self):
        model = TinyModel()
        model.requires_grad_(False)
        cam = SegmentationGradCAM(model)
        with patch.object(cam, "_compute", side_effect=RuntimeError("synthetic failure")):
            with self.assertRaises(RuntimeError):
                cam(np.zeros((220, 220, 3), np.uint8))
        self.assertFalse(model.dec1._forward_hooks)
        self.assertFalse(model.dec1._backward_hooks)
        self.assertTrue(all(not p.requires_grad and p.grad is None for p in model.parameters()))

    def test_cam_success_and_probability_are_different_layers(self):
        image = np.zeros((220, 220, 3), np.uint8)
        image[30:80] = 200
        model = TinyModel().eval()
        cam = SegmentationGradCAM(model)(image)
        self.assertEqual(cam["status"], "ok")
        self.assertEqual(cam["map"].shape, (220, 220))
        self.assertTrue(np.isfinite(cam["map"]).all())
        self.assertFalse(np.array_equal(cam["map"], predict_layers(model, image)["probability"]))

    def test_unrecognized_model_never_opens_path(self):
        with patch.object(Path, "open", side_effect=AssertionError("must not open")):
            for name in ("../unet", "mobilenet_v3_small", "steel", "deeplabv3plus_resnet18"):
                with self.assertRaises(ValueError):
                    runtime.load_model(name)

    def test_weight_change_rejected_before_deserialization(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / "models/unet/weights.pth"
            path.parent.mkdir(parents=True)
            path.write_bytes(b"not-real-weights")
            with patch.object(torch, "load", side_effect=AssertionError("must not deserialize")):
                with self.assertRaisesRegex(ValueError, "SHA-256"):
                    runtime.load_model("unet", root)

    def test_safe_loader_has_no_typeerror_pickle_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / "models/unet/weights.pth"
            path.parent.mkdir(parents=True)
            blob = b"synthetic-hash-fixture"
            path.write_bytes(blob)
            identity = (hashlib.sha256(blob).hexdigest(), 7849634, "dec1")
            with patch.dict(runtime.MODELS, unet=identity), patch.object(torch, "load", side_effect=TypeError("unsupported")) as load:
                with self.assertRaises(TypeError):
                    runtime.load_model("unet", root)
                self.assertEqual(load.call_count, 1)
                self.assertEqual(load.call_args.kwargs, {"map_location": "cpu", "weights_only": True})

    def test_strict_loading_rejects_missing_tensor(self):
        from infer.pcb import models
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / "models/unet/weights.pth"
            path.parent.mkdir(parents=True)
            blob = b"synthetic-hash-fixture"
            path.write_bytes(blob)
            identity = (hashlib.sha256(blob).hexdigest(), 8, "dec1")
            model = TinyModel()
            with patch.dict(runtime.MODELS, unet=identity), patch.object(torch, "load", return_value={"dec1.bias": model.dec1.bias}), patch.object(models, "build_model", return_value=model):
                with self.assertRaisesRegex(RuntimeError, "Missing key"):
                    runtime.load_model("unet", root)

    def test_admission_rejects_changed_frozen_manifest(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "ASSET_MANIFEST.json").write_text('{"files":[]}', encoding="utf-8")
            with self.assertRaisesRegex(admission.PcbAdmissionError, "指纹"):
                admission.verify_staging(root)

    def test_catalog_all_models_unavailable_when_admission_missing(self):
        with tempfile.TemporaryDirectory() as folder:
            rows = admission.catalog(Path(folder))
            self.assertEqual(len(rows), 3)
            self.assertTrue(all(not r["available"] for r in rows))

    def test_receipt_requires_every_model_current_runtime_source_and_no_foreground_difference(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "assets"
            root.mkdir()
            path = admission.receipt_path(root)
            original = {"status": "VERIFIED_FOR_STAGING", "manifest_sha256": admission.MANIFEST_SHA256,
                        "protocol_hash": admission.PROTOCOL_HASH, "source_hashes": {"test": "hash"},
                        "runtime": {"test": "version"}, "threads": 2, "interop": 6, "mkldnn": True,
                        "models": {name: {"status": "VERIFIED_FOR_STAGING", "weight_sha256": item[0],
                           "cross_passed": True, "foreground_mismatch": 0, "structural_forward_passed": True,
                           "layers_cam_passed": True} for name, item in runtime.MODELS.items()}}
            with patch.object(admission, "verify_staging", return_value={}), patch.object(admission, "source_hashes", return_value={"test": "hash"}), patch.object(admission, "runtime_versions", return_value={"test": "version"}):
                path.write_text(json.dumps(original), encoding="utf-8")
                self.assertEqual(admission.require_admitted(root)["status"], "VERIFIED_FOR_STAGING")
                for key, bad in (("runtime", {}), ("source_hashes", {}), ("threads", 6), ("interop", 1), ("models", {})):
                    changed = {**original, key: bad}
                    path.write_text(json.dumps(changed), encoding="utf-8")
                    with self.subTest(key=key), self.assertRaises(admission.PcbAdmissionError):
                        admission.require_admitted(root)
                changed = json.loads(json.dumps(original))
                changed["models"]["unet"]["foreground_mismatch"] = 1
                path.write_text(json.dumps(changed), encoding="utf-8")
                with self.assertRaises(admission.PcbAdmissionError):
                    admission.require_admitted(root)


if __name__ == "__main__":
    unittest.main(verbosity=2)

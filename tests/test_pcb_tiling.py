"""Synthetic pointwise-model tests: no private weights, services or dataset."""
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages"))
import numpy as np
import torch
from infer.pcb import tiling
from infer.pcb.visualize import predict_layers, error_map as original_error_map


class Pointwise(torch.nn.Module):
    def forward(self, x):
        return torch.cat((torch.zeros_like(x[:, :1]), x[:, :1] - .5), dim=1)


class TilingTests(unittest.TestCase):
    def test_limits_and_modes(self):
        limits = tiling.limits()
        self.assertEqual(limits["max_window_model_budget"], 500)
        self.assertEqual(limits["max_images"], 10)
        self.assertTrue(tiling.plan(220, 220)["cam_supported"])
        self.assertFalse(tiling.plan(220, 220, "L")["cam_supported"])
        self.assertTrue(tiling.plan(220, 220, "L")["gray_to_rgb"])
        self.assertEqual(tiling.plan(110, 110)["input_adaptation"], "pad_to_220")
        self.assertEqual(tiling.plan(221, 110)["input_adaptation"], "sliding_window")

    def test_invalid_dimensions_or_mode(self):
        for width, height, mode in [(0, 2, "RGB"), (-1, 220, "RGB"), (2049, 1, "RGB"),
                                     (1, 2049, "RGB"), (True, 1, "RGB"), (1.0, 1, "RGB"),
                                     (220, 220, "RGBA"), (220, 220, "I;16"), (220, 220, "CMYK")]:
            with self.subTest(width=width, height=height, mode=mode), self.assertRaises(ValueError):
                tiling.plan(width, height, mode)

    def test_full_coverage_and_last_tile(self):
        for width, height in [(1, 1), (110, 110), (220, 220), (221, 300), (512, 384),
                              (1024, 1024), (2048, 220), (110, 2048), (2048, 2048)]:
            with self.subTest(size=(width, height)):
                plan = tiling.plan(width, height)
                coverage = np.zeros((max(height, 220), max(width, 220)), dtype=np.uint16)
                for x, y in plan["windows"]:
                    coverage[y:y+220, x:x+220] += 1
                self.assertTrue(np.all(coverage > 0))
                self.assertEqual(plan["x_starts"][-1]+220, max(width, 220))
                self.assertEqual(plan["y_starts"][-1]+220, max(height, 220))
                self.assertEqual(plan["window_count"], len(plan["windows"]))

    def test_native_path_bitwise_identical(self):
        image = np.random.default_rng(1).integers(0, 256, size=(220, 220, 3), dtype=np.uint8)
        old = predict_layers(Pointwise(), image)
        new, meta = tiling._predict_loaded(Pointwise(), image)
        self.assertEqual(set(old), set(new))
        for key in old:
            np.testing.assert_array_equal(np.asarray(old[key]), np.asarray(new[key]))
        self.assertEqual(meta["blend"], "native")

    def test_pointwise_stitching_has_no_seams_or_padding_border(self):
        for width, height in [(110, 110), (221, 300), (512, 384), (110, 400), (1024, 1024)]:
            with self.subTest(size=(width, height)):
                yy, xx = np.indices((height, width))
                image = np.stack(((xx*3+yy*7)%256, xx%256, yy%256), axis=2).astype(np.uint8)
                layers, meta = tiling._predict_loaded(Pointwise(), image)
                np.testing.assert_array_equal(layers["pred_mask"], (image[:, :, 0] > 127).astype(np.uint8))
                expected = torch.sigmoid(torch.from_numpy(image[:, :, 0].astype(np.float32))/255-.5).numpy()
                np.testing.assert_allclose(layers["probability"], expected, atol=2e-7, rtol=0)
                self.assertGreater(meta["coverage_min"], 0)
                for key in ("overlay", "boundary", "probability_heatmap"):
                    self.assertEqual(layers[key].shape, (height, width, 3))
                np.testing.assert_allclose(layers["probabilities"].sum(axis=0), 1, atol=1e-6, rtol=0)

    def test_background_and_thin_objects_survive_seams(self):
        image = np.zeros((384, 512, 3), dtype=np.uint8)
        image[175:178, :, 0] = 255
        image[:, 351:354, 0] = 255
        image[-1, :, 0] = 255
        image[:, -1, 0] = 255
        layers, _ = tiling._predict_loaded(Pointwise(), image)
        np.testing.assert_array_equal(layers["pred_mask"], (image[:, :, 0] == 255).astype(np.uint8))
        layers, _ = tiling._predict_loaded(Pointwise(), np.zeros_like(image))
        self.assertEqual(int(layers["pred_mask"].sum()), 0)

    def test_bad_arrays_and_nonfinite_logits(self):
        for image in [np.zeros((220, 220), np.uint8), np.zeros((220, 220, 4), np.uint8),
                      np.zeros((220, 220, 3), np.float32)]:
            with self.assertRaises(ValueError): tiling._predict_loaded(Pointwise(), image)
        for output in (torch.zeros(1, 3, 256, 256), torch.full((1, 2, 256, 256), float("nan")),
                       torch.full((1, 2, 256, 256), float("inf"))):
            with self.assertRaises(ValueError):
                tiling._predict_loaded(lambda x: output, np.zeros((110, 110, 3), np.uint8))

    def test_source_change_rejected_even_before_first_prediction(self):
        with patch.object(tiling, "source_hash", return_value="changed"):
            with self.assertRaises(ValueError): tiling.plan(220, 220)
            with self.assertRaises(ValueError): tiling.assert_current_source()

    def test_error_map_preserves_colors_and_supports_original_size(self):
        gt = np.zeros((220, 220), np.uint8); gt[5:15] = 1
        pred = np.zeros_like(gt); pred[10:20] = 1
        np.testing.assert_array_equal(tiling.error_map(gt, pred), original_error_map(gt, pred))
        self.assertEqual(tiling.error_map(gt[:110], pred[:110]).shape, (110, 220, 3))
        with self.assertRaises(ValueError): tiling.error_map(gt[:110], pred)
        with self.assertRaises(ValueError): tiling.error_map(np.full_like(gt, 2), pred)


if __name__ == "__main__":
    torch.set_num_threads(2)
    unittest.main()

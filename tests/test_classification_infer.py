"""Offline contract tests. Synthetic files/tensors only, no model weights or inference.
Run: .venv/Scripts/python.exe -B tests/test_classification_infer.py
"""
from __future__ import annotations
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1] / "packages"))
from infer import classification as cls


class ClassificationContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="cls-contract-")
        self.root = Path(self.temp.name)
        self.folder = self.root / cls.DEFAULT_MODEL
        self.folder.mkdir()
        (self.folder / "weights.pth").write_bytes(b"fixture-not-a-real-model")
        self.spec = {"model_name": cls.DEFAULT_MODEL, "builder": cls.DEFAULT_MODEL,
                     "framework": "torchvision", "head_attr": "classifier", "head_index": 3,
                     "input": [3,224,224], "output": ["B",6], "num_classes": 6}
        self.meta = {"model_name": cls.DEFAULT_MODEL, "num_classes": 6, "task": "classification",
                     "classes_hash": cls.CLASS_HASH, "preprocess_hash": cls.PREPROCESS_HASH,
                     "class_keys": [x["key"] for x in CLASSES["classes"]], "params": 123,
                     "weights_sha256": cls.file_hash(self.folder / "weights.pth")}
        for name, data in (("classes", CLASSES),("preprocess", PREPROCESS),
                           ("model_spec",self.spec),("metadata",self.meta)):
            self.write(name, data)
        self.asset = cls.inspect_asset(cls.DEFAULT_MODEL,self.root,require_validated=False)

    def tearDown(self):
        self.temp.cleanup()

    def write(self,name,data):
        (self.folder / (name+".json")).write_text(json.dumps(data,ensure_ascii=False),encoding="utf-8")

    def receipt(self):
        self.write("validated", {"ok":True,"asset_hash":self.asset.asset_hash,
                                 "runtime":cls.runtime_versions(),"shape_b1":[1,6],"shape_b2":[2,6]})

    def test_canonical_export_hashes(self):
        self.assertEqual(cls.canonical_hash(CLASSES),cls.CLASS_HASH)
        self.assertEqual(cls.canonical_hash(PREPROCESS),cls.PREPROCESS_HASH)

    def test_catalog_requires_current_receipt(self):
        self.assertFalse(cls.catalog(self.root)[0]["available"])
        self.receipt()
        row=cls.catalog(self.root)[0]
        self.assertTrue(row["available"])
        self.assertEqual(row["param_count"],123)
        self.assertFalse(any(key in row for key in ("path","weight_path","accuracy","macro_f1")))

    def test_changed_weights_are_unavailable(self):
        self.receipt()
        (self.folder / "weights.pth").write_bytes(b"other-fixture")
        self.assertFalse(cls.catalog(self.root)[0]["available"])

    def test_wrong_class_order_rejected(self):
        data=copy.deepcopy(CLASSES);data["classes"].reverse();self.write("classes",data)
        with self.assertRaisesRegex(cls.ClassificationError,"类别映射"):
            cls.inspect_asset(cls.DEFAULT_MODEL,self.root,require_validated=False)

    def test_changed_preprocess_rejected(self):
        data=copy.deepcopy(PREPROCESS);data["resize"]=[224,224];self.write("preprocess",data)
        with self.assertRaisesRegex(cls.ClassificationError,"预处理"):
            cls.inspect_asset(cls.DEFAULT_MODEL,self.root,require_validated=False)

    def test_wrong_head_rejected(self):
        self.spec["head_index"]=1;self.write("model_spec",self.spec)
        with self.assertRaisesRegex(cls.ClassificationError,"结构"):
            cls.inspect_asset(cls.DEFAULT_MODEL,self.root,require_validated=False)

    def test_unknown_slug_never_resolves_path(self):
        with self.assertRaisesRegex(cls.ClassificationError,"不支持"):
            cls.inspect_asset("../resnet18",self.root)

    def test_runtime_change_requires_revalidation(self):
        self.receipt()
        with patch.object(cls,"runtime_versions",return_value={"torch":"changed"}):
            self.assertFalse(cls.catalog(self.root)[0]["available"])

    def test_missing_runtime_is_unavailable_not_exception(self):
        self.receipt()
        from importlib.metadata import PackageNotFoundError
        with patch.object(cls,"runtime_versions",side_effect=PackageNotFoundError("torch")):
            self.assertFalse(cls.catalog(self.root)[0]["available"])

    def test_only_complete_classification_gt_produces_metrics(self):
        self.assertEqual(cls.classification_metrics(None,[0]),{"available":False})
        for labels,pred in (([True],[0]),([6],[0]),([1,2],[1]),([],[])):
            with self.assertRaises(cls.ClassificationError): cls.classification_metrics(labels,pred)
        values=cls.classification_metrics(list(range(6)),list(range(6)))
        self.assertEqual(values["accuracy"],1)
        self.assertEqual(values["macro_f1"],1)
        self.assertNotIn("miou",values)

    def test_fixed_six_class_macro_policy(self):
        value=cls.classification_metrics([0],[0])
        self.assertEqual(value["accuracy"],1)
        self.assertAlmostEqual(value["macro_f1"],1/6)

    def test_empty_or_oversize_inputs_rejected_before_load(self):
        for paths in ([],[Path('fake')]*51):
            with self.assertRaises(cls.ClassificationError): cls.predict_images(cls.DEFAULT_MODEL,paths,self.root)

    def test_logits_shape_finite_and_dtype(self):
        import torch
        for tensor in (torch.zeros(1,6,4,4),torch.zeros(1,5),torch.zeros(1,6,dtype=torch.long),
                       torch.full((1,6),float('nan')),torch.full((1,6),float('inf'))):
            with self.assertRaises(cls.ClassificationError): cls.validate_logits(tensor,1)
        cls.validate_logits(torch.zeros(2,6),2)

    def test_prediction_is_scores_not_accuracy(self):
        import torch
        row=cls.prediction_rows(torch.tensor([[0.,1.,2.,3.,4.,5.]]),CLASSES["classes"])[0]
        self.assertEqual(row["class_id"],5)
        self.assertEqual(len(row["topk"]),3)
        self.assertAlmostEqual(sum(row["scores"]),1)
        self.assertNotIn("accuracy",row)
        self.assertEqual(row["key"],"scratches")

    def test_preprocess_preserves_aspect_and_grayscale(self):
        from PIL import Image
        import torch
        path=self.root/'rgb.png';Image.new('RGB',(400,200),(190,70,20)).save(path)
        tensor=cls.image_tensor(path,self.asset)
        self.assertEqual(list(tensor.shape),[1,3,224,448])
        restored=tensor[0]*torch.tensor(PREPROCESS['normalize_std'])[:,None,None]+torch.tensor(PREPROCESS['normalize_mean'])[:,None,None]
        self.assertTrue(torch.allclose(restored[0],restored[1]))
        self.assertTrue(torch.allclose(restored[1],restored[2]))

    def test_corrupt_and_extreme_ratio_images_rejected(self):
        from PIL import Image
        path=self.root/'wide.png';Image.new('RGB',(1000,10)).save(path)
        with self.assertRaises(cls.ClassificationError): cls.image_tensor(path,self.asset)
        path.write_bytes(b'not an image')
        with self.assertRaises(cls.ClassificationError): cls.image_tensor(path,self.asset)

    def test_load_strict_and_restricted_contract(self):
        import torch
        from types import SimpleNamespace
        strict = Mock()
        fake=SimpleNamespace(load_state_dict=strict,parameters=lambda:[SimpleNamespace(numel=lambda:123)],eval=lambda:None)
        with patch('torchvision.models.mobilenet_v3_small',return_value=fake) as builder, patch('torch.load',return_value={'x':torch.zeros(1)}) as load:
            self.assertIs(cls.load_model(self.asset),fake)
            builder.assert_called_once_with(weights=None,num_classes=6)
            self.assertTrue(load.call_args.kwargs['weights_only'])
            self.assertTrue(strict.call_args.kwargs['strict'])

    def test_corrupted_state_dict_is_not_reinterpreted(self):
        import torch
        with patch('torchvision.models.mobilenet_v3_small') as builder, patch('torch.load',return_value={'model_state':{}}):
            with self.assertRaisesRegex(cls.ClassificationError,'完整 state_dict'):
                cls.load_model(self.asset)
            builder.return_value.load_state_dict.assert_not_called()

    def test_weight_change_between_inspection_and_load_rejected(self):
        (self.folder/'weights.pth').write_bytes(b'changed after inspection')
        with patch('torchvision.models.mobilenet_v3_small'),patch('torch.load') as load:
            with self.assertRaisesRegex(cls.ClassificationError,'加载前已变更'):
                cls.load_model(self.asset)
            load.assert_not_called()

    def test_installer_rejects_traversal_and_never_overwrites(self):
        import runpy,zipfile
        install=runpy.run_path(str(Path(__file__).resolve().parents[1]/'scripts/install_classification_assets.py'))['install']
        archive=self.root/'bad.zip'
        with zipfile.ZipFile(archive,'w') as z:
            z.writestr('neu_cls_v1_formal_exports/../outside.txt','bad')
        with self.assertRaisesRegex(ValueError,'Unsafe'):
            install(archive,self.root/'new-assets')
        self.assertFalse((self.root/'outside.txt').exists())
        with self.assertRaisesRegex(ValueError,'already exists'):
            install(archive,self.folder)
        self.assertEqual((self.folder/'weights.pth').read_bytes(),b'fixture-not-a-real-model')

CLASSES = {'task': 'classification',
 'num_classes': 6,
 'normal_class': False,
 'classes': [{'id': 0,
              'key': 'crazing',
              'display_zh': '龟裂',
              'source_aliases': ['Cr']},
             {'id': 1,
              'key': 'inclusion',
              'display_zh': '夹杂',
              'source_aliases': ['In']},
             {'id': 2,
              'key': 'patches',
              'display_zh': '斑块',
              'source_aliases': ['Pa']},
             {'id': 3,
              'key': 'pitted_surface',
              'display_zh': '麻点',
              'source_aliases': ['PS']},
             {'id': 4,
              'key': 'rolled_in_scale',
              'display_zh': '轧入氧化皮',
              'source_aliases': ['rolled-in_scale', 'RS']},
             {'id': 5,
              'key': 'scratches',
              'display_zh': '划痕',
              'source_aliases': ['Sc']}],
 'class_to_idx': {'crazing': 0,
                  'inclusion': 1,
                  'patches': 2,
                  'pitted_surface': 3,
                  'rolled_in_scale': 4,
                  'scratches': 5},
 'note': '六类都是缺陷。未标注图像不是正常类。'}

PREPROCESS = {'task': 'classification',
 'grayscale_to_rgb': 'Grayscale(num_output_channels=3)，在 Resize 之前作用于 PIL',
 'resize': 224,
 'interpolation': 'bilinear',
 'antialias': True,
 'backend_note': 'torchvision 0.15.1 在 PIL 路径上始终做抗锯齿；本配置显式传入 '
                 'antialias=True，并且先于 ToTensor，因此走 PIL。Tensor 后端才会按该开关切换。',
 'to_tensor': 'ToTensor，像素除以 255 变为 float32',
 'normalize_mean': [0.485, 0.456, 0.406],
 'normalize_std': [0.229, 0.224, 0.225],
 'train_augmentation': ['RandomHorizontalFlip(p=0.5)'],
 'val_test_augmentation': []}


if __name__ == '__main__':
    unittest.main(verbosity=2)

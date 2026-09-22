"""Runs inside the student Docker image (or a test subprocess). Never imported by FastAPI."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import traceback
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn as nn

from admit.ckpt import extract_whitelisted_state, load_checkpoint_file
from admit.perf import collect_env, count_all_parameters, measure_cpu_forward


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _fail(out_dir: Path, stage: str, message: str, **extra: Any) -> int:
    payload = {"ok": False, "fail_stage": stage, "message": message, **extra}
    _write_json(out_dir / "result.json", payload)
    return 1


def _load_module(py_path: Path):
    spec = importlib.util.spec_from_file_location("student_model", py_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载源码文件")
    module = importlib.util.module_from_spec(spec)
    sys.modules["student_model"] = module
    spec.loader.exec_module(module)
    return module


def _build(module: Any, entry: str, num_classes: int, in_channels: int) -> nn.Module:
    if not hasattr(module, entry):
        raise AttributeError(f"找不到入口 {entry}")
    target = getattr(module, entry)
    if isinstance(target, type) and issubclass(target, nn.Module):
        built = target(num_classes=num_classes, in_channels=in_channels)
    elif callable(target):
        built = target(num_classes=num_classes, in_channels=in_channels)
    else:
        raise TypeError(f"{entry} 既不是 build_model 也不是 nn.Module 子类")
    if not isinstance(built, nn.Module):
        raise TypeError("入口必须返回 torch.nn.Module")
    return built


def _forward_logits(model: nn.Module, tensor: torch.Tensor) -> torch.Tensor:
    output = model(tensor)
    if isinstance(output, (tuple, list)):
        output = output[0]
    if not torch.is_tensor(output):
        raise TypeError("forward 主输出必须是张量")
    return output


def run_admit(in_dir: Path, out_dir: Path) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((in_dir / "manifest.json").read_text(encoding="utf-8"))
    py_path = in_dir / manifest.get("source_name", "model.py")
    weight_path = in_dir / manifest.get("weight_name", "weights.pth")
    entry = str(manifest.get("entry_symbol") or "build_model")
    num_classes = int(manifest["num_classes"])
    in_channels = int(manifest["in_channels"])
    height = int(manifest["input_h"])
    width = int(manifest["input_w"])
    if not py_path.is_file():
        return _fail(out_dir, "file", "缺少模型源码")
    if not weight_path.is_file():
        return _fail(out_dir, "file", "缺少权重文件")

    try:
        module = _load_module(py_path)
    except Exception as exc:
        return _fail(out_dir, "import", f"import 失败：{exc}", traceback=traceback.format_exc(limit=8))

    try:
        model = _build(module, entry, num_classes, in_channels)
        model.eval()
    except Exception as exc:
        return _fail(out_dir, "build", f"构建失败：{exc}", traceback=traceback.format_exc(limit=8))

    try:
        ckpt = load_checkpoint_file(weight_path)
        state, _name = extract_whitelisted_state(ckpt)
        model.load_state_dict(state, strict=True)
    except Exception as exc:
        return _fail(out_dir, "load", f"加载权重失败：{exc}", traceback=traceback.format_exc(limit=8))

    try:
        dummy = torch.zeros(1, in_channels, height, width, dtype=torch.float32)
        with torch.no_grad():
            logits = _forward_logits(model, dummy)
    except Exception as exc:
        return _fail(out_dir, "forward", f"dummy 前向失败：{exc}", traceback=traceback.format_exc(limit=8))

    if logits.ndim != 4:
        return _fail(out_dir, "shape", f"输出维度为 {tuple(logits.shape)}，需要 B×C×H×W")
    if int(logits.shape[1]) != num_classes:
        return _fail(
            out_dir,
            "shape",
            f"输出通道为 {int(logits.shape[1])}，与声明类别数 {num_classes} 不一致",
        )

    param_count = count_all_parameters(model)
    _write_json(
        out_dir / "result.json",
        {
            "ok": True,
            "fail_stage": None,
            "message": "检查通过",
            "param_count": param_count,
            "output_shape": [int(x) for x in logits.shape],
        },
    )
    return 0


def run_infer(in_dir: Path, out_dir: Path) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    pred_dir = out_dir / "preds"
    pred_dir.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((in_dir / "manifest.json").read_text(encoding="utf-8"))
    py_path = in_dir / manifest.get("source_name", "model.py")
    weight_path = in_dir / manifest.get("weight_name", "weights.pth")
    entry = str(manifest.get("entry_symbol") or "build_model")
    num_classes = int(manifest["num_classes"])
    in_channels = int(manifest["in_channels"])
    keys = list(manifest.get("sample_keys") or [])

    try:
        module = _load_module(py_path)
        model = _build(module, entry, num_classes, in_channels)
        model.eval()
        ckpt = load_checkpoint_file(weight_path)
        state, _name = extract_whitelisted_state(ckpt)
        model.load_state_dict(state, strict=True)
    except Exception as exc:
        return _fail(out_dir, "load", f"推理装载失败：{exc}", traceback=traceback.format_exc(limit=8))

    try:
        for key in keys:
            array = np.load(in_dir / "tensors" / f"{key}.npy")
            tensor = torch.from_numpy(array).unsqueeze(0).float()
            with torch.no_grad():
                logits = _forward_logits(model, tensor)
            if logits.ndim != 4 or int(logits.shape[1]) != num_classes:
                return _fail(out_dir, "shape", f"{key} 输出形状非法：{tuple(logits.shape)}")
            pred = logits.argmax(dim=1)[0].cpu().numpy().astype(np.uint8)
            np.save(pred_dir / f"{key}.npy", pred)
    except Exception as exc:
        return _fail(out_dir, "forward", f"推理失败：{exc}", traceback=traceback.format_exc(limit=8))

    _write_json(out_dir / "result.json", {"ok": True, "fail_stage": None, "message": "infer ok", "n": len(keys)})
    return 0


def run_perf(in_dir: Path, out_dir: Path) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((in_dir / "manifest.json").read_text(encoding="utf-8"))
    py_path = in_dir / manifest.get("source_name", "model.py")
    weight_path = in_dir / manifest.get("weight_name", "weights.pth")
    entry = str(manifest.get("entry_symbol") or "build_model")
    num_classes = int(manifest["num_classes"])
    in_channels = int(manifest["in_channels"])
    height = int(manifest["input_h"])
    width = int(manifest["input_w"])
    if not py_path.is_file():
        return _fail(out_dir, "file", "缺少模型源码")
    if not weight_path.is_file():
        return _fail(out_dir, "file", "缺少权重文件")

    try:
        module = _load_module(py_path)
        model = _build(module, entry, num_classes, in_channels)
        model.eval()
        ckpt = load_checkpoint_file(weight_path)
        state, _name = extract_whitelisted_state(ckpt)
        model.load_state_dict(state, strict=True)
    except Exception as exc:
        return _fail(out_dir, "load", f"测量装载失败：{exc}", traceback=traceback.format_exc(limit=8))

    try:
        stats = measure_cpu_forward(model, in_channels=in_channels, height=height, width=width)
    except Exception as exc:
        return _fail(out_dir, "forward", f"dummy 计时失败：{exc}", traceback=traceback.format_exc(limit=8))

    _write_json(
        out_dir / "result.json",
        {
            "ok": True,
            "fail_stage": None,
            "message": "perf ok",
            "param_count": count_all_parameters(model),
            "flops": None,
            "weight_bytes": int(weight_path.stat().st_size),
            "env": collect_env(),
            **stats,
        },
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Student isolate runner")
    parser.add_argument("mode", choices=("admit", "infer", "perf"))
    parser.add_argument("--in", dest="in_dir", required=True)
    parser.add_argument("--out", dest="out_dir", required=True)
    args = parser.parse_args(argv)
    in_dir = Path(args.in_dir)
    out_dir = Path(args.out_dir)
    try:
        if args.mode == "admit":
            return run_admit(in_dir, out_dir)
        if args.mode == "perf":
            return run_perf(in_dir, out_dir)
        return run_infer(in_dir, out_dir)
    except MemoryError:
        return _fail(out_dir, "resource", "内存不足")
    except Exception as exc:
        return _fail(out_dir, "resource", str(exc), traceback=traceback.format_exc(limit=8))


if __name__ == "__main__":
    raise SystemExit(main())

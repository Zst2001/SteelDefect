"""Independent, stdlib-only admission of the frozen PCB release (no model execution).

Run with the repository interpreter. Default is read-only validation; --extract
creates a NEW private staging directory only. This script never executes archive
code, deserializes weights, reads .env, connects to services, or enables a model.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import sys
import unicodedata
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASE = "pcb_seg_meiwei_v2_formal_v1"
ZIP_SHA256 = "7c93a1f299f7e2b998ee1c8473ce9f3b6b700487247d4c069a69ec0240549c1d"
ZIP_BYTES = 144022706
TOTAL_BYTES = 158245813
SOURCE_SHA256 = "f36e2b509030b607ea621cb80be6a424cc88b66f4003ec8b710d67a02c9b0a7b"
MODEL_IDENTITIES = {
    "unet": ("c9ffbb31c5bc80ef74b71d5b35a1d13517610656362a2030bae639156314235b", 7849634, "dec1"),
    "unet_resnet18": ("6ce8f3ebe139c6781670af1889c1c80e519980ab056964a97b2359a1c7366fcd", 14413570, "dec0"),
    "unetpp_resnet18": ("ff621b6e9d6097f7f8d89bc12bc37834c94c3e68aa190b99cffa22c7cbf2bd69", 16111106, "dec0"),
}
ALLOWLIST = frozenset({
    "README_交接说明.md", "HANDOFF_TO_LOCAL_CODEX.md", "MODEL_REGISTRY.json",
    "ASSET_MANIFEST.json", "SHA256SUMS.txt", "LICENSE_NOTES.md",
    "source/trusted_models.py", "source/pcb_preprocess.py", "source/pcb_postprocess.py",
    "source/pcb_visualize.py", "source/source_manifest.json",
    "tools/verify_archive.py", "tools/smoke_cpu.py", "tools/compare_reference.py", "tools/reference_input.py",
    "reference_vectors/input_220_rgb.npy", "reference_vectors/input_black_220_rgb.npy",
    "reference_vectors/input_gray_220_rgb.npy", "reference_vectors/expected_preprocessed.npy",
    "reference_vectors/expected_preprocessed_black.npy", "reference_vectors/expected_preprocessed_gray.npy",
    "reference_vectors/unet_logits.npy", "reference_vectors/unet_resnet18_logits.npy",
    "reference_vectors/unetpp_resnet18_logits.npy", "reference_vectors/vectors_manifest.json",
    "docs/pcb_inference_contract.md", "docs/PCB_Guide_本地接入要点.md", "docs/PACKAGING_REPORT.md",
} | {
    f"models/{model}/{filename}"
    for model in MODEL_IDENTITIES
    for filename in ("weights.pth", "model_spec.json", "classes.json", "preprocess.json", "postprocess.json",
                     "metadata.json", "visualization_spec.json", "cpu_validation_autodl.json")
})
_RESERVED = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"} | {
    f"{prefix}{digit}" for prefix in ("COM", "LPT") for digit in "123456789¹²³"
}


class AdmissionError(ValueError):
    """Asset cannot be admitted; never repair an expected hash automatically."""


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise AdmissionError(reason)


def safe_name(name: str) -> str:
    require(isinstance(name, str) and bool(name) and len(name) <= 200, "invalid path length")
    require(not any(ord(c) < 32 or c in '\\:<>"|?*' for c in name), f"unsafe path characters: {name!r}")
    parts = name.split("/")
    require(all(p and p not in (".", "..") and not p.endswith((" ", ".")) for p in parts), f"unsafe path: {name!r}")
    require(all(p.split(".", 1)[0].upper() not in _RESERVED for p in parts), f"reserved Windows name: {name!r}")
    return unicodedata.normalize("NFC", name).casefold()


def scan_members(infos: list[zipfile.ZipInfo], *, expected_names: frozenset[str] | None = None,
                 expected_total: int | None = None) -> dict[str, zipfile.ZipInfo]:
    """Check central directory before reading any member or creating directories."""
    require(0 < len(infos) <= 52, "unexpected member count")
    names: dict[str, zipfile.ZipInfo] = {}
    folded: set[str] = set()
    total = 0
    for info in infos:
        key = safe_name(info.orig_filename)
        require(info.filename == info.orig_filename, "truncated ZIP filename")
        require(key not in folded, f"duplicate/case-colliding path: {info.filename}")
        require(not info.is_dir() and stat.S_ISREG(info.external_attr >> 16), f"not a regular file: {info.filename}")
        require(not info.flag_bits & (1 | 64), "encrypted member")
        require(info.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED), "unsupported compression")
        require(0 <= info.file_size <= 70_000_000 and info.compress_size >= 0, "oversized member")
        require(info.file_size <= max(info.compress_size, 1) * 2000, "excessive compression ratio")
        total += info.file_size
        require(total <= TOTAL_BYTES, "oversized expanded archive")
        names[info.filename] = info
        folded.add(key)
    require(not any("/".join(k.split("/")[:i]) in folded for k in folded for i in range(1, len(k.split("/")))), "file/directory path collision")
    if expected_names is not None:
        require(set(names) == expected_names, "archive differs from frozen file allowlist")
    if expected_total is not None:
        require(total == expected_total, "expanded byte total differs")
    return names


def stream_hash(stream, *, limit: int | None = None) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    while chunk := stream.read(1024 * 1024):
        size += len(chunk)
        require(limit is None or size <= limit, "stream exceeds declared size")
        digest.update(chunk)
    return digest.hexdigest(), size


def parse_sums(text: str, names: set[str]) -> dict[str, str]:
    hashes = {}
    for line in text.splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        require(match is not None, "malformed SHA256SUMS entry")
        digest, name = match.groups()
        safe_name(name)
        require(name not in hashes, "duplicate SHA256SUMS entry")
        hashes[name] = digest
    require(set(hashes) == names - {"SHA256SUMS.txt"}, "SHA256SUMS coverage differs")
    return hashes


def json_object(pairs):
    obj = {}
    for key, value in pairs:
        require(key not in obj, "duplicate JSON key")
        obj[key] = value
    return obj


def read_json(z: zipfile.ZipFile, name: str):
    require(z.getinfo(name).file_size < 100_000, "oversized metadata")
    return json.loads(z.read(name), object_pairs_hook=json_object)


def verify_metadata(z: zipfile.ZipFile, names: dict, hashes: dict) -> dict:
    manifest = read_json(z, "ASSET_MANIFEST.json")
    registry = read_json(z, "MODEL_REGISTRY.json")
    require(manifest["release_id"] == registry["release_id"] == RELEASE, "release identity mismatch")
    entries = manifest["files"]
    require(len(entries) == 50 and len({r["path"] for r in entries}) == 50, "manifest count/duplicate mismatch")
    require({r["path"] for r in entries} == set(names) - {"ASSET_MANIFEST.json", "SHA256SUMS.txt"}, "manifest coverage mismatch")
    for row in entries:
        require(row["sha256"] == hashes[row["path"]] and row["bytes"] == names[row["path"]].file_size, "manifest hash/size mismatch")
    require(registry["scene"] == "pcb_surface_defect_segmentation" and registry["task_kind"] == "segmentation", "scene identity mismatch")
    require(registry["asset_status"] == "TRANSFERRED_NOT_VERIFIED_ON_TARGET" and registry["verified_for_staging_on_windows"] is False, "unexpected source admission status")
    require(registry["database_registered"] is False and registry["default_candidate"]["enabled"] is False, "source must remain disabled")
    require(registry["classes"] == [{"id": 0, "key": "background"}, {"id": 1, "key": "defect"}], "class identity mismatch")
    require(registry["split_name"] == "meiwei_v2", "split identity mismatch")
    require(set(registry["allowlist"]) == set(MODEL_IDENTITIES) and len(registry["allowlist"]) == 3, "model allowlist mismatch")
    require(registry["trusted_source"] == {"path": "source/trusted_models.py", "sha256": SOURCE_SHA256}, "source registry mismatch")
    require(hashes["source/trusted_models.py"] == SOURCE_SHA256, "trusted source digest mismatch")
    rows = registry["models"]
    require(len(rows) == 3 and {r["model_id"] for r in rows} == set(MODEL_IDENTITIES), "model registry mismatch")
    for row in rows:
        digest, params, layer = MODEL_IDENTITIES[row["model_id"]]
        path = f"models/{row['model_id']}/weights.pth"
        require(row["weights"] == path and row["weights_sha256"] == hashes[path] == digest, "weight identity mismatch")
        require(row["weights_bytes"] == names[path].file_size and row["params"] == params and row["cam_layer"] == layer, "model protocol mismatch")
        require(row["offline_test"]["n_images"] == 140, "offline split size mismatch")
    source = read_json(z, "source/source_manifest.json")
    require(source["trusted_models_sha256"] == SOURCE_SHA256, "source manifest identity mismatch")
    for path, digest in source["modules"].items():
        require(path in hashes and hashes[path] == digest, "source module digest mismatch")
    return registry


def check_private_destination(destination: Path, private_root: Path) -> Path:
    """Only a new descendant of the administrator's private asset root is accepted."""
    root = private_root.absolute()
    target = destination.absolute()
    require(target != root and target.is_relative_to(root), "destination outside private asset root")
    for candidate in (root, *root.parents, target, *target.parents):
        require(not candidate.is_symlink() and not (hasattr(candidate, "is_junction") and candidate.is_junction()), "symlink/junction staging path")
    require(target.resolve().is_relative_to(root.resolve()), "resolved destination escapes private root")
    require(not target.exists(), "destination already exists; refusing overwrite")
    return target


def extract_verified(z: zipfile.ZipFile, names: dict, hashes: dict, destination: Path, private_root: Path) -> None:
    target = check_private_destination(destination, private_root)
    target.mkdir(parents=True, exist_ok=False)
    for name, info in names.items():
        path = target.joinpath(*name.split("/"))
        require(path.resolve().is_relative_to(target.resolve()), "extraction path escapes staging")
        path.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        count = 0
        with z.open(info) as source, path.open("xb") as out:
            while chunk := source.read(1024 * 1024):
                count += len(chunk)
                require(count <= info.file_size, "member expands beyond declared size")
                digest.update(chunk)
                out.write(chunk)
        require(count == info.file_size, "extracted size mismatch")
        if name in hashes:
            require(digest.hexdigest() == hashes[name], "extracted hash mismatch")
        # Re-read the actual file, rather than relying only on bytes passed to write().
        with path.open("rb") as actual:
            disk_digest, disk_size = stream_hash(actual, limit=info.file_size)
        require(disk_digest == digest.hexdigest() and disk_size == count, "on-disk verification mismatch")


def verify_release(archive: Path, *, destination: Path | None = None, private_root: Path | None = None) -> dict:
    require(archive.is_file() and not archive.is_symlink(), "missing or linked archive")
    sidecar = archive.with_suffix(archive.suffix + ".sha256")
    require(sidecar.is_file() and not sidecar.is_symlink() and sidecar.stat().st_size <= 512, "missing/invalid sidecar")
    expected = f"{ZIP_SHA256}  {RELEASE}.zip"
    require(sidecar.read_text(encoding="utf-8").strip() == expected, "external sidecar differs from fixed release")
    with archive.open("rb") as raw:
        digest, size = stream_hash(raw, limit=ZIP_BYTES)
        require(digest == ZIP_SHA256 and size == ZIP_BYTES, "archive SHA256/size mismatch")
        raw.seek(0)
        with zipfile.ZipFile(raw) as z:
            names = scan_members(z.infolist(), expected_names=ALLOWLIST, expected_total=TOTAL_BYTES)
            hashes = parse_sums(z.read("SHA256SUMS.txt").decode("utf-8"), set(names))
            actual_hashes = {}
            for name, info in names.items():
                with z.open(info) as member:
                    actual, member_size = stream_hash(member, limit=info.file_size)
                require(member_size == info.file_size, "member size mismatch")
                require(name not in hashes or hashes[name] == actual, f"SHA256SUMS mismatch: {name}")
                actual_hashes[name] = actual
            registry = verify_metadata(z, names, hashes)
            if destination is not None:
                require(private_root is not None, "private root required")
                extract_verified(z, names, hashes, destination, private_root)
    return {
        "status": "ASSET_INTEGRITY_PASS", "model_admission": "NOT_VERIFIED",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(), "archive": str(archive),
        "archive_sha256": digest, "archive_bytes": size,
        "sidecar_sha256_matches_fixed_release": True, "regular_files": len(names),
        "uncompressed_bytes": sum(i.file_size for i in names.values()),
        "internal_sha256_checks": len(hashes), "manifest_checks": 50,
        "trusted_source_sha256": hashes["source/trusted_models.py"],
        "model_weights": {r["model_id"]: r["weights_sha256"] for r in registry["models"]},
        "path_safety": "PASS", "frozen_allowlist": "PASS", "archive_code_executed": False,
        "extracted_to": str(destination) if destination else None,
        "files": {name: {"sha256": actual_hashes[name], "bytes": i.file_size} for name, i in names.items()},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=ROOT / "assets/PCB_segment" / f"{RELEASE}.zip")
    parser.add_argument("--extract", action="store_true", help="Create private staging, refusing existing destination")
    parser.add_argument("--destination", type=Path, default=ROOT / "assets/pcb/meiwei_v2_formal_v1")
    parser.add_argument("--report", type=Path, help="Write a NEW JSON evidence file; never overwrite")
    args = parser.parse_args()
    try:
        if args.report:
            require(not args.report.exists(), "report already exists; refusing overwrite")
        result = verify_release(args.archive, destination=args.destination if args.extract else None,
                                private_root=ROOT / "assets/pcb")
        code = 0
    except (AdmissionError, OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile, RuntimeError) as exc:
        result = {"status": "BLOCKED_ASSET_INTEGRITY", "error": str(exc), "model_admission": "NOT_VERIFIED"}
        code = 1
    if args.report and not args.report.exists():
        args.report.parent.mkdir(parents=True, exist_ok=True)
        with args.report.open("x", encoding="utf-8") as report:
            json.dump(result, report, ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in result.items() if k != "files"}, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())

"""Artifact policy shared by authenticated routes, serializers and the worker.

Callers MUST authorize task visibility before using this module. Registration,
semantic path checks and filesystem confinement are independent requirements.
This is not immutable publication or protection against a hostile host process.
"""
from __future__ import annotations

import re
import stat
import zipfile
from collections import Counter
from pathlib import Path

from sqlalchemy.orm import Session

from app.db.models import Artifact, Dataset, DatasetVersion, Model, ModelVersion, Sample, Task, TaskModel, TaskSample
from app.errors import AppError

BUNDLE_UNAVAILABLE = "图层包尚未生成或未通过安全校验，请联系管理员核查。"
GT_NOTICE = "固定集或来源不明的 GT 派生图层暂不提供下载；普通自有配对 GT 对照不受影响。"


def unavailable() -> AppError:
    return AppError("制品不存在或不可下载", code="ARTIFACT_UNAVAILABLE", stage="file", status_code=404)


def canonical_path(value: str) -> str:
    # Exact POSIX names only; reject Windows aliases, ADS and device paths too.
    parts = value.split("/")
    if not value or any(
        not p or p in {".", ".."} or p.endswith((".", " "))
        or re.search(r'[\\:<>"|?*\x00-\x1f\x7f]', p)
        or re.fullmatch(r"(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", p)
        for p in parts
    ):
        raise unavailable()
    return value


def _linked(path: Path) -> bool:
    return path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())


class TaskArtifacts:
    def __init__(self, db: Session, task: Task, settings):
        self.task = task
        self.storage = settings.storage_path.resolve()
        canonical_path(task.id)
        if "/" in task.id:
            raise unavailable()
        self.root = self.storage / "tasks" / task.id
        self.rows = db.query(Artifact).filter(Artifact.task_id == task.id).all()
        # Case aliases also conflict on Windows; never select an arbitrary row.
        counts = Counter(a.rel_path.casefold() for a in self.rows)
        self.unique = {a.rel_path: a for a in self.rows if counts[a.rel_path.casefold()] == 1}
        version = db.get(DatasetVersion, task.dataset_version_id)
        dataset = db.get(Dataset, version.dataset_id) if version else None
        samples = db.query(Sample).join(TaskSample, TaskSample.sample_id == Sample.id).filter(TaskSample.task_id == task.id).all()
        self.samples = {s.sample_key for s in samples if s.version_id == task.dataset_version_id}
        models = db.query(TaskModel, ModelVersion, Model).join(
            ModelVersion, ModelVersion.id == TaskModel.model_version_id
        ).join(Model, Model.id == ModelVersion.model_id).filter(TaskModel.task_id == task.id).all()
        self.models = {mv.id: (mv, model) for _, mv, model in models}
        self.valid = task.type in {"compare", "eval", "demo"}
        if task.type == "classification":
            from infer.classification import MODEL_SLUGS
            links = db.query(TaskModel).filter(TaskModel.task_id == task.id).count()
            self.valid = bool(
                version and version.kind == "classification_batch" and dataset
                and dataset.owner_id == task.creator_id and not version.is_fixed_test
                and 1 <= len(samples) <= 50 and len(self.samples) == len(samples)
                and 1 <= len(models) <= 3 and links == len(models) == len(self.models)
                and not any(s.mask_uri for s in samples)
                and all(tm.role == "baseline" and model.source == "builtin" and mv.num_classes == 6
                        and mv.slug in MODEL_SLUGS
                        and mv.preprocess_id == task.preprocess_id for tm, mv, model in models)
            )
        if task.type == "demo":
            links = db.query(TaskModel).filter(TaskModel.task_id == task.id).count()
            self.valid = bool(samples and models) and not task.has_gt and not any(s.mask_uri for s in samples) and links == len(models) and all(
                tm.role == "baseline" and model.source == "builtin" for tm, _, model in models
            )
        self.allow_gt = bool(
            task.type == "compare" and task.has_gt and version and dataset
            and version.kind == "upload_batch" and not version.is_fixed_test
            and not version.forbid_student_gt_download and dataset.owner_id == task.creator_id
            and samples and len(self.samples) == len(samples) and all(s.mask_uri for s in samples)
        )
        self.gt_sensitive = bool(task.has_gt or task.type == "eval" or (version and (
            version.is_fixed_test or version.forbid_student_gt_download
        )))

    def permitted(self, a: Artifact, *, member: bool = False) -> bool:
        if not self.valid or a.task_id != self.task.id or self.unique.get(a.rel_path) is not a:
            return False
        try:
            canonical_path(a.rel_path)
        except AppError:
            return False
        key, mid, kind = a.sample_key, a.model_version_id, a.kind
        if self.task.type == "classification":
            if kind == "classification_result":
                return (key is None and mid is None and a.rel_path == "classification.json"
                        and self.task.status in {"success", "partial_success"})
            return (kind == "origin" and key in self.samples and mid is None
                    and a.rel_path == f"origin/{key}.png")
        if kind in {"log", "bundle"}:
            return key is None and mid is None and a.rel_path == {"log": "task.json", "bundle": "bundle.zip"}[kind] and not (member and kind == "bundle")
        if key not in self.samples:
            return False
        if kind in {"origin", "gt"}:
            return mid is None and a.rel_path == f"{kind}/{key}.png" and (kind != "gt" or self.allow_gt)
        if kind == "montage":
            if mid is not None:
                return False
            classes = {c for mv, model in self.models.values() if model.source == "builtin" for c in range(1, max(int(mv.num_classes), 1))}
            if a.rel_path in {f"montage/{key}__cam_c{c}.png" for c in classes}:
                return True  # CAM rows contain origin and CAM, never a GT column.
            if a.rel_path == f"montage/{key}__error.png":
                return self.allow_gt
            return a.rel_path in {f"montage/{key}__mask.png", f"montage/{key}__overlay.png"} and (not self.gt_sensitive or self.allow_gt)
        if mid not in self.models:
            return False
        mv, model = self.models[mid]
        if kind == "cam":
            return model.source == "builtin" and a.rel_path in {f"cam/{mid}/{key}__c{c}.png" for c in range(1, max(int(mv.num_classes), 1))}
        folders = {"pred_color": "pred", "overlay": "overlay", "boundary": "boundary", "error": "error"}
        return kind in folders and a.rel_path == f"{folders[kind]}/{mid}/{key}.png" and (kind != "error" or self.allow_gt)

    def locate(self, rel: str, *, must_exist: bool = True) -> Path:
        canonical_path(rel)
        path = self.root / rel
        try:
            # Reject links/junctions even if they resolve inside another task root.
            for part in (self.storage / "tasks", self.root, *path.parents, path):
                if part == self.storage or part in self.storage.parents:
                    continue
                if _linked(part):
                    raise unavailable()
            resolved = path.resolve()
            if not resolved.is_relative_to(self.root) or (must_exist and not resolved.is_file()):
                raise unavailable()
        except (OSError, ValueError, RuntimeError):
            raise unavailable() from None
        return resolved

    def file(self, rel: str) -> Path:
        canonical_path(rel)
        row = self.unique.get(rel)
        if row is None or not self.permitted(row):
            raise unavailable()
        path = self.locate(rel)
        if row.kind == "bundle":
            self.validate_zip(path)
        return path

    def validate_zip(self, path: Path) -> None:
        try:
            with zipfile.ZipFile(path) as archive:
                seen = set()
                for entry in archive.infolist():
                    name = canonical_path(entry.filename)
                    mode = stat.S_IFMT(entry.external_attr >> 16)
                    if (entry.orig_filename != name or name.casefold() in seen or entry.is_dir()
                            or mode not in {0, stat.S_IFREG} or entry.external_attr & 0x10
                            or entry.flag_bits & 1 or entry.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}):
                        raise unavailable()
                    seen.add(name.casefold())
                    row = self.unique.get(name)
                    if row is None or not self.permitted(row, member=True):
                        raise unavailable()
                    self.locate(name)
                    # Check local/central header agreement and overlapping entries,
                    # without decompressing or extracting member data.
                    with archive.open(entry):
                        pass
                if "task.json" not in seen:
                    raise unavailable()
        except (OSError, ValueError, zipfile.BadZipFile, NotImplementedError):
            raise unavailable() from None

    def downloadable(self, *, bundle_ready: bool | None = None) -> list[Artifact]:
        result = []
        for row in self.rows:
            # Only serializers pass the result just checked in this same context.
            # file() and every download request still perform all checks afresh.
            if row.kind == "bundle" and bundle_ready is not None:
                if bundle_ready and self.permitted(row):
                    result.append(row)
                continue
            try:
                self.file(row.rel_path)
            except AppError:
                continue
            result.append(row)
        return result

    def bundle_state(self) -> dict:
        if self.task.type == "classification":
            return {"bundle_ready": False, "bundle_unavailable_reason": "分类不生成分割图层包，请在任务详情查看或下载分类结果。"}
        ready = False
        if self.task.status in {"success", "partial_success"}:
            try:
                self.file("bundle.zip")
                ready = True
            except AppError:
                pass
        return {"bundle_ready": ready, "bundle_unavailable_reason": None if ready else BUNDLE_UNAVAILABLE}


def write_bundle(db: Session, task: Task, settings) -> None:
    # SessionLocal has autoflush=False: include artifacts written in this run.
    db.flush()
    policy = TaskArtifacts(db, task, settings)
    members = [(row.rel_path, policy.locate(row.rel_path)) for row in policy.rows if policy.permitted(row, member=True)]
    if not any(name == "task.json" for name, _ in members):
        raise unavailable()
    target = policy.locate("bundle.zip", must_exist=False)
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, path in sorted(members):
            archive.write(path, name)

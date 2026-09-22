from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field

LAB_ADAPT_BEGIN = "# --- lab-adapt-begin ---"
LAB_ADAPT_END = "# --- lab-adapt-end ---"
LAB_BUILD_NAME = "lab_build_model"
NUM_CLASS_NAMES = {"num_classes", "n_classes", "classes", "num_class"}
IN_CHANNEL_NAMES = {"in_channels", "in_channel", "channels"}
PREVIEW_FIRST = "使用返回值第 1 项作为主分割输出。第一版不提供选路。"
BLOCK_NAME_RE = re.compile(
    r"(Block|Conv2d|Attention|Encoder|Decoder|Bottleneck|Basic|Layer|Gate|Pool|"
    r"Norm|Drop|Embed|CBAM|CSC|GAM|CPA|LAM)$",
    re.IGNORECASE,
)
OPINION_STAGES = {"file", "static", "import", "load", "resource"}
APPLY_STAGES = {"build", "forward"}


@dataclass(frozen=True)
class ParamInfo:
    name: str
    has_default: bool
    default_repr: str | None = None


@dataclass
class ClassInfo:
    name: str
    bases: list[str]
    init_params: list[ParamInfo] | None
    returns_sequence: bool | None
    is_nn_module: bool
    is_alias: bool
    body_stmts: int
    lineno: int


@dataclass
class SourceAnalysis:
    has_build_model: bool
    has_lab_build: bool
    has_marker: bool
    entry_exists: bool
    classes: list[ClassInfo]
    all_names: list[str]
    target: ClassInfo | None
    resolved_params: list[ParamInfo]
    returns_sequence: bool
    parse_error: str | None = None
    kinds: list[str] = field(default_factory=list)
    primary_kind: str = "opinion_only"
    can_apply: bool = False
    apply_blocked_reason: str | None = None
    call_kwargs: list[str] = field(default_factory=list)
    missing_required: list[str] = field(default_factory=list)
    wrapped_class: str | None = None
    hint_model_name: str | None = None
    name_registry: dict[str, str] = field(default_factory=dict)


def has_adapt_marker(source: str) -> bool:
    return LAB_ADAPT_BEGIN in source


def analyze_source(
    source: str,
    *,
    entry_symbol: str,
    fail_stage: str | None,
    fail_message: str | None,
    status: str,
    filename: str = "model.py",
    hint_model_name: str | None = None,
) -> SourceAnalysis:
    entry_symbol = (entry_symbol or "build_model").strip() or "build_model"
    analysis = SourceAnalysis(
        has_build_model=False,
        has_lab_build=False,
        has_marker=has_adapt_marker(source),
        entry_exists=False,
        classes=[],
        all_names=[],
        target=None,
        resolved_params=[],
        returns_sequence=False,
    )
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as exc:
        analysis.parse_error = exc.msg
        analysis.apply_blocked_reason = "源码无法解析，不能自动追加"
        analysis.kinds = ["opinion_only"]
        return analysis

    functions: set[str] = set()
    class_map: dict[str, ClassInfo] = {}
    name_registry: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            functions.add(node.name)
        elif isinstance(node, ast.ClassDef):
            info = _class_info(node)
            class_map[info.name] = info
            analysis.classes.append(info)
        elif isinstance(node, ast.Assign):
            name_registry.update(_dict_name_map(node.value))
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__" and isinstance(node.value, (ast.List, ast.Tuple)):
                    analysis.all_names = [
                        elt.value
                        for elt in node.value.elts
                        if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                    ]

    _mark_nn_modules(class_map)
    analysis.has_build_model = "build_model" in functions
    analysis.has_lab_build = LAB_BUILD_NAME in functions
    analysis.entry_exists = entry_symbol in functions or entry_symbol in class_map
    analysis.hint_model_name = (hint_model_name or "").strip() or None
    analysis.name_registry = name_registry
    analysis.wrapped_class = _wrapped_constructor(tree)
    target = _pick_target(
        class_map,
        analysis.all_names,
        entry_symbol,
        hint_model_name=hint_model_name,
        name_registry=name_registry,
    )
    if target is not None:
        analysis.target = target
        analysis.resolved_params = _resolve_params(target, class_map)
        analysis.returns_sequence = _resolve_returns_sequence(target, class_map)

    analysis.call_kwargs, analysis.missing_required = _call_kwargs(analysis.resolved_params)
    analysis.kinds = _classify(analysis, entry_symbol, fail_stage, fail_message)
    analysis.primary_kind = analysis.kinds[0] if analysis.kinds else "opinion_only"
    analysis.can_apply, analysis.apply_blocked_reason = _can_apply(
        analysis, status=status, fail_stage=fail_stage, fail_message=fail_message
    )
    return analysis


def render_adapter_patch(analysis: SourceAnalysis) -> str:
    if analysis.target is None:
        raise ValueError("没有可包装的目标类")
    class_name = analysis.target.name
    kwargs = ", ".join(analysis.call_kwargs) or ""
    call = f"{class_name}({kwargs})" if kwargs else f"{class_name}()"
    return (
        f"{LAB_ADAPT_BEGIN}\n"
        "# 模型适配助手追加。不改上方原有 class。\n"
        f"# {PREVIEW_FIRST}\n"
        "def lab_build_model(num_classes: int, in_channels: int = 3, **kwargs):\n"
        "    _ = in_channels\n"
        "    _ = kwargs\n"
        f"    model = {call}\n"
        "    _orig_forward = model.forward\n"
        "\n"
        "    def _lab_forward(*args, **kw):\n"
        "        out = _orig_forward(*args, **kw)\n"
        "        if isinstance(out, (tuple, list)):\n"
        "            out = out[0]\n"
        "        return out\n"
        "\n"
        "    model.forward = _lab_forward\n"
        "    return model\n"
        f"{LAB_ADAPT_END}\n"
    )


def append_patch(source: str, patch: str) -> str:
    body = source.rstrip()
    return f"{body}\n\n{patch.rstrip()}\n"


def apply_patch(source: str, patch: str) -> str:
    """Append a new adapt block, or replace the existing marked block in place."""
    if LAB_ADAPT_BEGIN in source and LAB_ADAPT_END in source:
        begin = source.index(LAB_ADAPT_BEGIN)
        end = source.index(LAB_ADAPT_END) + len(LAB_ADAPT_END)
        prefix = source[:begin].rstrip()
        suffix = source[end:].lstrip("\n")
        body = f"{prefix}\n\n{patch.rstrip()}\n"
        if suffix:
            return f"{body}{suffix}"
        return body
    return append_patch(source, patch)


def source_outside_adapt_unchanged(original: str, updated: str) -> bool:
    return _strip_adapt_block(original) == _strip_adapt_block(updated)


def _strip_adapt_block(source: str) -> str:
    if LAB_ADAPT_BEGIN not in source or LAB_ADAPT_END not in source:
        return source.rstrip()
    begin = source.index(LAB_ADAPT_BEGIN)
    end = source.index(LAB_ADAPT_END) + len(LAB_ADAPT_END)
    return (source[:begin].rstrip() + "\n" + source[end:].lstrip("\n")).rstrip()


def class_source_unchanged(original: str, updated: str, class_name: str) -> bool:
    orig_block = _class_block(original, class_name)
    new_block = _class_block(updated, class_name)
    return orig_block is not None and orig_block == new_block


def _class_block(source: str, class_name: str) -> str | None:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return ast.get_source_segment(source, node)
    return None


def _class_info(node: ast.ClassDef) -> ClassInfo:
    bases = [name for base in node.bases if (name := _expr_name(base))]
    init_params = None
    returns_sequence = None
    body_stmts = 0
    is_alias = True
    for item in node.body:
        if isinstance(item, ast.Expr) and isinstance(item.value, ast.Constant) and isinstance(item.value.value, str):
            continue
        if isinstance(item, ast.Pass):
            continue
        is_alias = False
        body_stmts += 1
        if isinstance(item, ast.FunctionDef) and item.name == "__init__":
            init_params = _fn_params(item)
        elif isinstance(item, ast.FunctionDef) and item.name == "forward":
            returns_sequence = _fn_returns_sequence(item)
    return ClassInfo(
        name=node.name,
        bases=bases,
        init_params=init_params,
        returns_sequence=returns_sequence,
        is_nn_module=_bases_look_like_module(bases),
        is_alias=is_alias,
        body_stmts=body_stmts,
        lineno=node.lineno,
    )


def _fn_params(fn: ast.FunctionDef) -> list[ParamInfo]:
    args = fn.args
    positional = list(args.args[1:])  # drop self
    defaults = list(args.defaults)
    pad = [None] * (len(positional) - len(defaults))
    default_nodes = pad + defaults
    params: list[ParamInfo] = []
    for arg, default in zip(positional, default_nodes, strict=True):
        params.append(
            ParamInfo(
                name=arg.arg,
                has_default=default is not None,
                default_repr=_const_repr(default) if default is not None else None,
            )
        )
    for arg, default in zip(args.kwonlyargs, args.kw_defaults, strict=True):
        params.append(
            ParamInfo(
                name=arg.arg,
                has_default=default is not None,
                default_repr=_const_repr(default) if default is not None else None,
            )
        )
    return params


def _fn_returns_sequence(fn: ast.FunctionDef) -> bool:
    for node in ast.walk(fn):
        if isinstance(node, ast.Return) and isinstance(node.value, (ast.Tuple, ast.List)):
            return True
    return False


def _const_repr(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant):
        return repr(node.value)
    return None


def _expr_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parts: list[str] = []
        current: ast.AST = node
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
            return ".".join(reversed(parts))
    return None


def _bases_look_like_module(bases: list[str]) -> bool:
    for base in bases:
        tail = base.split(".")[-1]
        if tail == "Module" or base in {"nn.Module", "torch.nn.Module"}:
            return True
    return False


def _mark_nn_modules(class_map: dict[str, ClassInfo]) -> None:
    changed = True
    while changed:
        changed = False
        for info in class_map.values():
            if info.is_nn_module:
                continue
            if any(class_map.get(base) and class_map[base].is_nn_module for base in info.bases):
                info.is_nn_module = True
                changed = True


def _resolve_params(target: ClassInfo, class_map: dict[str, ClassInfo]) -> list[ParamInfo]:
    current: ClassInfo | None = target
    seen: set[str] = set()
    while current is not None and current.name not in seen:
        seen.add(current.name)
        if current.init_params is not None:
            return current.init_params
        parent = next((class_map[base] for base in current.bases if base in class_map), None)
        current = parent
    return []


def _resolve_returns_sequence(target: ClassInfo, class_map: dict[str, ClassInfo]) -> bool:
    current: ClassInfo | None = target
    seen: set[str] = set()
    while current is not None and current.name not in seen:
        seen.add(current.name)
        if current.returns_sequence is not None:
            return current.returns_sequence
        parent = next((class_map[base] for base in current.bases if base in class_map), None)
        current = parent
    return False


def _wrapped_constructor(tree: ast.AST) -> str | None:
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or node.name != LAB_BUILD_NAME:
            continue
        for stmt in node.body:
            if not isinstance(stmt, ast.Assign):
                continue
            if not any(isinstance(target, ast.Name) and target.id == "model" for target in stmt.targets):
                continue
            if isinstance(stmt.value, ast.Call) and isinstance(stmt.value.func, ast.Name):
                return stmt.value.func.id
    return None


def _hint_maps_to_target(analysis: SourceAnalysis) -> bool:
    if analysis.target is None or not analysis.hint_model_name:
        return False
    hint = analysis.hint_model_name.strip().lower()
    mapped = analysis.name_registry.get(hint)
    if mapped == analysis.target.name:
        return True
    return analysis.target.name.lower() == hint.replace("_", "")


def _can_retarget_variant(analysis: SourceAnalysis, fail_stage: str | None) -> bool:
    if fail_stage != "load":
        return False
    if analysis.target is None or not analysis.wrapped_class:
        return False
    if analysis.wrapped_class == analysis.target.name:
        return False
    return _hint_maps_to_target(analysis)


def _dict_name_map(value: ast.AST) -> dict[str, str]:
    if not isinstance(value, ast.Dict):
        return {}
    mapping: dict[str, str] = {}
    for key, item in zip(value.keys, value.values, strict=True):
        if isinstance(key, ast.Constant) and isinstance(key.value, str) and isinstance(item, ast.Name):
            mapping[key.value.strip().lower()] = item.id
    return mapping


def _pick_target(
    class_map: dict[str, ClassInfo],
    all_names: list[str],
    entry_symbol: str,
    *,
    hint_model_name: str | None = None,
    name_registry: dict[str, str] | None = None,
) -> ClassInfo | None:
    candidates = [
        info
        for info in class_map.values()
        if info.is_nn_module and _has_num_classes(_resolve_params(info, class_map))
    ]
    if not candidates:
        return None
    if entry_symbol in class_map:
        chosen = class_map[entry_symbol]
        if chosen in candidates:
            return chosen

    hint = (hint_model_name or "").strip().lower()
    registry = name_registry or {}
    mapped = registry.get(hint) if hint else None
    if mapped and mapped in class_map:
        chosen = class_map[mapped]
        if chosen in candidates:
            return chosen

    compact_hint = hint.replace("_", "")

    def score(info: ClassInfo) -> tuple[int, int, str]:
        value = 0
        if info.name in all_names:
            value += 80
        if info.is_alias:
            value += 50
        if info.name == entry_symbol:
            value += 1000
        if mapped and info.name == mapped:
            value += 800
        if compact_hint and info.name.lower() == compact_hint:
            value += 400
        if BLOCK_NAME_RE.search(info.name):
            value -= 200
        return (value, info.body_stmts, info.name)

    return max(candidates, key=score)


def _has_num_classes(params: list[ParamInfo]) -> bool:
    return any(item.name in NUM_CLASS_NAMES for item in params)


def _call_kwargs(params: list[ParamInfo]) -> tuple[list[str], list[str]]:
    kwargs: list[str] = []
    missing: list[str] = []
    for item in params:
        if item.name in NUM_CLASS_NAMES:
            kwargs.append(f"{item.name}=num_classes")
        elif item.name in IN_CHANNEL_NAMES:
            kwargs.append(f"{item.name}=in_channels")
        elif "pretrained" in item.name.lower():
            kwargs.append(f"{item.name}=False")
        elif not item.has_default:
            missing.append(item.name)
    return kwargs, missing


def _classify(
    analysis: SourceAnalysis,
    entry_symbol: str,
    fail_stage: str | None,
    fail_message: str | None,
) -> list[str]:
    message = (fail_message or "").lower()
    kinds: list[str] = []
    if _can_retarget_variant(analysis, fail_stage):
        kinds.append("wrong_variant")
        return kinds
    if analysis.has_marker or analysis.has_lab_build:
        kinds.append("already_adapted")
        return kinds
    if fail_stage == "load":
        kinds.append("opinion_only")
        return kinds
    if fail_stage in OPINION_STAGES:
        kinds.append("opinion_only")
        return kinds
    if not analysis.has_build_model and (
        not analysis.entry_exists or entry_symbol != "build_model"
    ):
        kinds.append("missing_entry")
    if analysis.target and not any(p.name in IN_CHANNEL_NAMES for p in analysis.resolved_params):
        kinds.append("ctor_kwargs")
    if analysis.returns_sequence:
        kinds.append("multi_output")
    if fail_stage == "build" and "in_channels" in message and "ctor_kwargs" not in kinds:
        kinds.append("ctor_kwargs")
    if not kinds:
        kinds.append("opinion_only")
    return kinds


def _can_apply(
    analysis: SourceAnalysis,
    *,
    status: str,
    fail_stage: str | None,
    fail_message: str | None,
) -> tuple[bool, str | None]:
    if status != "cannot_start":
        return False, "仅不能启动的版本可追加适配"
    if analysis.parse_error:
        return False, analysis.apply_blocked_reason
    if "wrong_variant" in analysis.kinds:
        if analysis.target is None:
            return False, "未找到可包装的分割网络类（构造需能接收 num_classes）"
        if analysis.missing_required:
            names = "、".join(analysis.missing_required)
            return False, f"目标类还有未知的必填参数：{names}"
        return True, None
    if analysis.has_marker or analysis.has_lab_build:
        return False, "已追加过适配层，不再自动改"
    if fail_stage in OPINION_STAGES:
        if fail_stage == "load":
            return False, "加载失败只给意见，第一版不改权重加载逻辑"
        return False, "该失败阶段不在自动追加白名单"
    if fail_stage == "shape":
        return False, "输出形状失败可能涉及网络结构，不自动改"
    if fail_stage not in APPLY_STAGES and fail_stage is not None:
        return False, "该失败阶段不在自动追加白名单"
    if analysis.target is None:
        return False, "未找到可包装的分割网络类（构造需能接收 num_classes）"
    if analysis.missing_required:
        names = "、".join(analysis.missing_required)
        return False, f"目标类还有未知的必填参数：{names}"
    message = fail_message or ""
    if fail_stage == "forward" and not analysis.returns_sequence:
        return False, "前向失败且未发现 tuple/list 主输出，不自动改"
    if (
        fail_stage == "build"
        and "找不到入口" not in message
        and "unexpected keyword" not in message.lower()
        and "in_channels" not in message
        and "missing_entry" not in analysis.kinds
        and "ctor_kwargs" not in analysis.kinds
    ):
        return False, "构建失败原因不在白名单"
    return True, None

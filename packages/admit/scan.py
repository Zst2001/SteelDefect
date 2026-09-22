from __future__ import annotations

import ast
from dataclasses import dataclass

ALLOWED_MODULE_ROOTS = {
    "abc",
    "collections",
    "contextlib",
    "copy",
    "dataclasses",
    "enum",
    "functools",
    "__future__",
    "itertools",
    "math",
    "numbers",
    "numpy",
    "operator",
    "torch",
    "typing",
    "warnings",
}

ALLOWED_TORCH_PREFIXES = (
    "torch",
    "torch.nn",
    "torch.nn.functional",
    "torch.nn.init",
    "torch.nn.modules",
    "torch.nn.parameter",
)

BANNED_MODULE_ROOTS = {
    "aiohttp",
    "asyncio",
    "builtins",
    "concurrent",
    "ctypes",
    "dill",
    "docker",
    "ftplib",
    "glob",
    "http",
    "httpx",
    "importlib",
    "marshal",
    "mmap",
    "multiprocessing",
    "os",
    "pathlib",
    "pickle",
    "pip",
    "pty",
    "requests",
    "runpy",
    "setuptools",
    "shutil",
    "signal",
    "socket",
    "ssl",
    "subprocess",
    "sys",
    "tempfile",
    "urllib",
    "webbrowser",
}

BANNED_TORCH_PREFIXES = (
    "torch.hub",
    "torch.distributed",
    "torch.utils.data",
    "torch.multiprocessing",
)

BANNED_CALL_NAMES = {
    "Popen",
    "__import__",
    "breakpoint",
    "compile",
    "eval",
    "exec",
    "exit",
    "getattr",
    "input",
    "open",
    "popen",
    "system",
    "urlopen",
}

# nn.Module.eval() / train() must not be treated as the builtin eval().
BANNED_ATTR_CALLS = {
    "Popen",
    "__import__",
    "popen",
    "system",
    "urlopen",
}

SUGGEST = "请只保留网络结构与 forward，不要访问网络、子进程、磁盘或动态执行。"


@dataclass(frozen=True)
class ScanIssue:
    message: str
    line: int | None = None


def _module_root(name: str) -> str:
    return name.split(".", 1)[0]


def _torch_allowed(name: str) -> bool:
    if any(name == prefix or name.startswith(prefix + ".") for prefix in BANNED_TORCH_PREFIXES):
        return False
    return any(name == prefix or name.startswith(prefix + ".") for prefix in ALLOWED_TORCH_PREFIXES)


def _import_allowed(name: str) -> bool:
    if not name:
        return False
    root = _module_root(name)
    if root == "torch":
        return _torch_allowed(name)
    if root in BANNED_MODULE_ROOTS:
        return False
    return root in ALLOWED_MODULE_ROOTS


def _getattr_on_self(node: ast.Call) -> bool:
    if not node.args:
        return False
    first = node.args[0]
    return isinstance(first, ast.Name) and first.id == "self"


def scan_student_source(source: str, *, filename: str = "model.py") -> list[ScanIssue]:
    issues: list[ScanIssue] = []
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as exc:
        return [ScanIssue(f"源码无法解析：{exc.msg}", exc.lineno)]

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if not _import_allowed(alias.name):
                    issues.append(ScanIssue(f"不允许的导入 {alias.name}", node.lineno))
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                issues.append(ScanIssue("不允许相对导入（第一版仅单文件）", node.lineno))
                continue
            module = node.module or ""
            if not _import_allowed(module):
                issues.append(ScanIssue(f"不允许的导入 {module}", node.lineno))
                continue
            for alias in node.names:
                full = f"{module}.{alias.name}" if module else alias.name
                if alias.name != "*" and module.startswith("torch") and not _import_allowed(full):
                    issues.append(ScanIssue(f"不允许的导入 {full}", node.lineno))
                if alias.name == "*":
                    issues.append(ScanIssue("不允许 from ... import *", node.lineno))
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                name = func.id
                if name == "getattr" and _getattr_on_self(node):
                    continue
                if name in BANNED_CALL_NAMES:
                    issues.append(ScanIssue(f"不允许的调用 {name}()", node.lineno))
            elif isinstance(func, ast.Attribute) and func.attr in BANNED_ATTR_CALLS:
                issues.append(ScanIssue(f"不允许的调用 {func.attr}()", node.lineno))

    lowered = source.lower()
    for token, label in (
        ("os.system", "os.system"),
        ("subprocess", "subprocess"),
        ("torch.hub", "torch.hub"),
        ("pickle.loads", "pickle.loads"),
        ("__import__", "__import__"),
    ):
        if token in lowered and not any(token.split(".")[-1] in issue.message.lower() for issue in issues):
            issues.append(ScanIssue(f"源码包含阻断项 {label}", None))

    return issues


def scan_student_file(path: str) -> list[ScanIssue]:
    from pathlib import Path

    text = Path(path).read_text(encoding="utf-8")
    return scan_student_source(text, filename=path)


def format_static_failure(issues: list[ScanIssue]) -> str:
    if not issues:
        return ""
    first = issues[0]
    where = f" 第 {first.line} 行" if first.line else ""
    extra = f"（另有 {len(issues) - 1} 项）" if len(issues) > 1 else ""
    return f"{first.message}{where}。{SUGGEST}{extra}"

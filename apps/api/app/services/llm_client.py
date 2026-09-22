from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

SYSTEM_ADAPT = (
    "你是课题组实验台的「模型适配助手」。根据给定的失败阶段与 AST 诊断，"
    "用中文写 3 到 6 条给学生看的修改点。"
    "只解释接口适配（入口、构造参数、取 forward 返回值第 1 项、按 checkpoint 的 model_name 选源码里已有的消融变体），"
    "不要建议改网络结构或改统一类的默认开关。"
    "禁止写「模型不正确」「AI 已保证可运行」。"
    "不要建议去掉 module. 前缀或改 strict=False。"
    "每条一行，不要标题，不要代码块。"
)

SYSTEM_ADAPT_OPINION = (
    "你是课题组实验台的「模型适配助手」。这次失败不在自动追加白名单，不能改学生源码。"
    "根据失败阶段与检查器原文，用中文写 3 到 6 条学生可执行的修改意见。"
    "静态扫描或 import 失败时：点明被禁止的导入/调用，建议把需要的网络结构内联进这一份 .py，"
    "不要建议把被禁模块加入站点白名单，不要建议联网下载骨干，不要建议改检查器。"
    "禁止写「模型不正确」「AI 已保证可运行」。"
    "每条一行，不要标题，不要代码块。"
)


def chat_completion(
    messages: list[dict[str, str]],
    *,
    settings: Settings | None = None,
) -> str | None:
    settings = settings or get_settings()
    api_key = settings.resolved_llm_api_key
    if not api_key:
        return None
    base = settings.llm_base_url.rstrip("/")
    url = f"{base}/chat/completions"
    payload: dict[str, Any] = {
        "model": settings.llm_model,
        "messages": messages,
        "temperature": 0.2,
        "enable_thinking": False,
    }
    try:
        with httpx.Client(timeout=settings.llm_timeout_sec) as client:
            response = client.post(
                url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        if response.status_code >= 400:
            logger.warning(
                "llm chat_completion HTTP %s: %s",
                response.status_code,
                response.text[:300],
            )
            return None
        data = response.json()
        message = (data.get("choices") or [{}])[0].get("message") or {}
        content = message.get("content") or message.get("reasoning_content") or ""
        text = str(content).strip()
        return text or None
    except Exception:
        logger.warning("llm chat_completion failed", exc_info=True)
        return None


def draft_adapt_copy(
    summary: dict[str, Any],
    *,
    settings: Settings | None = None,
    can_apply: bool = True,
) -> str | None:
    system = SYSTEM_ADAPT if can_apply else SYSTEM_ADAPT_OPINION
    return chat_completion(
        [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": (
                    "请根据下列 JSON 写修改点。不要复述密钥或完整源码。\n"
                    + _safe_summary(summary)
                ),
            },
        ],
        settings=settings,
    )


def _safe_summary(summary: dict[str, Any]) -> str:
    import json

    allowed = {
        "fail_stage": summary.get("fail_stage"),
        "fail_message": (summary.get("fail_message") or "")[:400],
        "kinds": summary.get("kinds"),
        "target_class": summary.get("target_class"),
        "wrapped_class": summary.get("wrapped_class"),
        "hint_model_name": summary.get("hint_model_name"),
        "init_params": summary.get("init_params"),
        "returns_sequence": summary.get("returns_sequence"),
        "entry_symbol": summary.get("entry_symbol"),
        "preview_note": summary.get("preview_note"),
        "rule_points": summary.get("rule_points"),
        "can_apply": summary.get("can_apply"),
        "apply_blocked_reason": summary.get("apply_blocked_reason"),
    }
    return json.dumps(allowed, ensure_ascii=False)

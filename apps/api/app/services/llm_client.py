from __future__ import annotations

import json
import logging
from collections.abc import Iterator
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


def _chat_payload(settings: Settings, messages: list[dict[str, str]]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": settings.llm_model,
        "messages": messages,
        "temperature": 0.2,
    }
    host = settings.llm_base_url.lower()
    if "dashscope" in host:
        payload["enable_thinking"] = False
    elif "volces.com" in host or "volcengineapi.com" in host:
        payload["thinking"] = {"type": "disabled"}
    return payload


def _auth_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def _http_timeout(settings: Settings) -> httpx.Timeout:
    return httpx.Timeout(settings.llm_timeout_sec, connect=15.0)


def iter_chat_completion(
    messages: list[dict[str, str]],
    *,
    settings: Settings | None = None,
) -> Iterator[str]:
    settings = settings or get_settings()
    api_key = settings.resolved_llm_api_key
    if not api_key:
        return
    base = settings.llm_base_url.rstrip("/")
    url = f"{base}/chat/completions"
    payload = _chat_payload(settings, messages)
    payload["stream"] = True
    try:
        with httpx.Client(timeout=_http_timeout(settings), trust_env=False) as client:
            with client.stream("POST", url, headers=_auth_headers(api_key), json=payload) as response:
                if response.status_code >= 400:
                    body = response.read().decode("utf-8", errors="replace")[:300]
                    logger.warning("llm chat_completion HTTP %s: %s", response.status_code, body)
                    return
                for line in response.iter_lines():
                    if not line:
                        continue
                    text = line.decode("utf-8", errors="replace") if isinstance(line, bytes) else str(line)
                    if not text.startswith("data:"):
                        continue
                    data = text[5:].strip()
                    if not data or data == "[DONE]":
                        if data == "[DONE]":
                            break
                        continue
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    delta = (chunk.get("choices") or [{}])[0].get("delta") or {}
                    piece = delta.get("content")
                    if piece:
                        yield str(piece)
    except Exception:
        logger.warning("llm chat_completion stream failed", exc_info=True)
        return


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
    payload = _chat_payload(settings, messages)
    try:
        with httpx.Client(timeout=_http_timeout(settings), trust_env=False) as client:
            response = client.post(
                url,
                headers=_auth_headers(api_key),
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


HISTORY_MAX = 12
HISTORY_CHARS = 8000


def compose_chat_messages(
    system: str,
    *,
    history: list[dict[str, str]] | None = None,
    user_content: str,
) -> list[dict[str, str]]:
    messages = [{"role": "system", "content": system}]
    used = 0
    for item in (history or [])[-HISTORY_MAX:]:
        role = item.get("role")
        if role not in {"user", "assistant"}:
            continue
        text = str(item.get("content") or "").strip()[:2000]
        if not text:
            continue
        if used + len(text) > HISTORY_CHARS:
            break
        used += len(text)
        messages.append({"role": role, "content": text})
    messages.append({"role": "user", "content": user_content})
    return messages


SYSTEM_ANALYZE = (
    "你是课题组实验台的「科研助手」，当前专科是分割结果分析。"
    "只根据用户提供的证据包 JSON 写中文说明，不要使用包外知识编造数字。"
    "内容限于：数据质量、哪类或哪种尺度较弱、边界差异、协议是否一致、"
    "无 GT 时说明无法谈精度、下一步仍应在 AutoDL 上做的实验建议。"
    "每条结论单独成段，段首标注【测量事实】【规则判断】或【推测】。"
    "metrics.available 不为 true 时，禁止写 mIoU、mDice、Acc 或任何精度数字。"
    "禁止分析公开演示，禁止写「AI 已保证可运行」「模型不正确」「FPS 达到部署要求」。"
    "不要建议修改学生源码或改变模型可运行状态。"
    "不要输出 JSON。"
)


def analyze_messages(
    pack: dict[str, Any],
    *,
    question: str | None = None,
    history: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    payload = {
        "task": pack.get("task"),
        "metrics": pack.get("metrics"),
        "judgements": pack.get("judgements"),
        "question": (question or "").strip()[:2000] or None,
    }
    return compose_chat_messages(
        SYSTEM_ANALYZE,
        history=history,
        user_content=(
            "请根据证据包与对话历史回答。数字必须与 JSON 一致，不要丢掉上一轮已钉住的任务。\n"
            + json.dumps(payload, ensure_ascii=False, default=str)
        ),
    )


def draft_analyze_copy(
    pack: dict[str, Any],
    *,
    question: str | None = None,
    history: list[dict[str, str]] | None = None,
    settings: Settings | None = None,
) -> str | None:
    return chat_completion(
        analyze_messages(pack, question=question, history=history),
        settings=settings,
    )


SYSTEM_KB = (
    "你是课题组实验台的「科研助手」，当前专科是学术。"
    "只根据检索命中的语料转述，不要使用命中以外的知识，不要编造 DOI 或论文指标。"
    "禁止把第三方仓库写成本组成果，禁止把 NEU-20 或公开演示说成论文测试集。"
    "禁止报 mIoU / mDice / Acc，禁止报论文 GPU FPS。"
    "每段末尾用括号写来源标题。证据不足就写「语料未覆盖，不能回答」。"
    "不要输出 JSON。"
)


def kb_messages(
    question: str,
    hits: list[dict[str, Any]],
    *,
    history: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    payload = {
        "question": (question or "").strip()[:2000],
        "hits": [
            {
                "title": item.get("title"),
                "source": item.get("source"),
                "excerpt": item.get("excerpt"),
            }
            for item in hits
        ],
    }
    return compose_chat_messages(
        SYSTEM_KB,
        history=history,
        user_content=(
            "请只根据命中语料与对话历史回答。未出现的事实不要补。"
            + json.dumps(payload, ensure_ascii=False, default=str)
        ),
    )


def draft_kb_copy(
    question: str,
    hits: list[dict[str, Any]],
    *,
    history: list[dict[str, str]] | None = None,
    settings: Settings | None = None,
) -> str | None:
    return chat_completion(
        kb_messages(question, hits, history=history),
        settings=settings,
    )


SYSTEM_CODE = (
    "你是课题组实验台的「科研助手」，当前专科是模型源码建议。"
    "只给出中文说明与建议代码文本，不要声称已经写入磁盘或已经可运行。"
    "禁止建议 strict=False、去掉 module. 前缀、把被禁 import 加入站点白名单、代写全新网络。"
    "若失败落在适配助手可自动提案范围，引导学生到该版本模型卡，用模型适配助手同意追加并复检。"
    "不要输出 JSON。"
)


def code_messages(
    summary: dict[str, Any],
    *,
    history: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    return compose_chat_messages(
        SYSTEM_CODE,
        history=history,
        user_content=(
            "请根据下列 JSON 与对话历史写说明与建议代码。不要复述完整源码。"
            + json.dumps(summary, ensure_ascii=False, default=str)
        ),
    )


def draft_code_advice(
    summary: dict[str, Any],
    *,
    history: list[dict[str, str]] | None = None,
    settings: Settings | None = None,
) -> str | None:
    return chat_completion(
        code_messages(summary, history=history),
        settings=settings,
    )


def _safe_summary(summary: dict[str, Any]) -> str:

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

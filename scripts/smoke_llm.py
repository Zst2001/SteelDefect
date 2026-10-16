"""Live smoke: writing LLM via OpenAI-compatible chat/completions.

Does not print secrets. Requires .env LLM_API_KEY and network.
"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "apps" / "api"), str(ROOT / "packages")]

from app.config import Settings  # noqa: E402
from app.services.llm_client import _chat_payload, chat_completion  # noqa: E402


def main() -> int:
    settings = Settings()
    api_key = settings.resolved_llm_api_key
    if not api_key:
        print("FAIL: LLM_API_KEY is empty")
        return 1

    base = settings.llm_base_url.rstrip("/")
    url = f"{base}/chat/completions"
    messages = [
        {"role": "system", "content": "只回答一个词。"},
        {"role": "user", "content": "请只回复：pong"},
    ]
    payload = _chat_payload(settings, messages)
    payload["max_tokens"] = 32
    print(f"base={base}")
    print(f"model={settings.llm_model}")
    print(f"key_len={len(api_key)} suffix=...{api_key[-4:]}")
    print(f"url={url}")

    try:
        with httpx.Client(timeout=settings.llm_timeout_sec, trust_env=False) as client:
            response = client.post(
                url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
    except Exception as exc:
        print(f"FAIL: request error {type(exc).__name__}: {exc}")
        return 1

    body_preview = response.text[:400].replace("\n", " ")
    print(f"http={response.status_code}")
    if response.status_code >= 400:
        print(f"FAIL: HTTP {response.status_code} {body_preview}")
        return 1

    data = response.json()
    reply_model = data.get("model")
    message = (data.get("choices") or [{}])[0].get("message") or {}
    content = str(message.get("content") or message.get("reasoning_content") or "").strip()
    print(f"response_model={reply_model}")
    print(f"raw_reply={content[:120]!r}")

    via_client = chat_completion(messages, settings=settings)
    print(f"chat_completion={None if via_client is None else via_client[:120]!r}")

    if not content:
        print("FAIL: empty model content")
        return 1
    if reply_model and "deepseek" not in str(reply_model).lower() and "deepseek" in settings.llm_model:
        print(f"WARN: requested {settings.llm_model}, provider returned {reply_model}")
    if via_client is None:
        print("FAIL: chat_completion returned None after raw HTTP 200")
        return 1
    print("PASS: volcengine ark chat/completions reachable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

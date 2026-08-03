from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .utils import fingerprint_json, load_env


@dataclass(frozen=True)
class LLMConfig:
    api_key: str
    base_url: str
    model: str
    timeout_seconds: int = 180
    max_tokens: int = 9000
    format_mode: str = "json_object"
    thinking_mode: str = "disabled"

    @classmethod
    def from_env(cls, env_path: Path, **overrides: Any) -> "LLMConfig":
        values = load_env(env_path)
        missing = [
            key
            for key in ["THIRD_PARTY_API_KEY", "THIRD_PARTY_BASE_URL", "THIRD_PARTY_MODEL"]
            if not values.get(key)
        ]
        if missing:
            raise RuntimeError(f"LLM 配置缺失：{missing}")
        return cls(
            api_key=values["THIRD_PARTY_API_KEY"],
            base_url=values["THIRD_PARTY_BASE_URL"],
            model=values["THIRD_PARTY_MODEL"],
            **overrides,
        )

    @property
    def endpoint(self) -> str:
        base = self.base_url.rstrip("/")
        return base if base.endswith("/chat/completions") else f"{base}/chat/completions"


def extract_json_object(text: str) -> dict[str, Any]:
    value = (text or "").strip()
    if value.startswith("```"):
        lines = value.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        value = "\n".join(lines).strip()
    try:
        parsed = json.loads(value)
        if not isinstance(parsed, dict):
            raise ValueError("模型输出不是JSON对象")
        return parsed
    except json.JSONDecodeError:
        start = value.find("{")
        if start < 0:
            raise ValueError("模型输出中没有JSON对象")
        parsed, _ = json.JSONDecoder().raw_decode(value[start:])
        if not isinstance(parsed, dict):
            raise ValueError("模型输出不是JSON对象")
        return parsed


def render_template(path: Path, replacements: dict[str, str]) -> str:
    text = path.read_text(encoding="utf-8")
    for key, value in replacements.items():
        text = text.replace("{{" + key + "}}", value)
    return text


class OpenAICompatibleJSONClient:
    def __init__(self, config: LLMConfig):
        self.config = config

    @staticmethod
    def _message_text(response: dict[str, Any]) -> str:
        choices = response.get("choices") or []
        if not choices:
            raise ValueError("API 响应没有 choices")
        message = choices[0].get("message") or {}
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(
                item.get("text", "")
                for item in content
                if isinstance(item, dict)
            )
        raise ValueError("API 响应没有可解析的 message.content")

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            self.config.endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                request, timeout=self.config.timeout_seconds
            ) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"LLM API HTTP {exc.code}：{body[:1000]}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"LLM API 网络失败：{exc}") from exc
        parsed = json.loads(body)
        if not isinstance(parsed, dict):
            raise ValueError("LLM API 响应不是JSON对象")
        return parsed

    def complete_json(
        self,
        system_prompt: str,
        user_prompt: str,
        output_schema: dict[str, Any],
        schema_name: str,
    ) -> dict[str, Any]:
        modes = [self.config.format_mode]
        if self.config.format_mode != "prompt_only":
            modes.append("prompt_only")
        attempts: list[dict[str, Any]] = []
        for mode in modes:
            payload: dict[str, Any] = {
                "model": self.config.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "stream": False,
                "max_tokens": self.config.max_tokens,
            }
            if self.config.thinking_mode == "disabled":
                payload["thinking"] = {"type": "disabled"}
            if mode == "json_object":
                payload["response_format"] = {"type": "json_object"}
            elif mode == "json_schema":
                payload["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": schema_name,
                        "strict": True,
                        "schema": output_schema,
                    },
                }
            started = time.time()
            try:
                response = self._post(payload)
                elapsed = round(time.time() - started, 3)
                choices = response.get("choices") or []
                finish_reason = (
                    choices[0].get("finish_reason")
                    if choices and isinstance(choices[0], dict)
                    else None
                )
                if finish_reason == "length":
                    raw_text = self._message_text(response)
                    attempts.append(
                        {
                            "format_mode": mode,
                            "error": "模型输出因 max_tokens 限制被截断",
                            "raw_text_chars": len(raw_text),
                            "usage": response.get("usage"),
                        }
                    )
                    break
                raw_text = self._message_text(response)
                parsed = extract_json_object(raw_text)
                return {
                    "payload": parsed,
                    "raw_text": raw_text,
                    "transport": {
                        "endpoint": self.config.endpoint,
                        "model": self.config.model,
                        "format_mode": mode,
                        "response_id": response.get("id"),
                        "usage": response.get("usage"),
                        "finish_reason": finish_reason,
                        "elapsed_seconds": elapsed,
                    },
                }
            except Exception as exc:
                attempts.append({"format_mode": mode, "error": str(exc)})
        raise RuntimeError(f"LLM JSON调用失败：{attempts}")


def invocation_fingerprint(
    model: str,
    system_prompt: str,
    user_prompt: str,
    output_schema: dict[str, Any],
    generation_config: dict[str, Any] | None = None,
) -> str:
    return fingerprint_json(
        {
            "model": model,
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "output_schema": output_schema,
            "generation_config": generation_config or {},
        }
    )

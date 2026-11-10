"""OpenAI 兼容接口客户端（仅用标准库 urllib，无需 openai SDK）。"""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass

from .config import Settings


class LLMError(Exception):
    """模型调用失败，携带可读的失败原因。"""


@dataclass
class LLMResponse:
    message: dict
    prompt_tokens: int = 0
    completion_tokens: int = 0


class LLMClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def ready(self) -> bool:
        return self.settings.online_ready

    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> LLMResponse:
        if not self.settings.api_key:
            raise LLMError("未配置 API Key")

        url = self.settings.base_url.rstrip("/") + "/chat/completions"
        payload: dict = {
            "model": self.settings.model,
            "messages": messages,
            "temperature": float(self.settings.temperature),
            "stream": False,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.settings.api_key}",
                "Accept": "application/json",
            },
        )

        try:
            with urllib.request.urlopen(request, timeout=self.settings.timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="replace")[:300]
            except Exception:  # noqa: BLE001
                pass
            if exc.code in (401, 403):
                raise LLMError(f"鉴权失败（HTTP {exc.code}），请检查 API Key 是否正确") from exc
            if exc.code == 429:
                raise LLMError("请求频率或额度受限（HTTP 429），请稍后再试") from exc
            raise LLMError(f"接口返回错误 HTTP {exc.code}：{detail or exc.reason}") from exc
        except urllib.error.URLError as exc:
            raise LLMError(f"网络连接失败：{exc.reason}") from exc
        except socket.timeout as exc:
            raise LLMError(f"接口请求超时（{self.settings.timeout}s）") from exc
        except OSError as exc:
            raise LLMError(f"网络异常：{exc}") from exc

        try:
            data = json.loads(raw)
        except ValueError as exc:
            raise LLMError("接口返回内容不是合法 JSON，可能命中了错误的 base_url") from exc

        choices = data.get("choices") or []
        if not choices:
            message = (data.get("error") or {}).get("message") if isinstance(data, dict) else ""
            raise LLMError(f"接口未返回有效回答：{message or 'empty choices'}")

        message = choices[0].get("message") or {}
        usage = data.get("usage") or {}
        return LLMResponse(
            message=message,
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
        )

import os
from dataclasses import dataclass
from typing import Any, Dict, List

import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.config.models_config import MODELS


@dataclass
class Usage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass
class Message:
    content: str


@dataclass
class Choice:
    message: Message


@dataclass
class CompletionResponse:
    choices: List[Choice]
    usage: Usage


class _ChatCompletions:
    def __init__(self, client: "OpenAI") -> None:
        self._client = client

    def create(
        self,
        *,
        model: str,
        messages: List[Dict[str, Any]],
        temperature: float = 0.2,
    ) -> CompletionResponse:
        provider = _provider_for_model(model)
        if provider == "gemini":
            return _gemini_chat_completion(model, messages, temperature)
        if provider == "anthropic":
            return _anthropic_chat_completion(model, messages, temperature)
        if provider == "glm":
            return _glm_chat_completion(model, messages, temperature)
        return _openai_chat_completion(model, messages, temperature, self._client.api_key, self._client.base_url)


class _Chat:
    def __init__(self, client: "OpenAI") -> None:
        self.completions = _ChatCompletions(client)


class OpenAI:
    def __init__(self, api_key: str | None = None, base_url: str | None = None, **_: Any) -> None:
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.base_url = base_url
        self.chat = _Chat(self)


def _provider_for_model(model: str) -> str:
    info = MODELS.get(model, {})
    return info.get("provider", "openai")


@retry(
    retry=retry_if_exception_type(requests.exceptions.Timeout),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=4, max=30),
    reraise=True,
)
def _openai_chat_completion(
    model: str,
    messages: List[Dict[str, Any]],
    temperature: float,
    api_key: str | None,
    base_url: str | None = None,
) -> CompletionResponse:
    key = api_key or os.getenv("OPENAI_API_KEY", "")
    if not key:
        raise RuntimeError("OPENAI_API_KEY no está configurada.")
    
    url = f"{base_url.rstrip('/')}/chat/completions" if base_url else "https://api.openai.com/v1/chat/completions"
    
    payload: Dict[str, Any] = {"model": model, "messages": messages}
    if MODELS.get(model, {}).get("supports_temperature", True):
        payload["temperature"] = temperature

    response = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=120,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"OpenAI error {response.status_code}: {response.text}")
    data = response.json()
    content = data["choices"][0]["message"]["content"]
    usage_data = data.get("usage", {})
    usage = Usage(
        prompt_tokens=usage_data.get("prompt_tokens", 0),
        completion_tokens=usage_data.get("completion_tokens", 0),
        total_tokens=usage_data.get("total_tokens", 0),
    )
    return CompletionResponse(choices=[Choice(message=Message(content=content))], usage=usage)


def _gemini_chat_completion(
    model: str,
    messages: List[Dict[str, Any]],
    temperature: float,
) -> CompletionResponse:
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY no está configurada.")
    system_text = "\n".join(
        msg["content"] for msg in messages if msg.get("role") == "system"
    )
    contents = []
    for msg in messages:
        role = msg.get("role")
        if role == "system":
            continue
        mapped_role = "model" if role == "assistant" else "user"
        contents.append(
            {"role": mapped_role, "parts": [{"text": msg.get("content", "")}]}
        )
    model_path = model if model.startswith("models/") else f"models/{model}"
    url = (
        "https://generativelanguage.googleapis.com/v1beta/"
        f"{model_path}:generateContent?key={api_key}"
    )
    payload: Dict[str, Any] = {
        "contents": contents,
        "generationConfig": {"temperature": temperature},
    }
    if system_text:
        payload["systemInstruction"] = {"parts": [{"text": system_text}]}
    response = requests.post(url, json=payload, timeout=60)
    if response.status_code >= 400:
        raise RuntimeError(f"Gemini error {response.status_code}: {response.text}")
    data = response.json()
    content = ""
    if data.get("candidates"):
        parts = data["candidates"][0].get("content", {}).get("parts", [])
        if parts:
            content = parts[0].get("text", "")
    usage_data = data.get("usageMetadata", {})
    prompt_tokens = usage_data.get("promptTokenCount", 0)
    completion_tokens = usage_data.get("candidatesTokenCount", 0)
    usage = Usage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=usage_data.get(
            "totalTokenCount", prompt_tokens + completion_tokens
        ),
    )
    return CompletionResponse(choices=[Choice(message=Message(content=content))], usage=usage)


def _anthropic_chat_completion(
    model: str,
    messages: List[Dict[str, Any]],
    temperature: float,
) -> CompletionResponse:
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY no está configurada.")
    system_text = "\n".join(
        msg["content"] for msg in messages if msg.get("role") == "system"
    )
    filtered_messages = [
        {"role": msg.get("role"), "content": msg.get("content", "")}
        for msg in messages
        if msg.get("role") != "system"
    ]
    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": model,
            "max_tokens": 1024,
            "temperature": temperature,
            "messages": filtered_messages,
            "system": system_text,
        },
        timeout=60,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"Anthropic error {response.status_code}: {response.text}")
    data = response.json()
    content = ""
    if data.get("content"):
        content = data["content"][0].get("text", "")
    usage_data = data.get("usage", {})
    prompt_tokens = usage_data.get("input_tokens", 0)
    completion_tokens = usage_data.get("output_tokens", 0)
    usage = Usage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
    )
    return CompletionResponse(choices=[Choice(message=Message(content=content))], usage=usage)

def _glm_chat_completion(
    model: str,
    messages: List[Dict[str, Any]],
    temperature: float,
) -> CompletionResponse:
    
    api_key = os.getenv("GLM_API_KEY", "")
    if not api_key:
        raise RuntimeError("GLM_API_KEY no está configurada.")

    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

    response = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": messages,
            "temperature": temperature,
        },
        timeout=60,
    )

    if response.status_code >= 400:
        raise RuntimeError(f"GLM error {response.status_code}: {response.text}")

    data = response.json()

    content = data["choices"][0]["message"]["content"]

    usage_data = data.get("usage", {})
    usage = Usage(
        prompt_tokens=usage_data.get("prompt_tokens", 0),
        completion_tokens=usage_data.get("completion_tokens", 0),
        total_tokens=usage_data.get("total_tokens", 0),
    )

    return CompletionResponse(
        choices=[Choice(message=Message(content=content))],
        usage=usage,
    )
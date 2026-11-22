"""Cliente del modelo de lenguaje (chat).

Igual que con los embeddings, el resto del código depende de la interfaz `ChatLLM`
y no de OpenAI: en los tests usamos `FakeLLM` con respuestas predefinidas.
"""
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

from openai import OpenAI

from app.core.config import get_settings


@dataclass
class ChatMessage:
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass
class LLMResult:
    text: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0


class ChatLLM(Protocol):
    def complete(
        self, messages: list[ChatMessage], max_tokens: int = 800, json_mode: bool = False
    ) -> LLMResult: ...


class OpenAIChatLLM:
    def __init__(self, api_key: str, model: str, temperature: float | None):
        if not api_key:
            raise RuntimeError("Falta OPENAI_API_KEY en el .env")
        self.client = OpenAI(api_key=api_key, max_retries=3, timeout=60)
        self.model = model
        self.temperature = temperature

    def complete(
        self, messages: list[ChatMessage], max_tokens: int = 800, json_mode: bool = False
    ) -> LLMResult:
        kwargs = {}
        # Algunos modelos (los de razonamiento) no aceptan temperature: es opcional
        if self.temperature is not None:
            kwargs["temperature"] = self.temperature
        if json_mode:
            # Garantiza que la salida sea JSON válido (el prompt debe mencionar "JSON")
            kwargs["response_format"] = {"type": "json_object"}
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": m.role, "content": m.content} for m in messages],
            max_completion_tokens=max_tokens,
            **kwargs,
        )
        usage = response.usage
        return LLMResult(
            text=response.choices[0].message.content or "",
            model=response.model,
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
        )


class FakeLLM:
    """LLM de prueba: `responder` recibe los mensajes y devuelve el texto de respuesta.
    Guarda las llamadas en `calls` para que los tests inspeccionen el prompt."""

    def __init__(self, responder: Callable[[list[ChatMessage]], str]):
        self.responder = responder
        self.calls: list[list[ChatMessage]] = []

    def complete(
        self, messages: list[ChatMessage], max_tokens: int = 800, json_mode: bool = False
    ) -> LLMResult:
        self.calls.append(messages)
        return LLMResult(self.responder(messages), "fake-llm", 100, 20)


@lru_cache
def get_llm() -> ChatLLM:
    s = get_settings()
    return OpenAIChatLLM(s.openai_api_key, s.openai_chat_model, s.openai_temperature)


@lru_cache
def get_judge_llm() -> ChatLLM:
    """LLM evaluador. Puede ser un modelo distinto (a menudo más potente) que el del chat:
    un juez que comete los mismos errores que el evaluado detecta menos fallos."""
    s = get_settings()
    return OpenAIChatLLM(s.openai_api_key, s.eval_judge_model or s.openai_chat_model, 0.0)

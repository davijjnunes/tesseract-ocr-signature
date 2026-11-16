from collections.abc import Mapping, Sequence
from typing import Any, Literal

from ollama import ChatResponse, Client

from src.api.config import OLLAMA_HOST

SYSTEM_PROMPT = "Você analisa documentos e responde só com base na imagem."

USER_PROMPT = (
    "Esta imagem é um recorte da área de assinatura de um documento. Embaixo "
    "aparece o nome de quem assina em letra de fôrma impressa (fonte de "
    "computador). Acima ou por cima desse nome existe alguma escrita feita à mão "
    "com caneta? Conta como assinatura: nome escrito em letra cursiva (mesmo "
    "legível), rubrica, rabisco ou traços irregulares de caneta. Não conta: "
    "apenas o texto impresso, área vazia ou borrão sem traços nítidos. "
    'Responda em JSON: {"has_signature": true} ou {"has_signature": false}.'
)

DEFAULT_OPTIONS = {
    "temperature": 0,
    "top_p": 0.9,
    "top_k": 40,
    "min_p": 0.0,
    "seed": 42,
    "num_predict": 1024,
    "num_ctx": 4096,
    "num_gpu": -1,
    "num_thread": None,
    "num_batch": 512,
}

client = Client(
    host=OLLAMA_HOST,
    timeout=120,
)


def ollama_ask(
    model: str,
    messages: Sequence[Mapping[str, Any]],
    stream: Literal[False] = False,
    format: dict[str, Any] | Literal["", "json"] | None = None,
    keep_alive: str | float | None = "10m",
    think: bool | str | None = None,
    tools: Sequence[Any] | None = None,
    options: Mapping[str, Any] | None = None,
) -> ChatResponse:
    """Envia as mensagens ao Ollama e retorna a resposta do ``client.chat``."""
    return client.chat(
        model=model,
        messages=messages,
        stream=stream,
        format=format,
        keep_alive=keep_alive,
        think=think,
        tools=tools,
        options=DEFAULT_OPTIONS if options is None else options,
    )

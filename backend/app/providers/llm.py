import json
import logging
import urllib.error
import urllib.request

from app.config import ALLOWED_MODELS, settings

LOGGER = logging.getLogger("llm")
_CALLS = 0


def model_allowed(name: str) -> bool:
    return bool(name) and name.strip().lower() in ALLOWED_MODELS


def llm_status() -> dict:
    config = settings()
    if not (config.llm_base_url and config.llm_api_key and config.llm_model):
        return {
            "mode": "demo",
            "model": None,
            "note": "Параметры модели не заданы. Работает локальный движок, без вызова LLM и без расхода бюджета.",
        }
    if not model_allowed(config.llm_model):
        return {
            "mode": "demo",
            "model": None,
            "note": "Имя модели нет в списке, разрешенном организаторами. Вызов заблокирован.",
        }
    return {
        "mode": "live",
        "model": config.llm_model,
        "note": "Подключена разрешенная модель. Числа и упоминание банка проверяются отдельно.",
    }


def complete(messages: list[dict]) -> str | None:
    global _CALLS
    status = llm_status()
    config = settings()
    if status["mode"] != "live":
        return None
    if _CALLS >= config.llm_max_calls:
        LOGGER.info("llm skipped: call budget reached")
        return None
    _CALLS += 1
    body = json.dumps(
        {"model": config.llm_model, "messages": messages, "temperature": 0.2, "max_tokens": 700},
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{config.llm_base_url}/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {config.llm_api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return payload["choices"][0]["message"]["content"]
    except (urllib.error.URLError, KeyError, TypeError, json.JSONDecodeError, TimeoutError):
        LOGGER.info("llm request failed")
        return None


def reset_call_counter() -> None:
    global _CALLS
    _CALLS = 0

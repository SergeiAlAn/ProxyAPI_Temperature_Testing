"""Общение с OpenAI через proxyapi.ru."""

import csv
import logging
import time
from dataclasses import asdict, dataclass
from datetime import datetime

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    BadRequestError,
    RateLimitError,
)

import config

logger = logging.getLogger(__name__)

client = AsyncOpenAI(
    api_key=config.PROXY_API_KEY,
    base_url=config.PROXY_BASE_URL,
    timeout=config.REQUEST_TIMEOUT,
    max_retries=2,
)


class APIClientError(Exception):
    """Ошибка API с понятным пользователю текстом."""


@dataclass
class ChatResult:
    text: str
    request_id: str
    model: str
    temperature: float | None
    max_tokens: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_rub: float | None
    finish_reason: str
    elapsed_sec: float


def normalize_model(model: str) -> str:
    return model.strip().removeprefix("openai/")


def is_reasoning_model(model: str) -> bool:
    return normalize_model(model).startswith(config.REASONING_MODEL_PREFIXES)


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float | None:
    prices = config.PRICES_RUB_PER_1M.get(normalize_model(model))
    if not prices:
        return None
    price_in, price_out = prices
    return (prompt_tokens * price_in + completion_tokens * price_out) / 1_000_000


def _write_usage_csv(user_id: int, result: ChatResult) -> None:
    row = {"timestamp": datetime.now().isoformat(timespec="seconds"), "user_id": user_id}
    row.update(asdict(result))
    row["answer_len"] = len(row.pop("text"))
    is_new = not config.USAGE_CSV.exists()
    try:
        with open(config.USAGE_CSV, "a", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=list(row.keys()), delimiter=";")
            if is_new:
                writer.writeheader()
            writer.writerow(row)
    except OSError:
        logger.exception("Не удалось записать %s", config.USAGE_CSV)


async def ask_openai(
    messages: list[dict],
    model: str = config.MODEL,
    temperature: float = config.TEMPERATURE,
    max_tokens: int = config.MAX_TOKENS,
    user_id: int = 0,
) -> ChatResult:
    model = normalize_model(model)
    params = {"model": model, "messages": messages}
    if is_reasoning_model(model):
        params["max_completion_tokens"] = max_tokens
    else:
        params["temperature"] = temperature
        params["max_tokens"] = max_tokens

    logger.info(
        "Запрос -> user=%s %s messages=%s last=%r",
        user_id,
        {k: v for k, v in params.items() if k != "messages"},
        len(messages),
        messages[-1]["content"][:200],
    )

    started = time.perf_counter()
    try:
        response = await client.chat.completions.create(**params)
    except AuthenticationError as e:
        logger.error("Ошибка авторизации ProxyAPI: %s", e)
        raise APIClientError("Неверный ключ API. Проверьте PROXY_API_KEY в .env.") from e
    except RateLimitError as e:
        logger.error("Лимит запросов / недостаточно средств: %s", e)
        raise APIClientError("Превышен лимит запросов или закончился баланс. Попробуйте позже.") from e
    except BadRequestError as e:
        logger.error("Некорректный запрос (model=%s): %s", model, e)
        raise APIClientError(f"Некорректный запрос к модели «{model}». Проверьте название модели и параметры.") from e
    except APITimeoutError as e:
        logger.error("Таймаут запроса: %s", e)
        raise APIClientError("Модель слишком долго отвечает. Попробуйте ещё раз.") from e
    except APIConnectionError as e:
        logger.error("Ошибка соединения с ProxyAPI: %s", e)
        raise APIClientError("Не удалось подключиться к API. Проверьте интернет.") from e
    except APIStatusError as e:
        logger.error("Ошибка API %s: %s", e.status_code, e)
        raise APIClientError(f"Сервис вернул ошибку {e.status_code}. Попробуйте позже.") from e

    elapsed = time.perf_counter() - started
    choice = response.choices[0]
    usage = response.usage
    prompt_tokens = usage.prompt_tokens if usage else 0
    completion_tokens = usage.completion_tokens if usage else 0

    result = ChatResult(
        text=(choice.message.content or "").strip(),
        request_id=response.id,
        model=response.model or model,
        temperature=None if is_reasoning_model(model) else temperature,
        max_tokens=max_tokens,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=usage.total_tokens if usage else 0,
        cost_rub=estimate_cost(model, prompt_tokens, completion_tokens),
        finish_reason=choice.finish_reason or "",
        elapsed_sec=round(elapsed, 2),
    )

    logger.info(
        "Ответ <- user=%s id=%s tokens(prompt=%s, completion=%s, total=%s) "
        "cost≈%s₽ finish=%s time=%.2fs",
        user_id, result.request_id, result.prompt_tokens, result.completion_tokens,
        result.total_tokens, result.cost_rub, result.finish_reason, elapsed,
    )
    _write_usage_csv(user_id, result)
    return result

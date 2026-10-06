"""Настройки бота: токены из .env и параметры модели."""

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# --- Ключи (только из .env) ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
PROXY_API_KEY = (
    os.getenv("PROXY_API_KEY")
    or os.getenv("OPENAI_API_KEY")
    or os.getenv("GENAPI_KEY")
    or ""
)

# --- ProxyAPI (OpenAI-совместимый эндпоинт) ---
PROXY_BASE_URL = os.getenv("PROXY_BASE_URL", "https://api.proxyapi.ru/openai/v1")
REQUEST_TIMEOUT = 60  # секунд

# --- Параметры модели по умолчанию (можно менять здесь или командами в боте) ---
MODEL = "gpt-5-nano"
TEMPERATURE = 0.7
MAX_TOKENS = 1000

SYSTEM_PROMPT = "Ты — дружелюбный и полезный ассистент. Отвечай на русском языке."

# --- Контекст ---
# Сколько последних сообщений (user + assistant) хранить для каждого пользователя.
MAX_HISTORY_MESSAGES = 20

# --- Цены ProxyAPI, ₽ за 1 млн токенов (ввод, вывод), с НДС ---
# Источник: https://proxyapi.ru/models/browse?cat=text&vendor=openai (на 06.10.2026).
# В каталоге модели называются "openai/<имя>", а в эндпоинт /openai/v1 передаётся имя без префикса.
PRICES_RUB_PER_1M = {
    "gpt-5-nano": (13.0, 104.0),
    "gpt-4.1-nano": (26.0, 104.0),
    "gpt-4o-mini": (39.0, 155.0),
    "gpt-4.1-mini": (104.0, 413.0),
    "gpt-3.5-turbo": (129.0, 387.0),
    "gpt-4o": (645.0, 2577.0),
}

# Модели, которые предлагает команда /model (от дешёвых к дорогим)
AVAILABLE_MODELS = list(PRICES_RUB_PER_1M)

# Рассуждающие модели не принимают temperature и max_tokens:
# для них отправляется max_completion_tokens, а temperature не передаётся.
REASONING_MODEL_PREFIXES = ("gpt-5", "o1", "o3", "o4")

# --- Логи ---
LOG_FILE = BASE_DIR / "bot.log"
USAGE_CSV = BASE_DIR / "usage_log.csv"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")


def setup_logging() -> None:
    fmt = logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")

    console = logging.StreamHandler()
    console.setFormatter(fmt)

    file_handler = RotatingFileHandler(
        LOG_FILE, maxBytes=2_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(LOG_LEVEL)
    root.handlers = [console, file_handler]

    # Не засоряем лог служебными сообщениями HTTP-библиотек
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)


def validate_config() -> None:
    missing = [
        name
        for name, value in (("BOT_TOKEN", BOT_TOKEN), ("PROXY_API_KEY", PROXY_API_KEY))
        if not value
    ]
    if missing:
        raise RuntimeError(
            f"Не заданы переменные окружения: {', '.join(missing)}. "
            "Создайте файл .env по образцу .env.example"
        )

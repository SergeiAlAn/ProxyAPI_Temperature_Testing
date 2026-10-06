"""Хранение контекста диалога и настроек каждого пользователя в оперативной памяти."""

import logging
from dataclasses import dataclass, field

import config

logger = logging.getLogger(__name__)


@dataclass
class UserSettings:
    model: str = config.MODEL
    temperature: float = config.TEMPERATURE
    max_tokens: int = config.MAX_TOKENS


@dataclass
class UserState:
    history: list[dict] = field(default_factory=list)
    settings: UserSettings = field(default_factory=UserSettings)
    last_usage: dict | None = None


class ContextManager:
    def __init__(self, max_messages: int = config.MAX_HISTORY_MESSAGES):
        self.max_messages = max_messages
        self._users: dict[int, UserState] = {}

    def _state(self, user_id: int) -> UserState:
        if user_id not in self._users:
            self._users[user_id] = UserState()
        return self._users[user_id]

    def get_history(self, user_id: int) -> list[dict]:
        return list(self._state(user_id).history)

    def build_messages(self, user_id: int, user_text: str) -> list[dict]:
        """Системный промпт + история + новое сообщение пользователя."""
        return [
            {"role": "system", "content": config.SYSTEM_PROMPT},
            *self.get_history(user_id),
            {"role": "user", "content": user_text},
        ]

    def add_exchange(self, user_id: int, user_text: str, bot_text: str) -> None:
        history = self._state(user_id).history
        history.append({"role": "user", "content": user_text})
        history.append({"role": "assistant", "content": bot_text})
        if len(history) > self.max_messages:
            del history[: len(history) - self.max_messages]
        logger.debug("user=%s history_len=%s", user_id, len(history))

    def reset(self, user_id: int) -> None:
        self._state(user_id).history.clear()
        logger.info("Контекст очищен: user=%s", user_id)

    def get_settings(self, user_id: int) -> UserSettings:
        return self._state(user_id).settings

    def reset_settings(self, user_id: int) -> None:
        self._state(user_id).settings = UserSettings()

    def set_last_usage(self, user_id: int, usage: dict) -> None:
        self._state(user_id).last_usage = usage

    def get_last_usage(self, user_id: int) -> dict | None:
        return self._state(user_id).last_usage


context_manager = ContextManager()

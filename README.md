# Telegram-бот с контекстом (aiogram + ProxyAPI)

Мини-бот: ведёт диалог через OpenAI-модели на [proxyapi.ru](https://proxyapi.ru), помнит последние сообщения каждого пользователя (dict в оперативной памяти), умеет очищать контекст.

## Структура

| Файл | Назначение |
|---|---|
| `bot.py` | Основной файл: aiogram, хэндлеры команд и диалога |
| `config.py` | Токены из `.env`, модель, temperature, max_tokens, цены, логирование |
| `context_manager.py` | Хранение/загрузка/очистка контекста и настроек пользователя |
| `openai_client.py` | Запрос к OpenAI через ProxyAPI, обработка ошибок, подсчёт токенов и стоимости |
| `api_client.py` | Имя модуля из задания; реэкспортирует `openai_client.py` |
| `.env.example` | Образец файла с ключами |
| `bot.log` | Лог ошибок и отправляемых параметров (создаётся автоматически) |
| `usage_log.csv` | Каждый запрос: параметры, ID, токены, стоимость (для отчёта) |

## Запуск

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env   # и впишите BOT_TOKEN и PROXY_API_KEY
python bot.py
```

Модель и параметры по умолчанию меняются в `config.py` (`MODEL`, `TEMPERATURE`, `MAX_TOKENS`, `MAX_HISTORY_MESSAGES`, `SYSTEM_PROMPT`).

## Команды бота

- обычный текст — диалог с учётом контекста;
- `/reset` или «очистить контекст» — очистить историю;
- `/settings` — текущие модель/temperature/max_tokens;
- `/model gpt-4o`, `/temp 1.2`, `/max_tokens 100` — сменить параметры для себя (для экспериментов);
- `/defaults` — вернуть параметры из `config.py`;
- `/usage` — ID запроса, токены и стоимость последнего ответа;
- `/help` — справка.

## Логирование

В консоль и в `bot.log` пишутся: модель, temperature, max_tokens, число сообщений в контексте, начало запроса; ID ответа, токены, стоимость, `finish_reason`, время; все ошибки API (неверный ключ, лимит/баланс, неверная модель, таймаут, сеть) и необработанные исключения. Ключи в лог не попадают.

---

# Отчёт

**Методика.** Один и тот же промпт после `/reset`, меняются только параметры (`/temp`, `/max_tokens`, `/model`).
Промпт: «Придумай слоган для кофейни у моря».
Данные берутся из `/usage` или `usage_log.csv`. Цены — из `PRICES_RUB_PER_1M` в `config.py` (ориентировочные, сверить с [прайсом ProxyAPI](https://proxyapi.ru/pricing)).

| Модель | temperature | max_tokens | № прогона | Эффект (сжатость / креатив) | Токены (prompt + completion = total) | Стоимость, ₽ | ID запроса |
|---|---|---|---|---|---|---|---|
| gpt-4o-mini | 0.2 | 50 | 1 | | | | |
| gpt-4o-mini | 0.2 | 50 | 2 | | | | |
| gpt-4o-mini | 0.7 | 150 | 3 | | | | |
| gpt-4o-mini | 0.7 | 150 | 4 | | | | |
| gpt-4o-mini | 1.2 | 150 | 5 | | | | |
| gpt-4o-mini | 1.2 | 500 | 6 | | | | |
| gpt-4o | 0.7 | 150 | 7 | | | | |

**Выводы** (заполнить по результатам):

- низкая temperature (0–0.3): ответы ...;
- высокая temperature (1.0+): ответы ...;
- маленький max_tokens: ответ ... (`finish_reason=length`, бот предупреждает об обрезке);
- контекст увеличивает prompt_tokens с каждым сообщением: ...

## Скриншот Usage / ID запросов

ID запросов — в таблице выше (поле `request_id` из `/usage` и `usage_log.csv`).
Скриншот раздела баланса/статистики личного кабинета ProxyAPI:

![Usage ProxyAPI](screenshots/usage.png)

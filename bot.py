"""Telegram-бот с контекстом диалога (aiogram 3 + ProxyAPI)."""

import asyncio
import logging

from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ChatAction, ParseMode
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import BotCommand, ErrorEvent, Message

import config
from api_client import APIClientError, ask_openai
from context_manager import context_manager

logger = logging.getLogger("bot")
router = Router()

TELEGRAM_LIMIT = 4096
RESET_PHRASES = {"очистить контекст", "сбросить контекст", "reset"}

HELP_TEXT = (
    "Я помню наш диалог (последние {n} сообщений).\n\n"
    "<b>Команды:</b>\n"
    "/reset или «очистить контекст» — забыть историю\n"
    "/settings — текущие параметры модели\n"
    "/model &lt;название&gt; — сменить модель (например, /model gpt-4o)\n"
    "/temp &lt;0..2&gt; — temperature\n"
    "/max_tokens &lt;число&gt; — лимит токенов ответа\n"
    "/defaults — вернуть параметры по умолчанию\n"
    "/usage — токены и стоимость последнего ответа\n"
    "/help — эта справка"
)


def split_text(text: str, limit: int = TELEGRAM_LIMIT) -> list[str]:
    parts = []
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        if cut <= 0:
            cut = limit
        parts.append(text[:cut])
        text = text[cut:].lstrip("\n")
    if text:
        parts.append(text)
    return parts


def format_usage(u: dict) -> str:
    cost = f"{u['cost_rub']:.4f} ₽" if u["cost_rub"] is not None else "нет цены в config"
    temperature = u["temperature"] if u["temperature"] is not None else "не поддерживается моделью"
    return (
        f"<b>Последний запрос</b>\n"
        f"ID: <code>{u['request_id']}</code>\n"
        f"Модель: {u['model']}\n"
        f"temperature: {temperature}, max_tokens: {u['max_tokens']}\n"
        f"Токены: prompt {u['prompt_tokens']} + completion {u['completion_tokens']} "
        f"= {u['total_tokens']}\n"
        f"Стоимость ≈ {cost}\n"
        f"finish_reason: {u['finish_reason']}, время: {u['elapsed_sec']} с"
    )


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    context_manager.reset(message.from_user.id)
    await message.answer(
        f"Привет, {message.from_user.first_name}! Напиши мне что-нибудь.\n\n"
        + HELP_TEXT.format(n=config.MAX_HISTORY_MESSAGES),
        parse_mode=ParseMode.HTML,
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        HELP_TEXT.format(n=config.MAX_HISTORY_MESSAGES), parse_mode=ParseMode.HTML
    )


@router.message(Command("reset"))
@router.message(F.text.lower().strip().in_(RESET_PHRASES))
async def cmd_reset(message: Message) -> None:
    context_manager.reset(message.from_user.id)
    await message.answer("🧹 Контекст очищен. Начнём сначала!")


@router.message(Command("settings"))
async def cmd_settings(message: Message) -> None:
    s = context_manager.get_settings(message.from_user.id)
    history_len = len(context_manager.get_history(message.from_user.id))
    await message.answer(
        f"<b>Текущие параметры</b>\n"
        f"Модель: <code>{s.model}</code>\n"
        f"temperature: {s.temperature}\n"
        f"max_tokens: {s.max_tokens}\n"
        f"Сообщений в контексте: {history_len}/{config.MAX_HISTORY_MESSAGES}",
        parse_mode=ParseMode.HTML,
    )


@router.message(Command("model"))
async def cmd_model(message: Message, command: CommandObject) -> None:
    if not command.args:
        lines = [
            f"<code>{name}</code> — ввод {p_in:g} ₽, вывод {p_out:g} ₽ за 1М токенов"
            for name, (p_in, p_out) in config.PRICES_RUB_PER_1M.items()
        ]
        await message.answer(
            "Укажите модель: /model gpt-4o-mini\n\n" + "\n".join(lines),
            parse_mode=ParseMode.HTML,
        )
        return
    s = context_manager.get_settings(message.from_user.id)
    s.model = command.args.strip().removeprefix("openai/")
    logger.info("user=%s model=%s", message.from_user.id, s.model)
    await message.answer(f"Модель: {s.model}")


@router.message(Command("temp"))
async def cmd_temp(message: Message, command: CommandObject) -> None:
    try:
        value = float((command.args or "").replace(",", "."))
        if not 0 <= value <= 2:
            raise ValueError
    except ValueError:
        await message.answer("Укажите число от 0 до 2: /temp 0.7")
        return
    context_manager.get_settings(message.from_user.id).temperature = value
    logger.info("user=%s temperature=%s", message.from_user.id, value)
    await message.answer(f"temperature = {value}")


@router.message(Command("max_tokens"))
async def cmd_max_tokens(message: Message, command: CommandObject) -> None:
    try:
        value = int(command.args or "")
        if not 1 <= value <= 16000:
            raise ValueError
    except ValueError:
        await message.answer("Укажите целое число от 1 до 16000: /max_tokens 300")
        return
    context_manager.get_settings(message.from_user.id).max_tokens = value
    logger.info("user=%s max_tokens=%s", message.from_user.id, value)
    await message.answer(f"max_tokens = {value}")


@router.message(Command("defaults"))
async def cmd_defaults(message: Message) -> None:
    context_manager.reset_settings(message.from_user.id)
    await message.answer("Параметры сброшены к значениям из config.py")


@router.message(Command("usage"))
async def cmd_usage(message: Message) -> None:
    usage = context_manager.get_last_usage(message.from_user.id)
    if not usage:
        await message.answer("Запросов к модели ещё не было.")
        return
    await message.answer(format_usage(usage), parse_mode=ParseMode.HTML)


@router.message(F.text & ~F.text.startswith("/"))
async def handle_text(message: Message, bot: Bot) -> None:
    user_id = message.from_user.id
    user_text = message.text.strip()
    settings = context_manager.get_settings(user_id)

    await bot.send_chat_action(message.chat.id, ChatAction.TYPING)
    messages = context_manager.build_messages(user_id, user_text)

    try:
        result = await ask_openai(
            messages,
            model=settings.model,
            temperature=settings.temperature,
            max_tokens=settings.max_tokens,
            user_id=user_id,
        )
    except APIClientError as e:
        await message.answer(f"⚠️ {e}")
        return

    answer = result.text or "(модель вернула пустой ответ)"
    if result.finish_reason == "length":
        answer += "\n\n✂️ Ответ обрезан лимитом max_tokens."

    context_manager.add_exchange(user_id, user_text, result.text)
    context_manager.set_last_usage(user_id, result.__dict__)

    for part in split_text(answer):
        await message.answer(part)


@router.message()
async def handle_other(message: Message) -> None:
    await message.answer("Я понимаю только текстовые сообщения. /help — список команд.")


@router.error()
async def on_error(event: ErrorEvent) -> None:
    logger.exception("Необработанная ошибка: %s", event.exception, exc_info=event.exception)
    message = event.update.message
    if message:
        await message.answer("😔 Произошла внутренняя ошибка. Попробуйте ещё раз.")


async def main() -> None:
    config.setup_logging()
    config.validate_config()

    bot = Bot(token=config.BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    await bot.set_my_commands([
        BotCommand(command="reset", description="Очистить контекст"),
        BotCommand(command="settings", description="Текущие параметры"),
        BotCommand(command="usage", description="Токены последнего ответа"),
        BotCommand(command="help", description="Справка"),
    ])

    logger.info(
        "Бот запущен. model=%s temperature=%s max_tokens=%s base_url=%s",
        config.MODEL, config.TEMPERATURE, config.MAX_TOKENS, config.PROXY_BASE_URL,
    )
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен")

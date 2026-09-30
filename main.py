import os as _os
from pathlib import Path as _Path

# Токен бота берётся из .env рядом с этим файлом.
_env_file = _Path(__file__).with_name(".env")
if _env_file.exists():
    for _line in _env_file.read_text(encoding="utf-8").splitlines():
        if "=" in _line and not _line.lstrip().startswith("#"):
            _key, _value = _line.split("=", 1)
            _os.environ.setdefault(_key.strip(), _value.strip().strip('"').strip("'"))

import asyncio
import logging
from io import BytesIO
from urllib.parse import quote_plus

from aiogram import Bot, Dispatcher, F, Router, types
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
# googletrans 4.0.0rc1 давно не обновлялся и регулярно ломается — deep-translator поддерживается
from deep_translator import GoogleTranslator
# PyPDF2 заброшен (CVE-2023-36464: бесконечный цикл на специально собранном PDF) — pypdf его преемник.
from pypdf import PdfReader

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("search_bot")

router = Router()

MAX_PDF_BYTES = 10 * 1024 * 1024
MAX_PDF_PAGES = 30
MAX_TEXT_LENGTH = 4000       # лимит Telegram — 4096 символов на сообщение
MAX_TRANSLATE_LENGTH = 5000  # лимит одного запроса к Google Translate
HISTORY_SIZE = 20
LANG_NAMES = {"ru": "Русский", "en": "English", "es": "Español", "fr": "Français", "de": "Deutsch", "it": "Italiano"}

# Язык интерфейса и язык перевода хранятся раздельно: выбор «Español» для перевода
# не должен менять язык справки.
interface_language: dict[int, str] = {}
target_language: dict[int, str] = {}
translation_history: dict[int, list[str]] = {}


def translate_text(text: str, target: str) -> str:
    return GoogleTranslator(source="auto", target=target).translate(text[:MAX_TRANSLATE_LENGTH]) or ""


async def safe_translate(text: str, target: str) -> str | None:
    try:
        return await asyncio.to_thread(translate_text, text, target)
    except Exception:
        log.exception("Ошибка перевода")
        return None


def search_keyboard(query: str) -> InlineKeyboardMarkup:
    # Обычный текст: перевод и кнопки поиска в Google и Яндексе
    q = quote_plus(query[:300])
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🔎 Google", url=f"https://www.google.com/search?q={q}"),
        InlineKeyboardButton(text="🔎 Яндекс", url=f"https://yandex.ru/search/?text={q}"),
    ]])


def remember(user_id: int, source: str, translated: str) -> None:
    history = translation_history.setdefault(user_id, [])
    history.append(f"{source[:200]} → {translated[:200]}")
    del history[:-HISTORY_SIZE]  # храним только последние записи


def command_argument(message: types.Message) -> str:
    parts = (message.text or "").split(maxsplit=1)
    return parts[1].strip() if len(parts) > 1 else ""


@router.message(Command(commands=["start"]))
async def start_command(message: types.Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Русский 🇷🇺", callback_data="lang_ru"),
         InlineKeyboardButton(text="English 🇬🇧", callback_data="lang_en")]
    ])
    await message.answer("👋 Привет! Я бот для поиска информации и перевода.\n\nВыберите язык интерфейса:",
                         reply_markup=keyboard)


@router.callback_query(F.data.in_({"lang_ru", "lang_en"}))
async def set_language(callback: CallbackQuery):
    lang = callback.data.split("_", 1)[1]
    interface_language[callback.from_user.id] = lang
    await callback.answer()
    await callback.message.edit_text(f"🌐 Вы выбрали язык: {LANG_NAMES[lang]}.", reply_markup=None)


@router.message(Command(commands=["help"]))
async def help_command(message: types.Message):
    if interface_language.get(message.from_user.id, "en") == "ru":
        text = ("ℹ Справка:\n"
                "- Отправьте текст — я переведу его и дам ссылки для поиска в Google и Яндексе.\n"
                "- /choose_language — язык перевода, /translate текст, /translate_multi текст.\n"
                "- Загрузите PDF-файл, чтобы я извлёк из него текст.\n"
                "- /history — последние переводы.")
    else:
        text = ("ℹ Help:\n"
                "- Send any text: I will translate it and give Google / Yandex search links.\n"
                "- /choose_language — translation language, /translate text, /translate_multi text.\n"
                "- Upload a PDF file to extract its text.\n"
                "- /history — recent translations.")
    await message.answer(text)


@router.message(Command(commands=["about"]))
async def about_command(message: types.Message):
    if interface_language.get(message.from_user.id, "en") == "ru":
        await message.answer("🤖 Я бот для поиска, перевода и работы с PDF файлами.")
    else:
        await message.answer("🤖 I am a bot for searching, translating, and working with PDF files.")


@router.message(Command(commands=["choose_language"]))
async def choose_language_command(message: types.Message):
    codes = list(LANG_NAMES)
    rows = [[InlineKeyboardButton(text=LANG_NAMES[c], callback_data=f"translate_to_{c}") for c in codes[i:i + 2]]
            for i in range(0, len(codes), 2)]
    await message.answer("🌐 Выберите язык, на который вы хотите переводить:",
                         reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data.startswith("translate_to_"))
async def set_translation_language(callback: CallbackQuery):
    lang = callback.data.removeprefix("translate_to_")
    if lang not in LANG_NAMES:
        await callback.answer("Неизвестный язык")
        return
    target_language[callback.from_user.id] = lang
    await callback.answer()
    await callback.message.edit_text(f"🌐 Вы выбрали язык для перевода: {LANG_NAMES[lang]}.", reply_markup=None)


@router.message(Command(commands=["translate_multi"]))
async def translate_multi_command(message: types.Message):
    query = command_argument(message)
    if not query:
        await message.answer("Введите текст для перевода после команды /translate_multi.")
        return
    results = await asyncio.gather(*(safe_translate(query, lang) for lang in ("en", "es", "fr", "de", "it")))
    lines = [f"{lang}: {text}" for lang, text in zip(("en", "es", "fr", "de", "it"), results) if text]
    await message.answer("🌐 Перевод в несколько языков:\n" + "\n".join(lines) if lines
                         else "⚠ Не удалось перевести, попробуйте позже.")


@router.message(Command(commands=["history"]))
async def history_command(message: types.Message):
    history = translation_history.get(message.from_user.id, [])
    if not history:
        await message.answer("ℹ История переводов пуста.")
        return
    await message.answer("📜 Ваша история переводов:\n" + "\n".join(f"{i + 1}. {item}" for i, item in enumerate(history)))


async def translate_and_reply(message: types.Message, query: str):
    target = target_language.get(message.from_user.id, "en")
    translated = await safe_translate(query, target)
    if translated is None:
        await message.answer("⚠ Не удалось перевести, попробуйте позже.", reply_markup=search_keyboard(query))
        return
    remember(message.from_user.id, query, translated)
    # Без parse_mode: переведённый текст — пользовательские данные, HTML в нём не нужен
    await message.answer(f"🌐 Перевод ({LANG_NAMES.get(target, target)}):\n{translated[:MAX_TEXT_LENGTH]}",
                         reply_markup=search_keyboard(query))


@router.message(Command(commands=["translate"]))
async def translate_command(message: types.Message):
    query = command_argument(message)
    if not query:
        await message.answer("Введите текст для перевода после команды /translate.")
        return
    await translate_and_reply(message, query)


@router.message(F.voice)
async def handle_voice(message: types.Message):
    await message.answer("🎙 Голосовое сообщение получено, но преобразование в текст не реализовано.")


@router.message(F.document)
async def handle_pdf(message: types.Message, bot: Bot):
    document = message.document
    if not (document.file_name or "").lower().endswith(".pdf"):
        await message.answer("❌ Пожалуйста, загрузите PDF файл.")
        return
    if (document.file_size or 0) > MAX_PDF_BYTES:
        await message.answer("❌ Файл слишком большой (максимум 10 МБ).")
        return

    buffer = BytesIO()
    await bot.download(file=document.file_id, destination=buffer)
    try:
        text = await asyncio.to_thread(extract_text_from_pdf, buffer)
    except Exception:
        # Текст исключения пользователю не показываем.
        log.exception("PDF processing failed")
        await message.answer("⚠ Не удалось обработать PDF файл.")
        return
    if not text.strip():
        await message.answer("❌ Не удалось извлечь текст из PDF файла.")
        return
    # Обычный текст без HTML: экранирование после обрезки до 4000 символов
    # могло бы вывести сообщение за лимит Telegram.
    suffix = "…" if len(text) > MAX_TEXT_LENGTH else ""
    await message.answer(f"📄 Содержимое PDF файла:\n{text[:MAX_TEXT_LENGTH]}{suffix}")


@router.message(F.text & ~F.text.startswith("/"))
async def handle_text(message: types.Message):
    await translate_and_reply(message, message.text.strip())


def extract_text_from_pdf(source):
    reader = PdfReader(source)
    parts = []
    for page in reader.pages[:MAX_PDF_PAGES]:  # ограничение против «PDF-бомб» на тысячи страниц
        parts.append(page.extract_text() or "")
        if sum(map(len, parts)) > 8000:
            break
    return "".join(parts)


async def main():
    bot = Bot(token=_os.environ["TELEGRAM_BOT_TOKEN"])
    dp = Dispatcher()
    dp.include_router(router)
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())

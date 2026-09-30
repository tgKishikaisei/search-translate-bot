"""Тесты без сети. Запуск: python -m pytest tests"""
import asyncio
import importlib
import sys
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
USER = 5


@pytest.fixture()
def app(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:TEST")
    sys.modules.pop("main", None)
    main = importlib.import_module("main")
    monkeypatch.setattr(main, "translate_text", lambda text, target: f"[{target}] {text}")
    return main


def msg(text):
    return SimpleNamespace(text=text, from_user=SimpleNamespace(id=USER), answer=AsyncMock())


def test_plain_text_gets_translation_and_search_links(app):
    m = msg("кот <b>")
    asyncio.run(app.handle_text(m))
    text = m.answer.await_args.args[0]
    markup = m.answer.await_args.kwargs["reply_markup"]
    assert "[en] кот <b>" in text
    assert markup.inline_keyboard[0][0].url == "https://www.google.com/search?q=%D0%BA%D0%BE%D1%82+%3Cb%3E"


def test_translation_language_does_not_change_interface(app):
    cb = SimpleNamespace(data="translate_to_es", from_user=SimpleNamespace(id=USER), answer=AsyncMock(),
                         message=SimpleNamespace(edit_text=AsyncMock()))
    asyncio.run(app.set_translation_language(cb))
    m = msg("/help")
    asyncio.run(app.help_command(m))
    assert m.answer.await_args.args[0].startswith("ℹ Help")  # интерфейс остался прежним
    m2 = msg("hola")
    asyncio.run(app.handle_text(m2))
    assert "[es] hola" in m2.answer.await_args.args[0]


def test_history_is_limited(app):
    for i in range(30):
        asyncio.run(app.handle_text(msg(f"слово {i}")))
    assert len(app.translation_history[USER]) == app.HISTORY_SIZE


def test_translation_error_is_reported(app, monkeypatch):
    def boom(text, target):
        raise RuntimeError("network")
    monkeypatch.setattr(app, "translate_text", boom)
    m = msg("text")
    asyncio.run(app.handle_text(m))
    assert "Не удалось" in m.answer.await_args.args[0]


def test_pdf_extraction_respects_limits(app):
    from pypdf import PdfWriter
    writer = PdfWriter()
    for _ in range(40):
        writer.add_blank_page(width=200, height=200)
    buffer = BytesIO()
    writer.write(buffer)
    buffer.seek(0)
    assert app.extract_text_from_pdf(buffer) == ""


def test_long_pdf_text_fits_telegram_limit(app, monkeypatch):
    monkeypatch.setattr(app, "extract_text_from_pdf", lambda source: "<&>" * 5000)
    bot = SimpleNamespace(download=AsyncMock())
    m = SimpleNamespace(document=SimpleNamespace(file_name="a.pdf", file_size=100, file_id="f"), answer=AsyncMock())
    asyncio.run(app.handle_pdf(m, bot))
    assert len(m.answer.await_args.args[0]) <= 4096

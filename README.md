# Search & Translate Bot

Telegram-бот для быстрого перевода. Пишете ему текст: он переводит на выбранный язык и прикладывает кнопки поиска этой фразы в Google и Яндексе. Пришлёте PDF, и бот вернёт текст из файла.

[![License](https://img.shields.io/github/license/tgKishikaisei/search-translate-bot)](LICENSE)
[![CI](https://img.shields.io/github/actions/workflow/status/tgKishikaisei/search-translate-bot/ci.yml?branch=main&label=CI)](https://github.com/tgKishikaisei/search-translate-bot/actions/workflows/ci.yml)

## Команды

| Команда | Что делает |
|---|---|
| обычный текст | перевод и кнопки «Искать в Google» и «Искать в Яндексе» |
| `/translate текст` | перевод на выбранный язык |
| `/translate_multi текст` | перевод сразу на английский, испанский, французский, немецкий и итальянский |
| `/choose_language` | язык перевода: русский, английский, испанский, французский, немецкий, итальянский |
| `/history` | последние переводы |
| PDF-файл | текст из файла, до 4000 символов |
| `/start`, `/help`, `/about` | язык интерфейса (русский или английский), справка |

Язык интерфейса и язык перевода хранятся отдельно: перевод на испанский не переключит справку.

## Стек

Python 3.12, aiogram 3, deep-translator, pypdf.

## Запуск

```bash
git clone https://github.com/tgKishikaisei/search-translate-bot.git
cd search-translate-bot
python -m venv venv
venv\Scripts\activate               # Linux и macOS: source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                 # впишите TELEGRAM_BOT_TOKEN
python main.py
```

## Тесты

```bash
pip install pytest
python -m pytest -q
```

## Демо

Скриншотов нет: бот работает в Telegram, запустите его со своим токеном от @BotFather.

## Лицензия

[MIT](LICENSE) © 2026 Behruz Avezmatov

# Scanner Human Imitation Bot

Telegram-бот, который имитирует человека:
- Подключается к каналам/группам
- Сканирует сообщения
- Сохраняет лог срабатываний по триггерам
- Позволяет управлять триггерами через Telegram-команды
- Репостит найденные сообщения в подписанные чаты

## Установка

Установите зависимости:
```bash
pipenv install -r requirements.txt
```

Создайте .env с настройками:

```bash
TG_API_ID=
TG_API_HASH=
TG_SESSION=
#Database
DATABASE_URL=
#FastAPI
FASTAPI_URL=http://127.0.0.1:8000
#BOT TOKEN
BOT_TOKEN=
#POLL_INTERVAL — (сек) как часто опрашивать /feed (по умолчанию 60)
POLL_INTERVAL=60

BOT_AUTHOR_ID=
BOT_AUTHOR_NAME=

POSTGRES_USER=
POSTGRES_PASSWORD=
POSTGRES_DB=
```

Для запуска:

1. есть юзербот (Telethon), который под своим Telegram-аккаунтом подключается к API. Чтобы впервые получить токен/сессию, Telethon нужно авторизоваться:
```bash
pipenv run python authorize.py
```
2. Запустить FastAPI-сервер:
```bash
uvicorn app.main:app --reload
```
3. В отдельной консоли Запустить репостер-бота:
```bash
pipenv run python reposter_bot.py
```

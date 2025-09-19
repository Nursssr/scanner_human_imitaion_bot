import os
import asyncio
import json
import html as html_lib
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv
import httpx
from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.client.default import DefaultBotProperties


STATE_PATH_DEFAULT = "reposter_state.json"
load_dotenv()

#Загружает состояние бота из файла json
def load_state(path: str) -> Dict[str, Any]:
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"last_seen_id": 0, "chats": []}
    return {"last_seen_id": 0, "chats": []}

#Сохраняет сост. бота в json
def save_state(path: str, state: Dict[str, Any]):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

def esc(s: Optional[str]) -> str:
    if s is None:
        return ""
    return html_lib.escape(str(s))

#Формирует текстовое сообщение из канала+инфо
def format_log_message(log: Dict[str, Any], targets_map: Dict[int, Dict[str, Any]]) -> str:
    target_id = log.get("target_id")
    tgt = targets_map.get(target_id) if target_id is not None else None
    target_title = tgt.get("title") or tgt.get("username") if tgt else None
    target_username = tgt.get("username") if tgt else None

    author_name = log.get("author_name") or ""
    author_id = log.get("author_id") or ""
    matched_text = log.get("matched_text") or ""
    matched_trigger = log.get("matched_trigger_id") or ""
    text = log.get("text") or ""
    message_id = log.get("message_id")

    parts = []
    parts.append("🔔 <b>Новое сообщение в ленте</b>")
    parts.append(f"<b>Источник:</b> {esc(target_title or (target_username or str(target_id)))}")
    if target_username:
        parts.append(f"<b>Username:</b> {esc(target_username)}")
    parts.append(f"<b>Автор:</b> {esc(author_name) if author_name else esc(author_id)}")
    if matched_trigger:
        parts.append(f"<b>Совпадение триггера:</b> {esc(matched_trigger)}")
        parts.append(f"<b>Найденный текст:</b> {esc(matched_text)}")
    parts.append("")  # blank
    # body as preformatted (safe)
    parts.append("<pre>{}</pre>".format(esc(text)[:3900]))

    if target_username and message_id:
        uname = target_username.lstrip("@")
        parts.append(f'\n<a href="https://t.me/{uname}/{message_id}">Открыть сообщение</a>')

    return "\n".join(parts)

#Получает из фастапи все таргеты и превращает в id для быстрого доступа
async def fetch_targets_map(client: httpx.AsyncClient, api_base: str) -> Dict[int, Dict[str, Any]]:
    try:
        r = await client.get(f"{api_base.rstrip('/')}/targets")
        if r.status_code == 200:
            arr = r.json()
            m = {}
            for t in arr:
                if t.get("id") is not None:
                    m[int(t["id"])] = t
            return m
    except Exception:
        pass
    return {}


async def poller(bot: Bot, api_base: str, state_path: str, poll_interval: int, backfill: bool):
    state = load_state(state_path)
    last_seen = int(state.get("last_seen_id", 0))
    print("Reposter: starting poller, last_seen =", last_seen)

    async with httpx.AsyncClient(timeout=10.0) as client:
        if last_seen == 0 and not backfill:
            try:
                r = await client.get(f"{api_base.rstrip('/')}/feed?limit=1")
                if r.status_code == 200:
                    arr = r.json() or []
                    if len(arr) > 0:
                        last_seen = int(arr[0].get("id") or 0)
                        state["last_seen_id"] = last_seen
                        save_state(state_path, state)
                        print("Reposter: initialized last_seen to", last_seen)
            except Exception as e:
                print("Reposter: init fetch failed:", e)

    while True:
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                r = await client.get(f"{api_base.rstrip('/')}/feed?limit=50")
                if r.status_code == 200:
                    logs: List[Dict[str, Any]] = r.json() or []
                    if not isinstance(logs, list):
                        logs = []
                    new_logs = [
                        l for l in logs
                        if int(l.get("id", 0)) > last_seen
                        and l.get("matched_trigger_id")
                    ]

                    BOT_AUTHOR_ID = int(os.getenv("BOT_AUTHOR_ID", "7124862056"))
                    new_logs = [l for l in new_logs if l.get("author_id") != BOT_AUTHOR_ID]

                    if new_logs:
                        new_logs.sort(key=lambda x: int(x.get("id", 0)))
                        targets_map = await fetch_targets_map(client, api_base)
                        for log in new_logs:

                            msg = format_log_message(log, targets_map)

                            state = load_state(state_path)
                            chats: List[int] = state.get("chats", [])
                            for chat in chats:
                                try:
                                    await bot.send_message(chat, msg, disable_web_page_preview=True)
                                except Exception as e:
                                    print(f"Failed send to {chat}: {e}")
                            last_seen = max(last_seen, int(log.get("id", 0)))
                            state["last_seen_id"] = last_seen
                            save_state(state_path, state)
                else:
                    print("Reposter: feed request failed, status:", r.status_code)
        except Exception as e:
            print("Reposter poller error:", e)

        await asyncio.sleep(poll_interval)

FASTAPI_URL = os.getenv("FASTAPI_URL")

#Регистрирует обработчики команд бота
def register_handlers(dp: Dispatcher, state_path: str, api_url: str):
    @dp.message(Command(commands=["start"]))
    async def cmd_start(message: Message):
        text = (
            "Я — репостер ленты `/feed` FastAPI. Команды:\n"
            "\nДля показа ленты с названием группы/канала, автором и текстом сообщения:\n"
            "/subscribe — подписать этот чат на репосты\n"
            "/unsubscribe — отписать этот чат\n"
            "/status — показать статус\n"
            "\nДля поиска канала по названию:\n"
            "/search &lt;слова&gt; — поиск групп/каналов\n"
            "\nДля добавление/редактирование и удаление правил для триггеров на сообщения:\n"
            "/listtriggers — Для просмотра списка триггеров\n"
            "/addtrigger &lt;слова&gt — Для добавления триггера на сообщения\n"
            "/updatetrigger &lt;id&gt &lt;слова&gt — Для обновления триггера\n "
            "/deletetrigger &lt;id&gt — Для удаления триггера\n "
            "\nДля добавления и выхода из группы/канала: \n "
            "/join &lt;@username&gt; — добавить userbot в канал/группу\n"
            "/leave &lt;@username&gt; — выйти из канала/группы\n"
        )
        await message.answer(text)

    @dp.message(Command(commands=["subscribe"]))
    async def cmd_subscribe(message: Message):
        st = load_state(state_path)
        chats = st.get("chats", [])
        cid = message.chat.id
        if cid in chats:
            await message.reply("Этот чат уже подписан.")
            return
        chats.append(cid)
        st["chats"] = chats
        save_state(state_path, st)
        await message.reply("Готово — этот чат подписан на репосты.")

    @dp.message(Command(commands=["unsubscribe"]))
    async def cmd_unsubscribe(message: Message):
        st = load_state(state_path)
        chats = st.get("chats", [])
        cid = message.chat.id
        if cid not in chats:
            await message.reply("Этот чат не был подписан.")
            return
        chats = [c for c in chats if c != cid]
        st["chats"] = chats
        save_state(state_path, st)
        await message.reply("Готово — этот чат отписан.")

    @dp.message(Command(commands=["status"]))
    async def cmd_status(message: Message):
        st = load_state(state_path)
        last = st.get("last_seen_id", 0)
        chats = st.get("chats", [])
        await message.reply(f"last_seen_id = {last}\nsubscribed_chats = {chats}")

    @dp.message(Command(commands=["search"]))
    async def cmd_search(message: Message):
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            await message.reply("Использование: /search <ключевые слова>")
            return
        query = args[1]
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(f"{api_url.rstrip('/')}/search", params={"q": query})
            if r.status_code == 200:
                res = r.json().get("results", [])
                if not res:
                    await message.reply("Ничего не найдено.")
                else:
                    out_lines = []
                    for item in res[:10]:
                        out_lines.append(
                            f"{item['kind']} — {item.get('title') or item.get('username')} (username: {item.get('username')})"
                        )
                    await message.reply("\n".join(out_lines))
            else:
                await message.reply(f"Ошибка поиска: {r.status_code}")

    @dp.message(Command(commands=["join"]))
    async def cmd_join(message: Message):
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            await message.reply("Использование: /join <@username или ссылка>")
            return
        username = args[1]
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(f"{api_url.rstrip('/')}/join", json={"username": username})
            if r.status_code == 200:
                data = r.json()
                tgt = data.get("target", {})
                await message.reply(f"Готово: добавился в {tgt.get('title') or tgt.get('username')}")
            else:
                await message.reply(f"Ошибка join: {r.status_code} {r.text}")


    @dp.message(Command("listtriggers"))
    async def cmd_listtriggers(message: Message):
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(f"{api_url.rstrip('/')}/triggers")
            if r.status_code == 200:
                arr = r.json()
                if not arr:
                    await message.reply("Триггеров нет")
                else:
                    lines = []
                    for t in arr:
                        # показываем имя и человекочитаемый паттерн
                        lines.append(
                            f"#{t['id']} — {t.get('name') or ''}\n"
                            f"слово: <b>{t.get('raw_text')}</b>\n"
                            f"flags: {t.get('flags', 0)} enabled: {t.get('enabled', True)} target_id:{t.get('target_id')}"
                        )
                    await message.reply("\n\n".join(lines))
            else:
                await message.reply(f"Ошибка: {r.status_code} {r.text}")

    @dp.message(Command("addtrigger"))
    async def cmd_addtrigger(message: Message):
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            await message.reply("Использование: /addtrigger <регулярное выражение>")
            return
        user_pattern = args[1]
        payload = {
            "pattern": user_pattern,
            "raw_text": user_pattern,
            "name": f"Trigger {user_pattern}"
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(f"{api_url.rstrip('/')}/triggers", json=payload)
            if r.status_code == 200:
                t = r.json()
                # пользователю показываем исходный текст, а не скомпилированную регексп
                await message.reply(f"Добавлен триггер #{t['id']} по слову: <b>{user_pattern}</b>")
            else:
                await message.reply(f"Ошибка добавления: {r.status_code} {r.text}")

    @dp.message(Command("updatetrigger"))
    async def cmd_updatetrigger(message: Message):
        args = message.text.split(maxsplit=2)
        if len(args) < 3:
            await message.reply("Использование: /updatetrigger <id> <новый_паттерн>")
            return
        tid = args[1]
        user_pattern = args[2]
        payload = {
            "pattern": user_pattern,
            "raw_text": user_pattern,
            "name": f"Trigger {user_pattern}"
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.put(f"{api_url.rstrip('/')}/triggers/{tid}", json=payload)
            if r.status_code == 200:
                t = r.json()
                await message.reply(f"Триггер #{t['id']} обновлён. Новый шаблон: <b>{user_pattern}</b>")
            else:
                await message.reply(f"Ошибка при обновлении: {r.status_code} {r.text}")

    @dp.message(Command("deletetrigger"))
    async def cmd_deletetrigger(message: Message):
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            await message.reply("Использование: /deletetrigger <id>")
            return
        tid = args[1]
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.delete(f"{api_url.rstrip('/')}/triggers/{tid}")
            if r.status_code == 200:
                await message.reply(f"Триггер #{tid} удалён.")
            else:
                await message.reply(f"Ошибка удаления: {r.status_code} {r.text}")


    @dp.message(Command(commands=["leave"]))
    async def cmd_leave(message: Message):
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            await message.reply("Использование: /leave <@username или ссылка>")
            return
        username = args[1]
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(f"{api_url.rstrip('/')}/leave", json={"username": username})
            if r.status_code == 200:
                await message.reply("Готово: вышел.")
            else:
                await message.reply(f"Ошибка leave: {r.status_code} {r.text}")

async def main():
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN required in environment")

    api_url = os.getenv("FASTAPI_URL", "http://localhost:8000")
    POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "5"))
    STATE_PATH = os.getenv("REPOSTER_STATE_PATH", STATE_PATH_DEFAULT)
    BACKFILL = os.getenv("REPOSTER_BACKFILL", "false").lower() in ("1", "true", "yes")
    AUTO_CHAT = os.getenv("TARGET_CHAT_ID")

    state = load_state(STATE_PATH)
    if AUTO_CHAT:
        try:
            cid = int(AUTO_CHAT)
            if cid not in state.get("chats", []):
                state.setdefault("chats", []).append(cid)
                save_state(STATE_PATH, state)
                print("Auto-subscribed chat id from env:", cid)
        except Exception:
            pass

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode="HTML")
    )
    dp = Dispatcher()

    register_handlers(dp, STATE_PATH, api_url)

    poll_task = asyncio.create_task(poller(bot, api_url, STATE_PATH, POLL_INTERVAL, BACKFILL))
    print("Reposter: poller task started. Bot polling now...")

    try:
        await dp.start_polling(bot)
    finally:
        poll_task.cancel()
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Stopped by user")

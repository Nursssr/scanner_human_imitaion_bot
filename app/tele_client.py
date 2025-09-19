import os
import re
import asyncio
import json
from telethon import TelegramClient, events, functions
from telethon.tl.functions.channels import JoinChannelRequest, LeaveChannelRequest
from dotenv import load_dotenv
from .crud import get_triggers, upsert_target_by_tgid, create_log, get_target_by_tg_id

load_dotenv()

API_ID = int(os.getenv("TG_API_ID"))
API_HASH = os.getenv("TG_API_HASH")

BOT_AUTHOR_ID=int(os.getenv("BOT_AUTHOR_ID"))
BOT_AUTHOR_NAME = os.getenv("BOT_AUTHOR_NAME")


SESSION = os.getenv("TG_SESSION", "scanner_session")
client = TelegramClient(SESSION, API_ID, API_HASH)

_compiled_triggers = []
_lock = asyncio.Lock()
_my_id = None


async def refresh_triggers_cache():
    #Компилирует регулярки из БД
    global _compiled_triggers
    async with _lock:
        rows = await get_triggers(enabled_only=True)
        compiled = [] #регулярные выражения
        for r in rows:
            try:
                flags = (int(r.flags or 0) & ~re.LOCALE) | re.IGNORECASE #включить IGNORECASE и убрать LOCALE
                creg = re.compile(r.pattern, flags)
                #pattern - регул. выражение в таблице trigger(шаблон)
                #flags - числовое значение флагов рег.выраж.(применение шаблона)
                compiled.append({"id": r.id, "target_id": r.target_id, "regex": creg})
            except Exception as e:
                print("Failed compile regex", r.id, r.pattern, e)
        _compiled_triggers = compiled


async def _process_message(chat, event):
    #Проверяет сообщение на триггеры и пишет лог
    text = getattr(event, "raw_text", "") or getattr(getattr(event, "message", None), "message", "") or ""

    if not _compiled_triggers:
        await refresh_triggers_cache()

    tg_chat_id = getattr(chat, "id", None)
    chat_title = getattr(chat, "title", None) or getattr(chat, "name", None) or getattr(chat, "username", None)
    chat_username = getattr(chat, "username", None)
    chat_type = chat.__class__.__name__

    #сохраняем target
    db_target = None
    if tg_chat_id:
        db_target = await upsert_target_by_tgid(
            tg_chat_id, username=chat_username, title=chat_title, typ=chat_type
        )

    #получаем автора сразу
    author_name = None
    author_id = None
    try:
        author = await event.get_sender()
        if author:
            author_name = getattr(author, "username", None) or (
                (getattr(author, "first_name", "") or "") + " " + (getattr(author, "last_name", "") or "")
            )
            author_id = getattr(author, "id", None)
    except Exception:
        pass

    # пропускаем самого себя
    if author_id == BOT_AUTHOR_ID or author_name == BOT_AUTHOR_NAME:
        return
    if author_id == _my_id or (author_name and author_name == "Scanner_imitation_bot"):
        return

    #сериализация raw_json
    raw = None
    if hasattr(event, "to_dict"):
        try:
            raw = json.loads(json.dumps(event.to_dict(), default=str))
        except Exception:
            raw = None

    # проходим по триггерам и ищем ВСЕ совпадения
    for t in _compiled_triggers:
        # фильтрация по target_id
        if t["target_id"] is not None and tg_chat_id is not None:
            db_t = await get_target_by_tg_id(tg_chat_id)
            if db_t is None or db_t.id != t["target_id"]:
                continue

        #проверка текста на совпадения с триггерами
        for m in t["regex"].finditer(text or ""):
            matched_trigger_id = t["id"]
            matched_text = m.group(0)
            try:
                await create_log({
                    "target_id": db_target.id if db_target else None,
                    "message_id": getattr(getattr(event, "message", None), "id", None),
                    "author_id": author_id,
                    "author_name": author_name,
                    "text": text,
                    "matched_trigger_id": matched_trigger_id,
                    "matched_text": matched_text,
                    "raw_json": raw
                })
            except Exception as e:
                print("Failed to create log:", e)

    # параллельно выводим в консоль
    print(f"[{chat_title}] {author_name}: {text}")


@client.on(events.NewMessage(incoming=True))
async def _on_new_message(event):
    #Обработчик новых сообщений
    if event.out or getattr(event, 'sender_id', None) == _my_id:
        return
    chat = await event.get_chat()
    await _process_message(chat, event)


async def start_client():
    #Старт Telethon-клиента
    global _my_id
    await client.start()
    me = await client.get_me()
    _my_id = me.id
    print(f"Telethon client started as {_my_id}")
    await refresh_triggers_cache()


async def stop_client():
    #Отключение
    await client.disconnect()


async def search_public(query: str, limit: int = 20):
    #Поиск групп/каналов по названию
    try:
        res = await client(functions.contacts.SearchRequest(q=query, limit=limit))
        results = []
        for c in res.chats:
            results.append({
                "kind": c.__class__.__name__,
                "id": getattr(c, "id", None),
                "username": getattr(c, "username", None),
                "title": getattr(c, "title", None)
            })
        return results
    except Exception:
        # fallback: iterate local dialogs
        results = []
        async for dialog in client.iter_dialogs():
            ent = dialog.entity
            title = getattr(ent, "title", None) or getattr(ent, "username", None) or dialog.name
            if title and query.lower() in title.lower() and ent.__class__.__name__ != "User":
                results.append({
                    "kind": ent.__class__.__name__,
                    "id": getattr(ent, "id", None),
                    "username": getattr(ent, "username", None),
                    "title": title
                })
                if len(results) >= limit:
                    break
        return results


async def join_by_username(username_or_link: str):
    #Вступает в канал/группу по username
    try:
        ent = await client.get_entity(username_or_link)
        await client(JoinChannelRequest(ent))
        return {
            "ok": True,
            "msg": "joined",
            "id": getattr(ent, "id", None),
            "username": getattr(ent, "username", None),
            "title": getattr(ent, "title", None),
            "type": ent.__class__.__name__
        }
    except Exception as e:
        return {"ok": False, "msg": str(e)}


async def leave_by_username(username_or_link: str):
    #Выходит из канала/группы
    try:
        ent = await client.get_entity(username_or_link)
        await client(LeaveChannelRequest(ent))
        return {
            "ok": True,
            "msg": "left",
            "id": getattr(ent, "id", None),
            "username": getattr(ent, "username", None),
            "title": getattr(ent, "title", None),
            "type": ent.__class__.__name__
        }
    except Exception as e:
        return {"ok": False, "msg": str(e)}
from fastapi import FastAPI, HTTPException
from .db import init_models
from .tele_client import start_client, stop_client, search_public, join_by_username, leave_by_username, refresh_triggers_cache
from . import crud, schemas
from typing import List
import re


app = FastAPI(title="Telegram human-like scanner")

@app.on_event("startup")
async def startup_event():
    #При старте приложения:
    #1. Создаём таблицы в БД (если их нет)
    #2. Запускаем Telethon-клиент для чтения сообщении
    await init_models()
    await start_client()

@app.on_event("shutdown")
async def shutdown_event():
    #При завершении отключаем клиент-Telethon
    await stop_client()


#Добавляем новые триггеры
@app.post("/triggers", response_model=schemas.TriggerOut)
async def create_trigger(payload: schemas.TriggerCreate):
    p = payload.pattern.strip()
    #Автоматически формирует регулярку для обычного слова, если нет спецсимволов
    if not any(ch in p for ch in ".?*+|[](){}\\"):
        p = fr"\b{re.escape(p)}\w*\b"
    # если raw_text пустой – заполняем исходным текстом
    if not payload.raw_text:
        payload.raw_text = payload.pattern.strip()
    payload.pattern = p
    t = await crud.create_trigger(payload.dict())
    await refresh_triggers_cache()
    return schemas.TriggerOut(
        id=t.id, name=t.name,
        raw_text=t.raw_text,
        pattern=t.pattern, flags=t.flags,
        target_id=t.target_id, enabled=t.enabled
    )


#Возвращает все триггеры
@app.get("/triggers", response_model=List[schemas.TriggerOut])
async def list_triggers():
    rows = await crud.get_triggers(enabled_only=False)
    return [
        schemas.TriggerOut(
            id=r.id,
            name=r.name,
            raw_text=r.raw_text,
            pattern=r.pattern,
            flags=r.flags,
            target_id=r.target_id,
            enabled=r.enabled
        )
        for r in rows
    ]

#Обновление триггера по id
@app.put("/triggers/{tid}", response_model=schemas.TriggerOut)
async def update_trigger(tid: int, payload: schemas.TriggerCreate):
    p = payload.pattern.strip()
    if not any(ch in p for ch in ".?*+|[](){}\\"):
        p = fr"\b{re.escape(p)}\w*\b"
    payload.pattern = p
    if not payload.raw_text:
        payload.raw_text = payload.pattern
    t = await crud.update_trigger(tid, payload.dict())
    await refresh_triggers_cache()
    return schemas.TriggerOut(
        id=t.id, name=t.name,
        raw_text=t.raw_text,
        pattern=t.pattern, flags=t.flags,
        target_id=t.target_id, enabled=t.enabled
    )

#Удаление триггера по id
@app.delete("/triggers/{tid}")
async def delete_trigger(tid: int):
    await crud.delete_trigger(tid)
    await refresh_triggers_cache()
    return {"ok": True}

#Добавить чат/канал в базу
@app.post("/targets", response_model=schemas.TargetOut)
async def create_target(payload: schemas.TargetCreate):
    t = await crud.create_target(payload.dict())
    return schemas.TargetOut(id=t.id, tg_id=t.tg_id, username=t.username, title=t.title, type=t.type)

#Получить список всех подписанных чатов
@app.get("/targets", response_model=List[schemas.TargetOut])
async def list_targets():
    rows = await crud.list_targets()
    return [schemas.TargetOut(id=r.id, tg_id=r.tg_id, username=r.username, title=r.title, type=r.type) for r in rows]

#Получение ленты сообщений
@app.get("/feed", response_model=List[schemas.LogOut])
async def feed(limit: int = 50, offset: int = 0):
    rows = await crud.list_logs(limit=limit, offset=offset)
    out = []
    for r in rows:
        target_title = None
        target_username = None
        if r.target_id:
            t = await crud.get_target_by_id(r.target_id)
            if t:
                target_title = t.title
                target_username = t.username
        out.append(schemas.LogOut(
            id=r.id,
            target_id=r.target_id,
            target_title=target_title,
            target_username=target_username,
            message_id=r.message_id,
            author_id=r.author_id,
            author_name=r.author_name,
            text=r.text,
            matched_trigger_id=r.matched_trigger_id,
            matched_text=r.matched_text,
            created_at=r.created_at.isoformat() if r.created_at else None
        ))
    return out

#Поиск публичных каналов/групп по названию
@app.get("/search")
async def search(q: str):
    res = await search_public(q)
    return {"results": res}

#Присоединение к каналу/группе по username
@app.post("/join")
async def join(body: dict):
    username = body.get("username")
    if not username:
        raise HTTPException(400, "username required")
    r = await join_by_username(username)
    if not r.get("ok"):
        raise HTTPException(500, r.get("msg"))
    #обновляем/создаём таргет в БД
    await crud.upsert_target_by_tgid(r["id"], username=r["username"], title=r["title"], typ=r["type"])
    return {"ok": True, "joined": True, "target": r}

#Выход из канала/группы по username
@app.post("/leave")
async def leave(body: dict):
    username = body.get("username")
    if not username:
        raise HTTPException(400, "username required")
    r = await leave_by_username(username)
    if not r.get("ok"):
        raise HTTPException(500, r.get("msg"))
    return {"ok": True, "left": True, "tg_id": r.get("id")}

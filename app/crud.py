from sqlalchemy import text
from .models import Trigger, Target, Log  # только для типов возвращаемых объектов
from .db import AsyncSessionLocal
from typing import List, Optional

#Создать нового триггера в базе
async def create_trigger(data) -> Trigger:
    async with AsyncSessionLocal() as db:
        sql = text("""
            INSERT INTO triggers (pattern, target_id, enabled, flags)
            VALUES (:pattern, :target_id, :enabled, :flags)
            RETURNING *
        """)
        res = await db.execute(sql, data)
        row = res.first()
        await db.commit()
        return row

#Получить список триггеров
async def get_triggers(enabled_only: bool = True):
    async with AsyncSessionLocal() as db:
        if enabled_only:
            sql = text("SELECT * FROM triggers WHERE enabled = TRUE")
            res = await db.execute(sql)
        else:
            sql = text("SELECT * FROM triggers")
            res = await db.execute(sql)
        return res.fetchall()

#Получить триггер по id
async def get_trigger_by_id(tid: int):
    async with AsyncSessionLocal() as db:
        sql = text("SELECT * FROM triggers WHERE id = :tid")
        res = await db.execute(sql, {"tid": tid})
        return res.first()

#Обновить триггер по id
async def update_trigger(tid: int, patch: dict):
    async with AsyncSessionLocal() as db:
        set_parts = ", ".join([f"{k} = :{k}" for k in patch.keys()])
        patch["tid"] = tid
        sql = text(f"UPDATE triggers SET {set_parts} WHERE id = :tid RETURNING *")
        res = await db.execute(sql, patch)
        row = res.first()
        await db.commit()
        return row

#Удалить триггер по id
async def delete_trigger(tid: int):
    async with AsyncSessionLocal() as db:
        sql = text("DELETE FROM triggers WHERE id = :tid")
        await db.execute(sql, {"tid": tid})
        await db.commit()
        return True


#Создать обьект для таргета
async def create_target(data) -> Target:
    async with AsyncSessionLocal() as db:
        sql = text("""
            INSERT INTO targets (tg_id, username, title, type)
            VALUES (:tg_id, :username, :title, :type)
            RETURNING *
        """)
        res = await db.execute(sql, data)
        row = res.first()
        await db.commit()
        return row

#Список таргетов
async def list_targets() -> List[Target]:
    async with AsyncSessionLocal() as db:
        sql = text("SELECT * FROM targets")
        res = await db.execute(sql)
        return res.fetchall()

#Добавляет нового target(чат/канал) в базу или обновляет существующий по tg_id.
async def upsert_target_by_tgid(tgid: int, username: str = None, title: str = None, typ: str = None):
    async with AsyncSessionLocal() as db:
        # пробуем найти
        sel = text("SELECT * FROM targets WHERE tg_id = :tgid")
        res = await db.execute(sel, {"tgid": tgid})
        found = res.first()
        if found:
            sql = text("""
                UPDATE targets
                SET username = COALESCE(:username, username),
                    title = COALESCE(:title, title),
                    type = COALESCE(:typ, type)
                WHERE tg_id = :tgid
                RETURNING *
            """)
            res2 = await db.execute(sql, {
                "username": username,
                "title": title,
                "typ": typ,
                "tgid": tgid
            })
            row = res2.first()
            await db.commit()
            return row
        else:
            sql = text("""
                INSERT INTO targets (tg_id, username, title, type)
                VALUES (:tgid, :username, :title, :typ)
                RETURNING *
            """)
            res2 = await db.execute(sql, {
                "tgid": tgid,
                "username": username,
                "title": title,
                "typ": typ
            })
            row = res2.first()
            await db.commit()
            return row

#Получить target по внутреннему id
async def get_target_by_id(tid: int) -> Optional[Target]:
    async with AsyncSessionLocal() as db:
        sql = text("SELECT * FROM targets WHERE id = :tid")
        res = await db.execute(sql, {"tid": tid})
        return res.first()

#Получить Target по tg_id
async def get_target_by_tg_id(tgid: int) -> Optional[Target]:
    async with AsyncSessionLocal() as db:
        sql = text("SELECT * FROM targets WHERE tg_id = :tgid")
        res = await db.execute(sql, {"tgid": tgid})
        return res.first()

#Создать запись лога(сообщения, которое совпало с триггером)
async def create_log(data) -> Log:
    async with AsyncSessionLocal() as db:
        sql = text("""
            INSERT INTO logs (target_id, message_id, author_id, author_name, text, matched_trigger_id, matched_text, raw_json)
            VALUES (:target_id, :message_id, :author_id, :author_name, :text, :matched_trigger_id, :matched_text, :raw_json)
            RETURNING *
        """)
        res = await db.execute(sql, data)
        row = res.first()
        await db.commit()
        return row

#Получить список логов
async def list_logs(limit: int = 50, offset: int = 0):
    async with AsyncSessionLocal() as db:
        sql = text("""
            SELECT * FROM logs ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
        """)
        res = await db.execute(sql, {"limit": limit, "offset": offset})
        return res.fetchall()

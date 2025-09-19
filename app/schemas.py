from pydantic import BaseModel
from typing import Optional

#Схема создания триггера
class TriggerCreate(BaseModel):
    name: Optional[str]
    raw_text: Optional[str]
    pattern: str
    flags: Optional[int] = 0
    target_id: Optional[int] = None
    enabled: Optional[bool] = True

#Схема ответа триггера
class TriggerOut(BaseModel):
    id: int
    name: str
    raw_text: Optional[str] = None
    pattern: str
    flags: int
    target_id: Optional[str] = None
    enabled: bool

#Схема создания таргета
class TargetCreate(BaseModel):
    username: Optional[str] = None
    title: Optional[str] = None

#Схема ответа таргета
class TargetOut(BaseModel):
    id: int
    tg_id: Optional[int] = None
    username: Optional[str] = None
    title: Optional[str] = None
    type: Optional[str] = None

#Схема ответа лога
class LogOut(BaseModel):
    id: int
    target_id: Optional[int]
    target_title: Optional[str] = None
    target_username: Optional[str] = None
    message_id: Optional[int]
    author_id: Optional[int]
    author_name: Optional[str]
    text: Optional[str]
    matched_trigger_id: Optional[int]
    matched_text: Optional[str]
    created_at: Optional[str]

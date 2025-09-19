from sqlalchemy import Column, Integer, BigInteger, String, Boolean, Text, DateTime, ForeignKey, JSON, func
from .db import Base

#регулярка для поиска текста
class Trigger(Base):
    __tablename__ = "triggers"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=True)
    raw_text = Column(String)
    pattern = Column(String, nullable=False)
    flags = Column(Integer, default=0)
    target_id = Column(Integer, ForeignKey("targets.id", ondelete="CASCADE"), nullable=True)
    enabled = Column(Boolean, default=True)


#канал/чат
class Target(Base):
    __tablename__ = "targets"
    id = Column(Integer, primary_key=True, index=True)
    tg_id = Column(BigInteger, unique=True, nullable=True, index=True)
    username = Column(String, nullable=True)
    title = Column(String, nullable=True)
    type = Column(String, nullable=True)


#совпадение сообщения с триггером
class Log(Base):
    __tablename__ = "logs"
    id = Column(Integer, primary_key=True, index=True)
    target_id = Column(Integer, ForeignKey("targets.id", ondelete="CASCADE"), nullable=True)
    message_id = Column(BigInteger, nullable=True)
    author_id = Column(BigInteger, nullable=True)
    author_name = Column(String, nullable=True)
    text = Column(Text, nullable=True)
    matched_trigger_id = Column(ForeignKey('triggers.id', ondelete='CASCADE'))
    matched_text = Column(String, nullable=True)
    raw_json = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
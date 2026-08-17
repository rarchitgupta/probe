from __future__ import annotations

import os

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

DEFAULT_DATABASE_URL = "sqlite+aiosqlite:///.probe/probe.db"

load_dotenv()


class Base(DeclarativeBase):
    pass


database_url = os.getenv("PROBE_DATABASE_URL", DEFAULT_DATABASE_URL)
engine = create_async_engine(database_url)
async_session_factory = async_sessionmaker(
    engine,
    expire_on_commit=False,
)

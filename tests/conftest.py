from collections.abc import AsyncIterator
from pathlib import Path

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from qa_agent.database import Base
from qa_agent.runs import RunStore


@pytest_asyncio.fixture
async def run_store(tmp_path: Path) -> AsyncIterator[RunStore]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'probe.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    yield RunStore(async_sessionmaker(engine, expire_on_commit=False))
    await engine.dispose()

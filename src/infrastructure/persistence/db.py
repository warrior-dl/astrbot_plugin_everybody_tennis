import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .models import Base


def get_plugin_data_root() -> Path:
    astrbot_root = os.environ.get("ASTRBOT_ROOT")
    root = Path(astrbot_root).resolve() if astrbot_root else Path.cwd().resolve()
    return root / "data" / "plugin_data"


class DatabaseManager:
    def __init__(self, plugin_name: str):
        data_dir = get_plugin_data_root() / plugin_name
        self._data_dir: Path = data_dir
        self._db_path: Path = data_dir / "tennis.db"
        self._engine = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None

    async def initialize(self):
        self._data_dir.mkdir(parents=True, exist_ok=True)
        if self._engine is None:
            self._engine = create_async_engine(
                f"sqlite+aiosqlite:///{self._db_path}",
                future=True,
            )
            self._session_factory = async_sessionmaker(
                self._engine,
                expire_on_commit=False,
            )
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        if self._session_factory is None:
            raise RuntimeError("database is not initialized")
        session = self._session_factory()
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    async def close(self):
        if self._engine is not None:
            await self._engine.dispose()

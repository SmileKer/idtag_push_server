from pathlib import Path

import asyncpg


class Database:
    def __init__(self, url: str) -> None:
        self.url = url
        self.pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        self.pool = await asyncpg.create_pool(self.url, min_size=1, max_size=10)

    async def close(self) -> None:
        if self.pool:
            await self.pool.close()

    async def migrate(self) -> None:
        if not self.pool:
            raise RuntimeError("database is not connected")
        sql_path = Path(__file__).parent.parent / "sql" / "001_initial.sql"
        async with self.pool.acquire() as connection:
            await connection.execute(sql_path.read_text())

    def require_pool(self) -> asyncpg.Pool:
        if not self.pool:
            raise RuntimeError("database is not connected")
        return self.pool

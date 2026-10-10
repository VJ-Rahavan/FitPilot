"""Create or reset the schema from the models (no Alembic, by design for the hackathon).

Any model change: run `uv run python -m server.db.seed --reset` to rebuild and reseed.
"""

from sqlalchemy.ext.asyncio import AsyncEngine

from server.db.models import Base


async def create_schema(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def reset_schema(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

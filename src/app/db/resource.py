import logging
import typing

from sqlalchemy.ext import asyncio as sa

from app.settings import Settings

logger = logging.getLogger(__name__)


async def create_session(
    engine: sa.AsyncEngine,
) -> typing.AsyncIterator[sa.AsyncSession]:
    async with sa.AsyncSession(
        engine, expire_on_commit=False, autoflush=False
    ) as session:
        yield session

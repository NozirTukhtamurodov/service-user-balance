import contextlib
import typing

import fastapi


from sqlalchemy.ext.asyncio import (
    async_sessionmaker,
    create_async_engine,
    AsyncSession as AsyncSessionType,
    AsyncEngine,
)

from app.api import users, transactions
from app.settings import Settings
from app.api.base import get_db, get_settings
from app.utils import get_idempotency_storage


def include_routers(app: fastapi.FastAPI) -> None:
    app.include_router(users.ROUTER, prefix="/api")
    app.include_router(transactions.ROUTER, prefix="/api")


class AppBuilder:
    def __init__(self) -> None:
        self.settings = Settings()
        self._async_engine: typing.Optional[AsyncEngine] = None
        self._session_maker: typing.Optional[async_sessionmaker[AsyncSessionType]] = (
            None
        )

        self.app: fastapi.FastAPI = fastapi.FastAPI(
            title=self.settings.service_name,
            debug=self.settings.debug,
            lifespan=self.lifespan_manager,
        )

        self.app.dependency_overrides[get_db] = self._get_db
        self.app.dependency_overrides[get_settings] = self._get_settings
        include_routers(self.app)

    def _get_db(self) -> async_sessionmaker[AsyncSessionType]:
        if self._session_maker is None:
            raise RuntimeError("Database session maker not initialized")
        return self._session_maker

    def _get_settings(self) -> Settings:
        return self.settings

    async def init_async_resources(self) -> None:
        """Initialize async resources like database connections."""
        # Initialize database
        self._async_engine = create_async_engine(
            self.settings.db_dsn,
            echo=self.settings.debug,
            pool_pre_ping=True,
        )

        # Create session maker
        self._session_maker = async_sessionmaker(
            self._async_engine, class_=AsyncSessionType, expire_on_commit=False
        )

        # Redis will be initialized lazily when first accessed

    async def tear_down(self) -> None:
        # Close Redis connection
        try:
            idempotency_storage = get_idempotency_storage(
                redis_url=self.settings.redis_url
            )
            await idempotency_storage.close()
        except Exception as e:
            # Log error but don't fail teardown
            print(f"Error closing Redis connection: {e}")

        # Dispose database engine
        if self._async_engine is not None:
            await self._async_engine.dispose()

    @contextlib.asynccontextmanager
    async def lifespan_manager(
        self, _: fastapi.FastAPI
    ) -> typing.AsyncIterator[dict[str, typing.Any]]:
        try:
            await self.init_async_resources()
            yield {}
        finally:
            await self.tear_down()


application = AppBuilder().app

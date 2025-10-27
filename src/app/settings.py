import pydantic_settings
from granian.log import LogLevels
from sqlalchemy.engine.url import URL


class Settings(pydantic_settings.BaseSettings):
    service_name: str = "test-application"
    debug: bool = False
    log_level: LogLevels = LogLevels.info

    db_driver: str = "postgresql+asyncpg"
    db_host: str = "db"
    db_port: int = 5432
    db_user: str = "postgres"
    db_password: str = "password"
    db_database: str = "postgres"

    app_port: int = 8000

    # Redis settings
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str | None = None

    @property
    def redis_url(self) -> str:
        """Build Redis connection URL from components.

        Returns:
            str: Redis connection URL
        """
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def db_dsn(self) -> URL:
        """Build database connection URL from components.

        Returns:
            URL: SQLAlchemy database connection URL
        """
        return URL.create(
            self.db_driver,
            self.db_user,
            self.db_password,
            self.db_host,
            self.db_port,
            self.db_database,
        )

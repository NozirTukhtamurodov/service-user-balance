import granian
from granian.constants import Interfaces, Loops

from app.settings import Settings


if __name__ == "__main__":
    settings = Settings()
    granian.Granian(
        target="app.application:application",
        address="0.0.0.0",  # noqa: S104
        port=settings.app_port,
        interface=Interfaces.ASGI,
        log_dictconfig={"root": {"level": "INFO"}} if not settings.debug else {},
        log_level=settings.log_level,
        loop=Loops.uvloop,
    ).serve()

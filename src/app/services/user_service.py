import logging
from typing import Optional

from sqlalchemy.ext.asyncio import (
    async_sessionmaker,
    AsyncSession as AsyncSessionType,
)

from app import schemas
from app.models import User
from app.repositories.user import UserRepository

logger = logging.getLogger(__name__)


class UserService:
    def __init__(self, session_maker: async_sessionmaker[AsyncSessionType]):
        self.user_repo = UserRepository(session_maker=session_maker)

    async def create_user(self, data: schemas.UserCreate) -> User:
        """Create a new user with zero balance.

        Args:
            data: User creation data containing name

        Returns:
            User: Created user model instance
        """
        return await self.user_repo.create_user(data)

    async def get_user_by_id(self, user_id: str) -> Optional[User]:
        """Retrieve user by ID.

        Args:
            user_id: User UUID string

        Returns:
            Optional[User]: User instance if found, None otherwise
        """
        return await self.user_repo.get_user_by_id(user_id)

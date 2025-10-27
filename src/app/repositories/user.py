import logging
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import (
    async_sessionmaker,
    AsyncSession as AsyncSessionType,
)
import sqlalchemy as sa

from app import schemas
from app.exceptions import UserExistsError
from app.models import User

logger = logging.getLogger(__name__)


class UserRepository:
    def __init__(self, session_maker: async_sessionmaker[AsyncSessionType]):
        self.session_maker = session_maker

    async def create_user(self, data: schemas.UserCreate) -> User:
        """Create a new user with zero balance.

        Args:
            data: User creation data containing name

        Returns:
            User: Created user model instance with generated ID

        Raises:
            UserExistsError: If user creation fails due to constraints
        """
        try:
            async with self.session_maker() as session:
                async with session.begin():
                    user = User(name=data.name)
                    session.add(user)
                    await session.flush()
                    await session.refresh(user)
                    return user
        except IntegrityError as e:
            logger.error(f"Failed to create user: {e}")
            raise UserExistsError(f"User with name '{data.name}' might already exist")

    async def get_user_by_id(self, user_id: str) -> Optional[User]:
        """Retrieve user by ID.

        Args:
            user_id: User UUID string

        Returns:
            Optional[User]: User instance if found, None otherwise
        """
        async with self.session_maker() as session:
            result = await session.execute(sa.select(User).where(User.id == user_id))
            return result.scalar_one_or_none()

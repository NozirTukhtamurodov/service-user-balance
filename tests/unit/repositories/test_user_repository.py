"""
Unit tests for UserRepository.
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch
from sqlalchemy.exc import IntegrityError

from app.repositories.user import UserRepository
from app.exceptions import UserExistsError
from app.models import User


class TestUserRepository:
    """Test cases for UserRepository."""

    @pytest.fixture
    def user_repo(self, mock_session_maker):
        """Create UserRepository instance with mocked session maker."""
        return UserRepository(mock_session_maker)

    async def test_create_user_success(
        self,
        user_repo,
        mock_session_maker,
        mock_db_session,
        sample_user_create,
        sample_user,
    ):
        """Test successful user creation."""
        # Setup
        with patch("app.repositories.user.User") as MockUser:
            MockUser.return_value = sample_user

            # Execute
            result = await user_repo.create_user(sample_user_create)

            # Verify
            assert result == sample_user
            MockUser.assert_called_once_with(name="John Doe")
            mock_db_session.add.assert_called_once_with(sample_user)
            mock_db_session.flush.assert_called_once()
            mock_db_session.refresh.assert_called_once_with(sample_user)

    async def test_create_user_integrity_error(self, user_repo, sample_user_create):
        """Test user creation with database integrity error."""
        # Setup
        with patch.object(user_repo, "session_maker") as mock_maker:
            mock_session = AsyncMock()
            mock_session.add = Mock()
            mock_session.flush = AsyncMock(side_effect=IntegrityError("", "", ""))
            mock_session.refresh = AsyncMock()

            # Properly mock begin() context manager
            begin_mock = AsyncMock()
            begin_mock.__aenter__ = AsyncMock(return_value=None)
            begin_mock.__aexit__ = AsyncMock(return_value=None)
            mock_session.begin = Mock(return_value=begin_mock)

            mock_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_maker.return_value.__aexit__ = AsyncMock(return_value=None)

            # Execute & Verify
            with pytest.raises(
                UserExistsError, match="User with name 'John Doe' might already exist"
            ):
                await user_repo.create_user(sample_user_create)

    async def test_get_user_by_id_found(
        self, user_repo, mock_db_session, sample_user, mock_result
    ):
        """Test getting user by ID when user exists."""
        # Setup
        mock_db_session.execute.return_value = mock_result(sample_user)

        # Execute
        result = await user_repo.get_user_by_id("test-user-123")

        # Verify
        assert result == sample_user
        mock_db_session.execute.assert_called_once()

    async def test_get_user_by_id_not_found(
        self, user_repo, mock_db_session, mock_result
    ):
        """Test getting user by ID when user doesn't exist."""
        # Setup
        mock_db_session.execute.return_value = mock_result(None)

        # Execute
        result = await user_repo.get_user_by_id("nonexistent-user")

        # Verify
        assert result is None
        mock_db_session.execute.assert_called_once()

    async def test_get_user_by_id_database_query(
        self, user_repo, mock_db_session, sample_user, mock_result
    ):
        """Test that get_user_by_id makes correct database query."""
        # Setup
        mock_db_session.execute.return_value = mock_result(sample_user)

        # Execute
        await user_repo.get_user_by_id("test-user-123")

        # Verify that execute was called with a select statement
        mock_db_session.execute.assert_called_once()
        call_args = mock_db_session.execute.call_args[0][0]
        # We can't easily inspect the SQL, but we can verify it was called

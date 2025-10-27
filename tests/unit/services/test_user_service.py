"""
Unit tests for UserService.
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.user_service import UserService


class TestUserService:
    """Test cases for UserService."""

    @pytest.fixture
    def user_service(self, mock_session_maker):
        """Create UserService instance with mocked session maker."""
        with patch("app.services.user_service.UserRepository"):
            service = UserService(mock_session_maker)
            return service

    async def test_create_user_success(
        self, user_service, sample_user_create, sample_user
    ):
        """Test successful user creation."""
        # Setup
        user_service.user_repo.create_user = AsyncMock(return_value=sample_user)

        # Execute
        result = await user_service.create_user(sample_user_create)

        # Verify
        assert result == sample_user
        user_service.user_repo.create_user.assert_called_once_with(sample_user_create)

    async def test_get_user_by_id_found(self, user_service, sample_user):
        """Test getting user by ID when user exists."""
        # Setup
        user_service.user_repo.get_user_by_id = AsyncMock(return_value=sample_user)

        # Execute
        result = await user_service.get_user_by_id("test-user-123")

        # Verify
        assert result == sample_user
        user_service.user_repo.get_user_by_id.assert_called_once_with("test-user-123")

    async def test_get_user_by_id_not_found(self, user_service):
        """Test getting user by ID when user doesn't exist."""
        # Setup
        user_service.user_repo.get_user_by_id = AsyncMock(return_value=None)

        # Execute
        result = await user_service.get_user_by_id("nonexistent-user")

        # Verify
        assert result is None
        user_service.user_repo.get_user_by_id.assert_called_once_with(
            "nonexistent-user"
        )

    async def test_create_user_repository_error_propagation(
        self, user_service, sample_user_create
    ):
        """Test that repository errors are properly propagated."""
        # Setup
        from app.exceptions import UserExistsError

        user_service.user_repo.create_user = AsyncMock(
            side_effect=UserExistsError("User exists")
        )

        # Execute & Verify
        with pytest.raises(UserExistsError):
            await user_service.create_user(sample_user_create)

        user_service.user_repo.create_user.assert_called_once_with(sample_user_create)

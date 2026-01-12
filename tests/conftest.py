"""
Pytest configuration and fixtures
Provides TestClient for FastAPI app testing
"""
import pytest
from typing import Generator
from fastapi.testclient import TestClient

from main import app
from services.rbac_service import require_role
from api.auth import get_current_user


@pytest.fixture(scope="module")
def client() -> Generator[TestClient, None, None]:
    """Create TestClient for the FastAPI app"""
    # Note: Uses the app's default database (wsw.db)
    # Tests should be tolerant of database state
    # Override RBAC in tests to allow unauthenticated access
    def allow_all(_roles=None):
        def _dep():
            from models import User
            return User(
                id=0,
                email="test@local",
                username="tester",
                hashed_password="",
                role="analyst",  # Changed to analyst for selection tests
                is_active=True,
            )
        return _dep

    # Allow any role and bypass JWT in tests
    app.dependency_overrides[require_role] = allow_all
    def fake_current_user():
        from models import User
        return User(
            id=0,
            email="test@local",
            username="tester",
            hashed_password="",
            role="analyst",  # Changed to analyst for selection tests
            is_active=True,
        )
    app.dependency_overrides[get_current_user] = fake_current_user
    with TestClient(app) as test_client:
        # Seed ontology so universe tree tests have data
        try:
            from seed_ontology import seed_ontology
            seed_ontology()
        except Exception:
            # If seeding fails, continue; some tests tolerate empty state
            pass
        yield test_client


@pytest.fixture(autouse=True)
def cleanup_market_state():
    """Clean up market_data_service state after each test to ensure test isolation."""
    yield
    try:
        from services import market_data_service
        from config import settings
        market_data_service.cache_service.memory_cache.clear()
        market_data_service._rate_events = []
        market_data_service.set_provider_override(None)
        # Restore default settings
        settings.MARKET_PROVIDER_ENABLED = True
        settings.MARKET_RATE_LIMIT_PER_MINUTE = 60
        settings.MARKET_PROVIDER = "mock"
    except Exception:
        pass

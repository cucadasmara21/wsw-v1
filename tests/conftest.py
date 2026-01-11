"""
Pytest configuration and fixtures
Provides TestClient for FastAPI app testing
"""
import pytest
from typing import Generator
from fastapi.testclient import TestClient

from main import app


@pytest.fixture(scope="module")
def client() -> Generator[TestClient, None, None]:
    """Create TestClient for the FastAPI app"""
    # Note: Uses the app's default database (wsw.db)
    # Tests should be tolerant of database state
    with TestClient(app) as test_client:
        yield test_client

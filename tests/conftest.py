import os

os.environ["DEMO_BEARER_TOKEN"] = "test-token"

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.db.client import store


@pytest.fixture(autouse=True)
def reset_store():
    store.users.clear()
    store.posts.clear()
    store._user_seq = 0
    store._post_seq = 0
    store._users_by_email.clear()
    store._posts_by_key.clear()
    yield


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-token"}

import os
import pytest
from fastapi.testclient import TestClient

os.environ["DEMO_BEARER_TOKEN"] = "test-token"

from backend.main import app
from backend.db.client import store


@pytest.fixture(autouse=True)
def reset_store():
    store.users.clear()
    store.posts.clear()
    store._user_seq = 0
    store._post_seq = 0
    yield


client = TestClient(app)
headers = {"Authorization": "Bearer test-token"}


def test_list_users_empty():
    r = client.get("/users")
    assert r.status_code == 200
    assert r.json() == []


def test_create_user_requires_auth():
    r = client.post("/users", json={"name": "Ana", "email": "ana@example.com"})
    assert r.status_code == 401


def test_create_user_ok():
    r = client.post("/users", json={"name": "Ana", "email": "ana@example.com"}, headers=headers)
    assert r.status_code == 201
    body = r.json()
    assert body["id"] == 1
    assert body["name"] == "Ana"


def test_get_user_by_id():
    client.post("/users", json={"name": "Ana", "email": "ana@example.com"}, headers=headers)
    r = client.get("/users/1")
    assert r.status_code == 200
    assert r.json()["name"] == "Ana"


def test_get_user_not_found():
    r = client.get("/users/999")
    assert r.status_code == 404

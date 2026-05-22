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


def test_create_post_requires_existing_author():
    r = client.post("/posts", json={"title": "Hola", "body": "Mundo", "author_id": 1}, headers=headers)
    assert r.status_code == 404


def test_create_post_ok():
    client.post("/users", json={"name": "Ana", "email": "ana@example.com"}, headers=headers)
    r = client.post("/posts", json={"title": "Hola", "body": "Mundo", "author_id": 1}, headers=headers)
    assert r.status_code == 201
    assert r.json()["id"] == 1


def test_list_posts():
    client.post("/users", json={"name": "Ana", "email": "ana@example.com"}, headers=headers)
    client.post("/posts", json={"title": "Hola", "body": "Mundo", "author_id": 1}, headers=headers)
    r = client.get("/posts")
    assert r.status_code == 200
    assert len(r.json()) == 1

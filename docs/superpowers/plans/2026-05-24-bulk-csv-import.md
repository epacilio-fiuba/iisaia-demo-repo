# Bulk CSV Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an admin (current bearer token holder) bulk-import users or posts from a CSV file via `POST /import/{resource}`, with explicit handling of invalid rows, duplicates, and atomic rollback, surfaced through a small admin page in the frontend.

**Architecture:** New `routers/imports.py` is HTTP-only (multipart parsing, size/row limits, status code mapping). A FastAPI-agnostic `services/csv_import.py` runs the import using per-resource adapters (`UserAdapter`, `PostAdapter`) that know how to validate, dedup, and insert. The in-memory store gains two indexes (by email; by `(title, author_id, body)`) plus `snapshot()` / `restore()` so atomic mode can undo a partial run.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, pytest + FastAPI TestClient, vanilla HTML/JS for the frontend, `uv` for running scripts.

**Reference spec:** `docs/superpowers/specs/2026-05-24-bulk-csv-import-design.md`

---

## Task 1: Move `reset_store` fixture to `conftest.py`

This is a pure refactor with no behavior change. Doing it first means later tasks can extend the fixture in one place when we add the store indexes.

**Files:**
- Create: `tests/conftest.py`
- Modify: `tests/test_users.py` (delete lines 1-21 fixture/setup block)
- Modify: `tests/test_posts.py` (delete lines 1-21 fixture/setup block)

- [ ] **Step 1: Run the existing test suite to capture baseline**

Run: `cd C:/Users/Enzo/demo-repo && uv run pytest -v`
Expected: all existing tests pass (test_users.py and test_posts.py).

- [ ] **Step 2: Create `tests/conftest.py`**

```python
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
    yield


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-token"}
```

The env var is set at module import time so it is in place before `backend.main` is imported. `client` and `auth_headers` are exposed as fixtures so test modules don't need module-level setup.

- [ ] **Step 3: Replace `tests/test_users.py`**

```python
def test_list_users_empty(client):
    r = client.get("/users")
    assert r.status_code == 200
    assert r.json() == []


def test_create_user_requires_auth(client):
    r = client.post("/users", json={"name": "Ana", "email": "ana@example.com"})
    assert r.status_code == 401


def test_create_user_ok(client, auth_headers):
    r = client.post(
        "/users",
        json={"name": "Ana", "email": "ana@example.com"},
        headers=auth_headers,
    )
    assert r.status_code == 201
    body = r.json()
    assert body["id"] == 1
    assert body["name"] == "Ana"


def test_get_user_by_id(client, auth_headers):
    client.post(
        "/users",
        json={"name": "Ana", "email": "ana@example.com"},
        headers=auth_headers,
    )
    r = client.get("/users/1")
    assert r.status_code == 200
    assert r.json()["name"] == "Ana"


def test_get_user_not_found(client):
    r = client.get("/users/999")
    assert r.status_code == 404
```

- [ ] **Step 4: Replace `tests/test_posts.py`**

```python
def test_create_post_requires_existing_author(client, auth_headers):
    r = client.post(
        "/posts",
        json={"title": "Hola", "body": "Mundo", "author_id": 1},
        headers=auth_headers,
    )
    assert r.status_code == 404


def test_create_post_ok(client, auth_headers):
    client.post(
        "/users",
        json={"name": "Ana", "email": "ana@example.com"},
        headers=auth_headers,
    )
    r = client.post(
        "/posts",
        json={"title": "Hola", "body": "Mundo", "author_id": 1},
        headers=auth_headers,
    )
    assert r.status_code == 201
    assert r.json()["id"] == 1


def test_list_posts(client, auth_headers):
    client.post(
        "/users",
        json={"name": "Ana", "email": "ana@example.com"},
        headers=auth_headers,
    )
    client.post(
        "/posts",
        json={"title": "Hola", "body": "Mundo", "author_id": 1},
        headers=auth_headers,
    )
    r = client.get("/posts")
    assert r.status_code == 200
    assert len(r.json()) == 1
```

- [ ] **Step 5: Re-run the suite**

Run: `cd C:/Users/Enzo/demo-repo && uv run pytest -v`
Expected: all tests pass with the same count as the baseline.

- [ ] **Step 6: Commit**

```bash
git add tests/conftest.py tests/test_users.py tests/test_posts.py
git commit -m "refactor(tests): move reset_store fixture and test client to conftest"
```

---

## Task 2: Add store indexes and `find_*` methods

Add `_users_by_email` and `_posts_by_key` to the store, populate them from `create_user` / `create_post`, expose `find_user_by_email` and `find_post_by_content`. Update `reset_store` to clear the new fields.

**Files:**
- Modify: `backend/db/client.py`
- Modify: `tests/conftest.py` (extend `reset_store`)
- Create: `tests/test_store.py`

- [ ] **Step 1: Write failing tests for indexes**

Create `tests/test_store.py`:

```python
from backend.db.client import store
from backend.schemas.models import UserCreate, PostCreate


def test_find_user_by_email_returns_id():
    user = store.create_user(UserCreate(name="Ana", email="ana@x.com"))
    assert store.find_user_by_email("ana@x.com") == user.id


def test_find_user_by_email_missing():
    assert store.find_user_by_email("nobody@x.com") is None


def test_find_post_by_content_returns_id():
    author = store.create_user(UserCreate(name="Ana", email="ana@x.com"))
    post = store.create_post(
        PostCreate(title="Hola", body="Mundo", author_id=author.id)
    )
    assert store.find_post_by_content("Hola", author.id, "Mundo") == post.id


def test_find_post_by_content_missing():
    assert store.find_post_by_content("nope", 1, "nope") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:/Users/Enzo/demo-repo && uv run pytest tests/test_store.py -v`
Expected: 4 errors / `AttributeError: 'InMemoryStore' object has no attribute 'find_user_by_email'`.

- [ ] **Step 3: Extend the store with indexes and `find_*`**

Replace `backend/db/client.py`:

```python
from datetime import datetime, timezone
from typing import Optional
from backend.schemas.models import User, UserCreate, Post, PostCreate


class InMemoryStore:
    def __init__(self):
        self.users: dict[int, User] = {}
        self.posts: dict[int, Post] = {}
        self._user_seq = 0
        self._post_seq = 0
        self._users_by_email: dict[str, int] = {}
        self._posts_by_key: dict[tuple[str, int, str], int] = {}

    def create_user(self, data: UserCreate) -> User:
        self._user_seq += 1
        user = User(
            id=self._user_seq,
            created_at=datetime.now(timezone.utc),
            **data.model_dump(),
        )
        self.users[user.id] = user
        self._users_by_email[user.email] = user.id
        return user

    def get_user(self, user_id: int) -> Optional[User]:
        return self.users.get(user_id)

    def list_users(self) -> list[User]:
        return list(self.users.values())

    def find_user_by_email(self, email: str) -> Optional[int]:
        return self._users_by_email.get(email)

    def create_post(self, data: PostCreate) -> Optional[Post]:
        if data.author_id not in self.users:
            return None
        self._post_seq += 1
        post = Post(
            id=self._post_seq,
            created_at=datetime.now(timezone.utc),
            **data.model_dump(),
        )
        self.posts[post.id] = post
        self._posts_by_key[(post.title, post.author_id, post.body)] = post.id
        return post

    def get_post(self, post_id: int) -> Optional[Post]:
        return self.posts.get(post_id)

    def list_posts(self) -> list[Post]:
        return list(self.posts.values())

    def find_post_by_content(
        self, title: str, author_id: int, body: str
    ) -> Optional[int]:
        return self._posts_by_key.get((title, author_id, body))


store = InMemoryStore()
```

- [ ] **Step 4: Update `reset_store` to clear new fields**

In `tests/conftest.py`, replace the `reset_store` fixture body:

```python
@pytest.fixture(autouse=True)
def reset_store():
    store.users.clear()
    store.posts.clear()
    store._user_seq = 0
    store._post_seq = 0
    store._users_by_email.clear()
    store._posts_by_key.clear()
    yield
```

- [ ] **Step 5: Run the full suite**

Run: `cd C:/Users/Enzo/demo-repo && uv run pytest -v`
Expected: all tests pass including the 4 new ones in `test_store.py`.

- [ ] **Step 6: Commit**

```bash
git add backend/db/client.py tests/test_store.py tests/conftest.py
git commit -m "feat(store): add email and content indexes with find_* lookups"
```

---

## Task 3: Add `snapshot()` and `restore()` to the store

Snapshot returns shallow copies of the six pieces of state; restore reassigns them all.

**Files:**
- Modify: `backend/db/client.py`
- Modify: `tests/test_store.py`

- [ ] **Step 1: Write failing snapshot/restore test**

Append to `tests/test_store.py`:

```python
def test_snapshot_isolates_subsequent_mutations():
    store.create_user(UserCreate(name="Ana", email="ana@x.com"))
    snap = store.snapshot()

    store.create_user(UserCreate(name="Bob", email="bob@x.com"))
    assert len(store.users) == 2

    store.restore(snap)
    assert len(store.users) == 1
    assert store._user_seq == 1
    assert store._users_by_email == {"ana@x.com": 1}
    assert store._posts_by_key == {}


def test_snapshot_restores_posts_and_sequences():
    user = store.create_user(UserCreate(name="Ana", email="ana@x.com"))
    store.create_post(PostCreate(title="t", body="b", author_id=user.id))
    snap = store.snapshot()

    store.create_post(PostCreate(title="t2", body="b2", author_id=user.id))
    store.restore(snap)

    assert len(store.posts) == 1
    assert store._post_seq == 1
    assert store.find_post_by_content("t", user.id, "b") == 1
    assert store.find_post_by_content("t2", user.id, "b2") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:/Users/Enzo/demo-repo && uv run pytest tests/test_store.py -v`
Expected: 2 errors / `AttributeError: 'InMemoryStore' object has no attribute 'snapshot'`.

- [ ] **Step 3: Implement `snapshot()` and `restore()`**

Append to `InMemoryStore` in `backend/db/client.py` (before the final `store = InMemoryStore()`):

```python
    def snapshot(self) -> dict:
        return {
            "users": dict(self.users),
            "posts": dict(self.posts),
            "user_seq": self._user_seq,
            "post_seq": self._post_seq,
            "users_by_email": dict(self._users_by_email),
            "posts_by_key": dict(self._posts_by_key),
        }

    def restore(self, snap: dict) -> None:
        self.users = snap["users"]
        self.posts = snap["posts"]
        self._user_seq = snap["user_seq"]
        self._post_seq = snap["post_seq"]
        self._users_by_email = snap["users_by_email"]
        self._posts_by_key = snap["posts_by_key"]
```

- [ ] **Step 4: Run the full suite**

Run: `cd C:/Users/Enzo/demo-repo && uv run pytest -v`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/db/client.py tests/test_store.py
git commit -m "feat(store): add snapshot and restore for in-memory rollback"
```

---

## Task 4: Add import-result schemas

Three new Pydantic models for the service and router to share.

**Files:**
- Modify: `backend/schemas/models.py`

- [ ] **Step 1: Add the schemas**

In `backend/schemas/models.py`, add `Literal` to the top-of-file imports so the file starts with:

```python
from typing import Literal
from pydantic import BaseModel
from datetime import datetime
```

Then append the three new classes at the bottom of the file:

```python
class ImportRowError(BaseModel):
    row: int
    reason: Literal[
        "missing_field",
        "invalid_field",
        "duplicate_in_csv",
        "duplicate_in_store",
        "author_not_found",
    ]
    detail: str


class ImportInserted(BaseModel):
    row: int
    id: int


class ImportResult(BaseModel):
    resource: Literal["users", "posts"]
    mode: Literal["atomic", "partial"]
    total_rows: int
    inserted: list[ImportInserted]
    skipped: list[ImportRowError]
    rolled_back: bool
```

- [ ] **Step 2: Smoke-test instantiation**

Run: `cd C:/Users/Enzo/demo-repo && uv run python -c "from backend.schemas.models import ImportResult, ImportInserted, ImportRowError; r = ImportResult(resource='users', mode='atomic', total_rows=0, inserted=[], skipped=[], rolled_back=False); print(r.model_dump())"`

Expected: prints a dict matching the constructor arguments, no exception.

- [ ] **Step 3: Commit**

```bash
git add backend/schemas/models.py
git commit -m "feat(schemas): add ImportResult, ImportInserted, ImportRowError"
```

---

## Task 5: Build the per-resource adapters (validation only)

Adapters encapsulate "how do I validate one row of this resource, what is its dedup key, how do I insert it." Orchestrator comes in Task 6.

**Files:**
- Create: `backend/services/__init__.py` (empty)
- Create: `backend/services/csv_import.py`
- Create: `tests/test_csv_import_service.py`

- [ ] **Step 1: Create the empty `services` package**

Create `backend/services/__init__.py` with no content (empty file).

- [ ] **Step 2: Write failing adapter tests**

Create `tests/test_csv_import_service.py`:

```python
from backend.db.client import store
from backend.schemas.models import UserCreate, PostCreate, ImportRowError
from backend.services.csv_import import UserAdapter, PostAdapter


def test_user_adapter_required_columns():
    assert UserAdapter.required_columns == ("name", "email")


def test_user_adapter_validates_ok():
    result = UserAdapter.validate_row(2, {"name": "Ana", "email": "ana@x.com"})
    assert isinstance(result, UserCreate)
    assert result.name == "Ana"
    assert result.email == "ana@x.com"


def test_user_adapter_missing_field():
    result = UserAdapter.validate_row(3, {"name": "", "email": "ana@x.com"})
    assert isinstance(result, ImportRowError)
    assert result.row == 3
    assert result.reason == "missing_field"
    assert "name" in result.detail


def test_user_adapter_invalid_field_extra_whitespace_only():
    result = UserAdapter.validate_row(4, {"name": "   ", "email": "ana@x.com"})
    assert isinstance(result, ImportRowError)
    assert result.reason == "missing_field"


def test_user_adapter_dup_key_uses_email():
    user = UserCreate(name="Ana", email="ana@x.com")
    assert UserAdapter.dup_key(user) == "ana@x.com"


def test_post_adapter_required_columns():
    assert PostAdapter.required_columns == ("title", "body", "author_id")


def test_post_adapter_validates_ok():
    result = PostAdapter.validate_row(
        2, {"title": "t", "body": "b", "author_id": "5"}
    )
    assert isinstance(result, PostCreate)
    assert result.author_id == 5


def test_post_adapter_invalid_author_id():
    result = PostAdapter.validate_row(
        2, {"title": "t", "body": "b", "author_id": "abc"}
    )
    assert isinstance(result, ImportRowError)
    assert result.reason == "invalid_field"
    assert "author_id" in result.detail


def test_post_adapter_missing_body():
    result = PostAdapter.validate_row(
        2, {"title": "t", "body": "", "author_id": "1"}
    )
    assert isinstance(result, ImportRowError)
    assert result.reason == "missing_field"


def test_post_adapter_dup_key_is_tuple():
    post = PostCreate(title="t", body="b", author_id=1)
    assert PostAdapter.dup_key(post) == ("t", 1, "b")
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd C:/Users/Enzo/demo-repo && uv run pytest tests/test_csv_import_service.py -v`
Expected: `ModuleNotFoundError: No module named 'backend.services.csv_import'`.

- [ ] **Step 4: Implement the adapters**

Create `backend/services/csv_import.py`:

```python
from typing import Union
from pydantic import ValidationError

from backend.db.client import InMemoryStore
from backend.schemas.models import (
    UserCreate,
    PostCreate,
    User,
    Post,
    ImportRowError,
)


def _missing_field_error(row: int, columns: tuple[str, ...], data: dict[str, str]) -> ImportRowError | None:
    for col in columns:
        if not data.get(col, "").strip():
            return ImportRowError(
                row=row, reason="missing_field", detail=f"{col} is required"
            )
    return None


def _validation_error_detail(err: ValidationError) -> str:
    first = err.errors()[0]
    loc = ".".join(str(p) for p in first["loc"])
    return f"{loc}: {first['msg']}"


class UserAdapter:
    required_columns: tuple[str, ...] = ("name", "email")

    @staticmethod
    def validate_row(row: int, data: dict[str, str]) -> Union[UserCreate, ImportRowError]:
        miss = _missing_field_error(row, UserAdapter.required_columns, data)
        if miss:
            return miss
        try:
            return UserCreate(name=data["name"].strip(), email=data["email"].strip())
        except ValidationError as e:
            return ImportRowError(
                row=row, reason="invalid_field", detail=_validation_error_detail(e)
            )

    @staticmethod
    def dup_key(model: UserCreate) -> str:
        return model.email

    @staticmethod
    def find_in_store(store: InMemoryStore, model: UserCreate) -> int | None:
        return store.find_user_by_email(model.email)

    @staticmethod
    def insert(store: InMemoryStore, model: UserCreate) -> User:
        return store.create_user(model)


class PostAdapter:
    required_columns: tuple[str, ...] = ("title", "body", "author_id")

    @staticmethod
    def validate_row(row: int, data: dict[str, str]) -> Union[PostCreate, ImportRowError]:
        miss = _missing_field_error(row, PostAdapter.required_columns, data)
        if miss:
            return miss
        try:
            author_id = int(data["author_id"])
        except ValueError:
            return ImportRowError(
                row=row,
                reason="invalid_field",
                detail=f"author_id: '{data['author_id']}' is not an integer",
            )
        try:
            return PostCreate(
                title=data["title"].strip(),
                body=data["body"].strip(),
                author_id=author_id,
            )
        except ValidationError as e:
            return ImportRowError(
                row=row, reason="invalid_field", detail=_validation_error_detail(e)
            )

    @staticmethod
    def dup_key(model: PostCreate) -> tuple[str, int, str]:
        return (model.title, model.author_id, model.body)

    @staticmethod
    def find_in_store(store: InMemoryStore, model: PostCreate) -> int | None:
        return store.find_post_by_content(model.title, model.author_id, model.body)

    @staticmethod
    def insert(store: InMemoryStore, model: PostCreate) -> Post:
        created = store.create_post(model)
        assert created is not None, "author_not_found should have been caught earlier"
        return created
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd C:/Users/Enzo/demo-repo && uv run pytest tests/test_csv_import_service.py -v`
Expected: all 10 adapter tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/services/__init__.py backend/services/csv_import.py tests/test_csv_import_service.py
git commit -m "feat(import): add UserAdapter and PostAdapter for row validation"
```

---

## Task 6: Build the `run_import` orchestrator

The orchestrator takes parsed CSV rows, runs the two-pass walk (validate → dedup → insert), snapshots the store up-front, and restores it on rollback in atomic mode.

**Files:**
- Modify: `backend/services/csv_import.py`
- Modify: `tests/test_csv_import_service.py`

- [ ] **Step 1: Write failing orchestrator tests**

Append to `tests/test_csv_import_service.py`:

```python
from backend.services.csv_import import run_import
from backend.schemas.models import ImportResult


def _rows(*tuples):
    """Helper to build user rows: _rows(('Ana','a@x.com'), ('Bob','b@x.com'))."""
    return [{"name": n, "email": e} for n, e in tuples]


def test_run_import_users_partial_all_valid():
    result = run_import(
        "users",
        _rows(("Ana", "a@x.com"), ("Bob", "b@x.com")),
        mode="partial",
        store=store,
    )
    assert isinstance(result, ImportResult)
    assert result.total_rows == 2
    assert len(result.inserted) == 2
    assert result.skipped == []
    assert result.rolled_back is False
    assert len(store.users) == 2


def test_run_import_users_partial_mixed():
    rows = [
        {"name": "Ana", "email": "a@x.com"},
        {"name": "Bad", "email": ""},
        {"name": "Bob", "email": "b@x.com"},
    ]
    result = run_import("users", rows, mode="partial", store=store)
    assert len(result.inserted) == 2
    assert [s.row for s in result.skipped] == [3]
    assert result.skipped[0].reason == "missing_field"
    assert result.rolled_back is False
    assert len(store.users) == 2


def test_run_import_users_partial_duplicate_in_csv():
    rows = [
        {"name": "Ana", "email": "a@x.com"},
        {"name": "Ana2", "email": "a@x.com"},
    ]
    result = run_import("users", rows, mode="partial", store=store)
    assert len(result.inserted) == 1
    assert result.skipped[0].reason == "duplicate_in_csv"
    assert result.skipped[0].row == 3
    assert len(store.users) == 1


def test_run_import_users_partial_duplicate_in_store():
    store.create_user(UserCreate(name="Ana", email="a@x.com"))
    result = run_import(
        "users",
        _rows(("Ana", "a@x.com")),
        mode="partial",
        store=store,
    )
    assert result.inserted == []
    assert result.skipped[0].reason == "duplicate_in_store"
    assert len(store.users) == 1


def test_run_import_atomic_rolls_back_on_any_error():
    rows = [
        {"name": "Ana", "email": "a@x.com"},
        {"name": "Bad", "email": ""},
        {"name": "Bob", "email": "b@x.com"},
    ]
    result = run_import("users", rows, mode="atomic", store=store)
    assert result.inserted == []
    assert len(result.skipped) == 1
    assert result.rolled_back is True
    assert store.users == {}
    assert store._user_seq == 0


def test_run_import_atomic_reports_all_errors_not_just_first():
    rows = [
        {"name": "ok", "email": "ok@x.com"},
        {"name": "", "email": "a@x.com"},
        {"name": "b", "email": ""},
        {"name": "c", "email": ""},
    ]
    result = run_import("users", rows, mode="atomic", store=store)
    assert result.rolled_back is True
    assert [s.row for s in result.skipped] == [3, 4, 5]


def test_run_import_atomic_preserves_preexisting_data():
    pre = store.create_user(UserCreate(name="Pre", email="pre@x.com"))
    result = run_import(
        "users",
        [{"name": "x", "email": ""}],
        mode="atomic",
        store=store,
    )
    assert result.rolled_back is True
    assert store.users == {pre.id: pre}
    assert store._user_seq == 1


def test_run_import_posts_author_not_found_partial():
    rows = [{"title": "t", "body": "b", "author_id": "999"}]
    result = run_import("posts", rows, mode="partial", store=store)
    assert result.inserted == []
    assert result.skipped[0].reason == "author_not_found"
    assert "999" in result.skipped[0].detail


def test_run_import_posts_happy_path():
    author = store.create_user(UserCreate(name="Ana", email="a@x.com"))
    rows = [
        {"title": "t1", "body": "b1", "author_id": str(author.id)},
        {"title": "t2", "body": "b2", "author_id": str(author.id)},
    ]
    result = run_import("posts", rows, mode="atomic", store=store)
    assert len(result.inserted) == 2
    assert result.rolled_back is False
    assert len(store.posts) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:/Users/Enzo/demo-repo && uv run pytest tests/test_csv_import_service.py -v`
Expected: `ImportError: cannot import name 'run_import'`.

- [ ] **Step 3: Implement the orchestrator**

Append to `backend/services/csv_import.py`:

```python
from typing import Literal

from backend.schemas.models import ImportInserted, ImportResult


_ADAPTERS = {"users": UserAdapter, "posts": PostAdapter}


def run_import(
    resource: Literal["users", "posts"],
    rows: list[dict[str, str]],
    mode: Literal["atomic", "partial"],
    store: InMemoryStore,
) -> ImportResult:
    adapter = _ADAPTERS[resource]
    snap = store.snapshot()

    inserted: list[ImportInserted] = []
    skipped: list[ImportRowError] = []
    seen_keys: set = set()

    for idx, raw in enumerate(rows):
        row_n = idx + 2  # header is line 1, first data row is line 2

        parsed = adapter.validate_row(row_n, raw)
        if isinstance(parsed, ImportRowError):
            skipped.append(parsed)
            continue

        if resource == "posts" and parsed.author_id not in store.users:
            skipped.append(
                ImportRowError(
                    row=row_n,
                    reason="author_not_found",
                    detail=f"author_id {parsed.author_id} does not exist",
                )
            )
            continue

        key = adapter.dup_key(parsed)
        if key in seen_keys:
            skipped.append(
                ImportRowError(
                    row=row_n,
                    reason="duplicate_in_csv",
                    detail=f"duplicate of an earlier row in this file",
                )
            )
            continue
        seen_keys.add(key)

        existing_id = adapter.find_in_store(store, parsed)
        if existing_id is not None:
            skipped.append(
                ImportRowError(
                    row=row_n,
                    reason="duplicate_in_store",
                    detail=f"{key} already exists",
                )
            )
            continue

        created = adapter.insert(store, parsed)
        inserted.append(ImportInserted(row=row_n, id=created.id))

    rolled_back = False
    if mode == "atomic" and skipped:
        store.restore(snap)
        inserted = []
        rolled_back = True

    return ImportResult(
        resource=resource,
        mode=mode,
        total_rows=len(rows),
        inserted=inserted,
        skipped=skipped,
        rolled_back=rolled_back,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:/Users/Enzo/demo-repo && uv run pytest tests/test_csv_import_service.py -v`
Expected: all orchestrator + adapter tests pass.

- [ ] **Step 5: Run the full suite**

Run: `cd C:/Users/Enzo/demo-repo && uv run pytest -v`
Expected: every test passes.

- [ ] **Step 6: Commit**

```bash
git add backend/services/csv_import.py tests/test_csv_import_service.py
git commit -m "feat(import): add run_import orchestrator with atomic rollback"
```

---

## Task 7: Build the `/import/{resource}` router and wire it in

Router handles multipart parsing, the file/row size limits, header validation, and status code mapping (200 vs 422 vs 4xx). It delegates the row walk to `run_import`.

**Files:**
- Create: `backend/routers/imports.py`
- Modify: `backend/main.py`
- Create: `tests/test_imports.py`

- [ ] **Step 1: Write failing HTTP tests — auth and request shape**

Create `tests/test_imports.py`:

```python
import io


def _csv(content: str) -> dict:
    return {"file": ("test.csv", io.BytesIO(content.encode("utf-8")), "text/csv")}


def test_import_requires_auth(client):
    r = client.post(
        "/import/users",
        files=_csv("name,email\nAna,a@x.com\n"),
        data={"mode": "atomic"},
    )
    assert r.status_code == 401


def test_import_invalid_resource(client, auth_headers):
    r = client.post(
        "/import/widgets",
        files=_csv("a,b\n1,2\n"),
        data={"mode": "atomic"},
        headers=auth_headers,
    )
    assert r.status_code == 404


def test_import_missing_column(client, auth_headers):
    r = client.post(
        "/import/users",
        files=_csv("name\nAna\n"),
        data={"mode": "atomic"},
        headers=auth_headers,
    )
    assert r.status_code == 400
    assert "email" in r.json()["detail"]


def test_import_empty_csv(client, auth_headers):
    r = client.post(
        "/import/users",
        files=_csv("name,email\n"),
        data={"mode": "atomic"},
        headers=auth_headers,
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "empty csv"


def test_import_missing_file(client, auth_headers):
    r = client.post(
        "/import/users",
        data={"mode": "atomic"},
        headers=auth_headers,
    )
    assert r.status_code == 422  # FastAPI validation: file field required


def test_import_unknown_mode(client, auth_headers):
    r = client.post(
        "/import/users",
        files=_csv("name,email\nAna,a@x.com\n"),
        data={"mode": "weird"},
        headers=auth_headers,
    )
    assert r.status_code == 400


def test_import_too_many_rows(client, auth_headers):
    body = "name,email\n" + "\n".join(
        f"User{i},user{i}@x.com" for i in range(1001)
    ) + "\n"
    r = client.post(
        "/import/users",
        files=_csv(body),
        data={"mode": "partial"},
        headers=auth_headers,
    )
    assert r.status_code == 413


def test_import_file_too_large(client, auth_headers):
    big = "name,email\n" + ("padding,padding@x.com\n" * 60000)  # > 1 MB
    r = client.post(
        "/import/users",
        files=_csv(big),
        data={"mode": "partial"},
        headers=auth_headers,
    )
    assert r.status_code == 413
```

- [ ] **Step 2: Add happy-path and rollback HTTP tests**

Append to `tests/test_imports.py`:

```python
def test_import_users_atomic_ok(client, auth_headers):
    csv = "name,email\nAna,a@x.com\nBob,b@x.com\nCar,c@x.com\n"
    r = client.post(
        "/import/users",
        files=_csv(csv),
        data={"mode": "atomic"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total_rows"] == 3
    assert len(body["inserted"]) == 3
    assert body["skipped"] == []
    assert body["rolled_back"] is False
    assert len(client.get("/users").json()) == 3


def test_import_posts_atomic_ok(client, auth_headers):
    client.post(
        "/users",
        json={"name": "Ana", "email": "a@x.com"},
        headers=auth_headers,
    )
    csv = "title,body,author_id\nt1,b1,1\nt2,b2,1\n"
    r = client.post(
        "/import/posts",
        files=_csv(csv),
        data={"mode": "atomic"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert len(r.json()["inserted"]) == 2


def test_import_users_partial_with_invalid(client, auth_headers):
    csv = "name,email\nAna,a@x.com\nBad,\nBob,b@x.com\n"
    r = client.post(
        "/import/users",
        files=_csv(csv),
        data={"mode": "partial"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["inserted"]) == 2
    assert body["skipped"][0]["reason"] == "missing_field"
    assert body["rolled_back"] is False
    assert len(client.get("/users").json()) == 2


def test_import_users_atomic_rolls_back_returns_422(client, auth_headers):
    csv = "name,email\nAna,a@x.com\nBad,\nBob,b@x.com\n"
    r = client.post(
        "/import/users",
        files=_csv(csv),
        data={"mode": "atomic"},
        headers=auth_headers,
    )
    assert r.status_code == 422
    body = r.json()
    assert body["inserted"] == []
    assert body["rolled_back"] is True
    assert len(body["skipped"]) == 1
    assert client.get("/users").json() == []


def test_import_atomic_preserves_preexisting(client, auth_headers):
    client.post(
        "/users",
        json={"name": "Pre", "email": "pre@x.com"},
        headers=auth_headers,
    )
    csv = "name,email\nAna,a@x.com\nBad,\n"
    r = client.post(
        "/import/users",
        files=_csv(csv),
        data={"mode": "atomic"},
        headers=auth_headers,
    )
    assert r.status_code == 422
    users = client.get("/users").json()
    assert len(users) == 1
    assert users[0]["email"] == "pre@x.com"
    assert users[0]["id"] == 1
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd C:/Users/Enzo/demo-repo && uv run pytest tests/test_imports.py -v`
Expected: 404 errors on all routes (`/import/users` does not exist yet).

- [ ] **Step 4: Implement the router**

Create `backend/routers/imports.py`:

```python
import csv as csv_lib
import io
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from backend.db.client import store
from backend.middleware.auth import require_bearer
from backend.schemas.models import ImportResult
from backend.services.csv_import import run_import, UserAdapter, PostAdapter

router = APIRouter(prefix="/import", tags=["import"])

MAX_FILE_BYTES = 1_048_576  # 1 MB
MAX_ROWS = 1000

_ADAPTERS = {"users": UserAdapter, "posts": PostAdapter}


@router.post(
    "/{resource}",
    response_model=ImportResult,
    dependencies=[Depends(require_bearer)],
)
async def import_csv(
    resource: Literal["users", "posts"],
    file: UploadFile = File(...),
    mode: str = Form("atomic"),
) -> ImportResult:
    if mode not in ("atomic", "partial"):
        raise HTTPException(status_code=400, detail="mode must be atomic or partial")

    raw = await file.read()
    if len(raw) > MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="file exceeds 1 MB limit")

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="csv must be utf-8")

    reader = csv_lib.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise HTTPException(status_code=400, detail="empty csv")

    required = _ADAPTERS[resource].required_columns
    missing = [c for c in required if c not in reader.fieldnames]
    if missing:
        raise HTTPException(
            status_code=400, detail=f"missing column {missing[0]}"
        )

    rows = list(reader)
    if len(rows) == 0:
        raise HTTPException(status_code=400, detail="empty csv")
    if len(rows) > MAX_ROWS:
        raise HTTPException(
            status_code=413, detail=f"file exceeds {MAX_ROWS} row limit"
        )

    result = run_import(resource, rows, mode, store)

    if result.rolled_back:
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=result.model_dump(),
        )
    return result
```

- [ ] **Step 5: Wire the router into `backend/main.py`**

Replace `backend/main.py`:

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.routers import users, posts, imports

app = FastAPI(title="demo-repo API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(users.router)
app.include_router(posts.router)
app.include_router(imports.router)


@app.get("/")
def root():
    return {"name": "demo-repo", "version": "0.1.0"}
```

- [ ] **Step 6: Run the import tests**

Run: `cd C:/Users/Enzo/demo-repo && uv run pytest tests/test_imports.py -v`
Expected: all import HTTP tests pass.

- [ ] **Step 7: Run the full suite**

Run: `cd C:/Users/Enzo/demo-repo && uv run pytest -v`
Expected: every test passes.

- [ ] **Step 8: Commit**

```bash
git add backend/routers/imports.py backend/main.py tests/test_imports.py
git commit -m "feat(api): add POST /import/{resource} with size and rollback handling"
```

---

## Task 8: Create the `admin.html` page

Static markup only. JS comes in Task 9.

**Files:**
- Create: `frontend/admin.html`

- [ ] **Step 1: Create `frontend/admin.html`**

```html
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <title>demo-repo · Admin</title>
  <link rel="stylesheet" href="styles.css">
</head>
<body>
  <main>
    <h1>Admin · Import CSV</h1>
    <p><a href="index.html">Volver al inicio</a></p>

    <section>
      <form id="import-form">
        <label>
          Bearer token
          <input id="token" type="password" placeholder="Pegá el token" autocomplete="off">
        </label>

        <fieldset>
          <legend>Recurso</legend>
          <label><input type="radio" name="resource" value="users" checked> Users</label>
          <label><input type="radio" name="resource" value="posts"> Posts</label>
        </fieldset>

        <label>
          Archivo CSV
          <input id="file" type="file" accept=".csv" required>
        </label>

        <fieldset>
          <legend>Modo</legend>
          <label><input type="radio" name="mode" value="atomic" checked> Atomic · si una fila falla, no se inserta nada</label>
          <label><input type="radio" name="mode" value="partial"> Partial · inserta las válidas y reporta el resto</label>
        </fieldset>

        <button type="submit" id="submit-btn">Importar</button>
      </form>
    </section>

    <section id="result" hidden>
      <h2>Resultado</h2>
      <div id="banner" hidden></div>
      <p id="summary"></p>

      <h3>Insertadas</h3>
      <table class="import-table">
        <thead><tr><th>Row</th><th>ID</th></tr></thead>
        <tbody id="inserted-body"></tbody>
      </table>

      <h3>Descartadas</h3>
      <table class="import-table">
        <thead><tr><th>Row</th><th>Motivo</th><th>Detalle</th></tr></thead>
        <tbody id="skipped-body"></tbody>
      </table>
    </section>
  </main>
  <script src="admin.js"></script>
</body>
</html>
```

- [ ] **Step 2: Smoke-check the page renders**

Open `frontend/admin.html` in a browser. The form should display with token, resource radios, file input, mode radios, and a disabled-looking "Importar" button. The result section should be hidden.

- [ ] **Step 3: Commit**

```bash
git add frontend/admin.html
git commit -m "feat(frontend): add admin import page markup"
```

---

## Task 9: Implement `admin.js`

Reads form state, applies client-side checks, calls `POST /import/{resource}`, renders the result.

**Files:**
- Create: `frontend/admin.js`

- [ ] **Step 1: Create `frontend/admin.js`**

```javascript
const API = "http://localhost:8000";
const MAX_BYTES = 1_048_576;

const $ = (id) => document.getElementById(id);
const form = $("import-form");
const tokenInput = $("token");
const fileInput = $("file");
const submitBtn = $("submit-btn");
const resultSection = $("result");
const banner = $("banner");
const summary = $("summary");
const insertedBody = $("inserted-body");
const skippedBody = $("skipped-body");

// Restore token from sessionStorage.
const stored = sessionStorage.getItem("demo-bearer");
if (stored) tokenInput.value = stored;
tokenInput.addEventListener("change", () => {
  sessionStorage.setItem("demo-bearer", tokenInput.value);
});

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  showError(null);

  const token = tokenInput.value.trim();
  const resource = form.querySelector('input[name="resource"]:checked').value;
  const mode = form.querySelector('input[name="mode"]:checked').value;
  const file = fileInput.files[0];

  if (!token) return showError("Falta el bearer token.");
  if (!file) return showError("Elegí un archivo CSV.");
  if (!file.name.toLowerCase().endsWith(".csv")) return showError("El archivo debe terminar en .csv.");
  if (file.size > MAX_BYTES) return showError("El archivo supera 1 MB.");

  const data = new FormData();
  data.append("file", file);
  data.append("mode", mode);

  setLoading(true);
  try {
    const res = await fetch(`${API}/import/${resource}`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body: data,
    });
    const body = await res.json().catch(() => ({}));

    if (res.status === 200 || res.status === 422) {
      renderResult(body, res.status === 422);
    } else {
      showError(body.detail || `Error ${res.status}`);
    }
  } catch (err) {
    showError("No se pudo contactar al servidor.");
  } finally {
    setLoading(false);
  }
});

function setLoading(loading) {
  submitBtn.disabled = loading;
  submitBtn.textContent = loading ? "Importando…" : "Importar";
}

function showError(msg) {
  if (!msg) {
    banner.hidden = true;
    return;
  }
  resultSection.hidden = false;
  banner.hidden = false;
  banner.className = "banner-error";
  banner.textContent = msg;
  insertedBody.innerHTML = "";
  skippedBody.innerHTML = "";
  summary.textContent = "";
}

function renderResult(body, rolledBack) {
  resultSection.hidden = false;

  if (rolledBack) {
    banner.hidden = false;
    banner.className = "banner-error";
    banner.textContent = "Rollback · ningún ítem se insertó.";
  } else {
    banner.hidden = true;
  }

  summary.textContent =
    `Total: ${body.total_rows} · Insertadas: ${body.inserted.length} · ` +
    `Descartadas: ${body.skipped.length} · Modo: ${body.mode}`;

  insertedBody.innerHTML = body.inserted
    .map((r) => `<tr><td>${r.row}</td><td>${r.id}</td></tr>`)
    .join("");

  skippedBody.innerHTML = body.skipped
    .map(
      (r) =>
        `<tr><td>${r.row}</td><td>${escape(r.reason)}</td><td>${escape(r.detail)}</td></tr>`
    )
    .join("");
}

function escape(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}
```

- [ ] **Step 2: Manual e2e check — happy path**

In one terminal:
```bash
cd C:/Users/Enzo/demo-repo
DEMO_BEARER_TOKEN=test-token uv run uvicorn backend.main:app --reload
```

On Windows PowerShell:
```powershell
$env:DEMO_BEARER_TOKEN = "test-token"
uv run uvicorn backend.main:app --reload
```

Open `frontend/admin.html` in a browser. Paste `test-token`, select Users, mode Atomic, upload a CSV containing:

```csv
name,email
Ana,a@x.com
Bob,b@x.com
```

Expected: green panel with "Total: 2 · Insertadas: 2 · Descartadas: 0 · Modo: atomic", inserted table with two rows. `curl http://localhost:8000/users` shows both users.

- [ ] **Step 3: Manual e2e check — atomic rollback**

Upload a CSV with:

```csv
name,email
Ana,a@x.com
,bad@x.com
Bob,b@x.com
```

Expected: red banner "Rollback · ningún ítem se insertó.", summary shows `Insertadas: 0`, skipped table lists row 3 with reason `missing_field`. `curl http://localhost:8000/users` returns `[]`.

- [ ] **Step 4: Manual e2e check — partial mode**

Same CSV, switch mode to Partial.

Expected: no red banner, summary shows `Insertadas: 2 · Descartadas: 1 · Modo: partial`, inserted lists Ana and Bob, skipped lists row 3. `curl http://localhost:8000/users` returns both users.

- [ ] **Step 5: Commit**

```bash
git add frontend/admin.js
git commit -m "feat(frontend): wire admin.js to call import endpoint and render result"
```

---

## Task 10: Add styles and link from `index.html`

**Files:**
- Modify: `frontend/styles.css`
- Modify: `frontend/index.html`

- [ ] **Step 1: Append styles**

Append to `frontend/styles.css`:

```css
fieldset { padding: .5rem 1rem; border: 1px solid #ddd; border-radius: 4px; }
fieldset label { display: block; padding: .25rem 0; }

.import-table { width: 100%; border-collapse: collapse; margin-bottom: 1rem; }
.import-table th, .import-table td { padding: .5rem; border-bottom: 1px solid #eee; text-align: left; }
.import-table th { background: #f6f6f6; }

.banner-error { padding: .75rem 1rem; margin-bottom: 1rem; background: #fde8e8; color: #7a1f1f; border-radius: 4px; }
.banner-warn  { padding: .75rem 1rem; margin-bottom: 1rem; background: #fff4d6; color: #6a5200; border-radius: 4px; }

footer { margin-top: 2rem; padding-top: 1rem; border-top: 1px solid #eee; color: #666; font-size: .9rem; }
```

- [ ] **Step 2: Add the footer link in `index.html`**

In `frontend/index.html`, replace the closing `</main>` line with:

```html
    <footer>
      <a href="admin.html">Admin</a>
    </footer>
  </main>
```

- [ ] **Step 3: Manual check**

Open `frontend/index.html` in a browser, confirm an "Admin" link is in the footer, click it, confirm it takes you to `admin.html`.

- [ ] **Step 4: Commit**

```bash
git add frontend/styles.css frontend/index.html
git commit -m "feat(frontend): style admin tables and link from index"
```

---

## Task 11: Regenerate `openapi.yaml`

Required by `.claude/rules/api.md` whenever endpoints change.

**Files:**
- Modify: `openapi.yaml`

- [ ] **Step 1: Regenerate**

Run: `cd C:/Users/Enzo/demo-repo && uv run python scripts/export_openapi.py`
Expected output: `openapi.yaml updated`.

- [ ] **Step 2: Confirm the new endpoint is in the schema**

Run: `cd C:/Users/Enzo/demo-repo && uv run python -c "import yaml; s = yaml.safe_load(open('openapi.yaml')); print(list(s['paths'].keys()))"`
Expected: list includes `/import/{resource}`.

- [ ] **Step 3: Run the full test suite one more time**

Run: `cd C:/Users/Enzo/demo-repo && uv run pytest -v`
Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add openapi.yaml
git commit -m "chore: regenerate openapi.yaml for import endpoint"
```

---

## Done criteria

- `uv run pytest` passes with the new tests included.
- Manual e2e from Task 9 passes for happy, atomic-rollback, and partial cases.
- `openapi.yaml` reflects `/import/{resource}`.
- Branch `feature/import-data` has clean history of small commits matching each task.

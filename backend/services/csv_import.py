from typing import Literal, Union

from pydantic import ValidationError

from backend.db.client import InMemoryStore
from backend.schemas.models import (
    UserCreate,
    PostCreate,
    User,
    Post,
    ImportInserted,
    ImportResult,
    ImportRowError,
)


def _missing_field_error(
    row: int, columns: tuple[str, ...], data: dict[str, str]
) -> ImportRowError | None:
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

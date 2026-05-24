from typing import Literal

from pydantic import BaseModel
from datetime import datetime


class UserCreate(BaseModel):
    name: str
    email: str


class User(UserCreate):
    id: int
    created_at: datetime


class PostCreate(BaseModel):
    title: str
    body: str
    author_id: int


class Post(PostCreate):
    id: int
    created_at: datetime


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

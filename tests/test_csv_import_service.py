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

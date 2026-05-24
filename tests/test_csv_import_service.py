from backend.db.client import store
from backend.schemas.models import UserCreate, PostCreate, ImportRowError, ImportResult
from backend.services.csv_import import UserAdapter, PostAdapter, run_import


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

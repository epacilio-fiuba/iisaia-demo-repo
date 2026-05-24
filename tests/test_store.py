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

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

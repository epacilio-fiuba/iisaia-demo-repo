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

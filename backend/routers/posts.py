from fastapi import APIRouter, Depends, HTTPException, status
from backend.db.client import store
from backend.middleware.auth import require_bearer
from backend.schemas.models import Post, PostCreate

router = APIRouter(prefix="/posts", tags=["posts"])


@router.get("", response_model=list[Post])
def list_posts():
    return store.list_posts()


@router.post("", response_model=Post, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_bearer)])
def create_post(payload: PostCreate):
    post = store.create_post(payload)
    if post is None:
        raise HTTPException(status_code=404, detail="author not found")
    return post


@router.get("/{post_id}", response_model=Post)
def get_post(post_id: int):
    post = store.get_post(post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="post not found")
    return post

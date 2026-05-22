from fastapi import APIRouter, Depends, HTTPException, status
from backend.db.client import store
from backend.middleware.auth import require_bearer
from backend.schemas.models import User, UserCreate

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[User])
def list_users():
    return store.list_users()


@router.post("", response_model=User, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_bearer)])
def create_user(payload: UserCreate):
    return store.create_user(payload)


@router.get("/{user_id}", response_model=User)
def get_user(user_id: int):
    user = store.get_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    return user

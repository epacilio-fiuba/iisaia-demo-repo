from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.routers import users, posts

app = FastAPI(title="demo-repo API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(users.router)
app.include_router(posts.router)


@app.get("/")
def root():
    return {"name": "demo-repo", "version": "0.1.0"}

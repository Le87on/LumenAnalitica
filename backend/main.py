from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.core.config import settings
from backend.models.schemas import LoginRequest, LoginResponse
from backend.repositories.db import init_db
from backend.services.auth_service import authenticate_user, ensure_bootstrap_user

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup_event() -> None:
    init_db()
    ensure_bootstrap_user()


@app.get("/health")
def health() -> dict:
    return {"ok": True, "app": settings.app_name, "env": settings.app_env}


@app.post("/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest) -> LoginResponse:
    user, error = authenticate_user(payload.username, payload.password)
    if not user:
        return LoginResponse(ok=False, error=error or "Error de autenticación")
    return LoginResponse(ok=True, username=user["username"], rol=user["rol"])

"""Authentication routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response

from colearn.api.dependencies import auth_service, AUTH_COOKIE_NAME
from colearn.api.schemas import AuthLoginPayload, AuthRegisterPayload

router = APIRouter()


def _auth_status_payload(user: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "enabled": True,
        "authenticated": bool(user),
        "user_id": str((user or {}).get("user_id") or ""),
        "username": str((user or {}).get("username") or ""),
        "role": str((user or {}).get("role") or ""),
        "is_admin": bool((user or {}).get("is_admin")),
    }


def _current_user(request: Request) -> dict[str, Any] | None:
    return auth_service.user_for_session(request.cookies.get(AUTH_COOKIE_NAME))


@router.get("/api/v1/auth/status")
def auth_status(request: Request) -> dict[str, Any]:
    return _auth_status_payload(_current_user(request))


@router.post("/api/v1/auth/login")
def auth_login(payload: AuthLoginPayload, response: Response) -> dict[str, Any]:
    user = auth_service.authenticate(payload.username, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = auth_service.create_session(str(user.get("username") or ""))
    response.set_cookie(AUTH_COOKIE_NAME, token, httponly=True, samesite="lax", path="/")
    return {"ok": True, "user": _auth_status_payload(user)}


@router.post("/api/v1/auth/register")
def auth_register(payload: AuthRegisterPayload, response: Response) -> dict[str, Any]:
    try:
        user = auth_service.register(payload.username, payload.password)
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    token = auth_service.create_session(str(user.get("username") or ""))
    response.set_cookie(AUTH_COOKIE_NAME, token, httponly=True, samesite="lax", path="/")
    return {
        "ok": True,
        "role": user["role"],
        "is_first_user": bool(user.get("is_first_user")),
    }


@router.get("/api/v1/auth/is_first_user")
def auth_is_first_user() -> dict[str, Any]:
    return {"is_first_user": auth_service.is_first_user()}


@router.post("/api/v1/auth/logout")
def auth_logout(request: Request, response: Response) -> dict[str, Any]:
    token = request.cookies.get(AUTH_COOKIE_NAME)
    if token:
        auth_service.delete_session(token)
    response.delete_cookie(AUTH_COOKIE_NAME, path="/")
    return {"ok": True}

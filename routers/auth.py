from fastapi import APIRouter, HTTPException, Depends, Request, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from typing import Optional

from database.database import get_db
from services.auth_service import AuthService

router = APIRouter(prefix="/api/auth", tags=["Authentication"])
security = HTTPBearer()
auth_service = AuthService()


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    role: str
    is_active: bool


class AuthResponse(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse
    message: Optional[str] = None


# ==================== МОБИЛЬНЫЕ ЭНДПОИНТЫ (без префикса) ====================

@router.post("/login", response_model=AuthResponse)
async def mobile_login(
    login_data: LoginRequest,
    db: Session = Depends(get_db)
):
    """Вход для мобильного приложения (возвращает Bearer token)"""
    try:
        result = auth_service.login(
            email=login_data.email,
            password=login_data.password,
            db=db
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.get("/me", response_model=UserResponse)
async def mobile_get_current_user(
    token: str,
    db: Session = Depends(get_db)
):
    """Получение профиля для мобильного приложения (через token параметр)"""
    try:
        user = auth_service.get_user_by_token(token, db)
        return user
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


# Альтернативный вариант для мобилки через Bearer token
@router.get("/profile")
async def mobile_get_profile(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    """Получение профиля для мобильного приложения (через Bearer token)"""
    try:
        token = credentials.credentials
        user = auth_service.get_user_by_token(token, db)
        return user
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


# ==================== ВЕБ-ЭНДПОИНТЫ (с префиксом /web) ====================

@router.post("/web/login")
async def web_login(
    login_data: LoginRequest,
    response: Response,
    db: Session = Depends(get_db)
):
    """Вход для веб-приложения (устанавливает HttpOnly cookie)"""
    try:
        result = auth_service.login(
            email=login_data.email,
            password=login_data.password,
            db=db
        )

        response.set_cookie(
            key="access_token",
            value=result["access_token"],
            httponly=True,
            secure=False,
            samesite="lax",
            max_age=24 * 60 * 60,
            path="/"
        )

        return {
            "user": result["user"],
            "message": "Вход выполнен успешно"
        }
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.get("/web/me")
async def web_get_current_user(
    request: Request,
    db: Session = Depends(get_db)
):
    """Получение профиля для веб-приложения (из cookie)"""
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Токен не найден")

    try:
        user = auth_service.get_user_by_token(token, db)
        return user
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.post("/web/logout")
async def web_logout(response: Response):
    """Выход для веб-приложения (удаляет cookie)"""
    response.delete_cookie("access_token", path="/")
    return {"message": "Выход выполнен успешно"}
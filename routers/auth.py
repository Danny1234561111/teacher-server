# api/routes/auth.py
from fastapi import APIRouter, HTTPException, Depends, Response, Request
from pydantic import BaseModel, EmailStr
from typing import Optional
from sqlalchemy.orm import Session

from services.auth_service import AuthService
from database.database import get_db

router = APIRouter(tags=["authentication"])
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


class WebAuthResponse(BaseModel):
    user: UserResponse
    message: Optional[str] = None


class LogoutResponse(BaseModel):
    message: str


@router.post("/mobile/login", response_model=AuthResponse)
async def mobile_login(login_data: LoginRequest, db: Session = Depends(get_db)):
    try:
        result = auth_service.login_for_mobile(
            email=login_data.email,
            password=login_data.password,
            db=db
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        print(f"Ошибка входа: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


@router.get("/mobile/me", response_model=UserResponse)
async def mobile_get_current_user(token: str, db: Session = Depends(get_db)):
    try:
        user = auth_service.get_user_by_token(token, db)
        return user
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        print(f"Ошибка: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


@router.post("/web/login", response_model=WebAuthResponse)
async def web_login(
    response: Response,
    login_data: LoginRequest,
    db: Session = Depends(get_db)
):
    try:
        result = auth_service.login_for_web(
            email=login_data.email,
            password=login_data.password,
            response=response,
            db=db
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        print(f"Ошибка входа: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


@router.get("/web/me", response_model=UserResponse)
async def web_get_current_user(
    request: Request,
    db: Session = Depends(get_db)
):
    try:
        user = auth_service.get_current_user_web(request, db)
        return user
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        print(f"Ошибка: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


@router.post("/web/logout", response_model=LogoutResponse)
async def web_logout(response: Response):
    try:
        result = auth_service.logout_for_web(response)
        return result
    except Exception as e:
        print(f"Ошибка выхода: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")
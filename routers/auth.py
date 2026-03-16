from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session

from services.auth_service import AuthService
from database.database import get_db

router = APIRouter(tags=["authentication"])
auth_service = AuthService()


# Модели
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


# Эндпоинты
@router.post("/login", response_model=AuthResponse)
async def login(login_data: LoginRequest, db: Session = Depends(get_db)):
    """Вход пользователя"""
    try:
        result = auth_service.login(
            email=login_data.email,
            password=login_data.password,
            db=db
        )
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=401,
            detail=str(e)
        )
    except Exception as e:
        print(f"❌ Ошибка входа: {e}")
        raise HTTPException(
            status_code=500,
            detail="Внутренняя ошибка сервера"
        )


@router.get("/me", response_model=UserResponse)
async def get_current_user(token: str, db: Session = Depends(get_db)):
    """Получение данных пользователя по токену"""
    try:
        user = auth_service.get_user_by_token(token, db)
        return user
    except ValueError as e:
        raise HTTPException(
            status_code=401,
            detail=str(e)
        )
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        raise HTTPException(
            status_code=500,
            detail="Внутренняя ошибка сервера"
        )
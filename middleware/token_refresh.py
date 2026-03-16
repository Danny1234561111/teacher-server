# api/routes/token_refresh.py
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from jose import JWTError, jwt
from typing import Optional
import os

from database.database import get_db
from database.schema import User, RefreshToken
from api.routes.auth import create_access_token, create_refresh_token

router = APIRouter(prefix="/api", tags=["token"])

# Конфигурация JWT
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/login")


class TokenRefreshRequest:
    """Модель запроса на обновление токена"""

    def __init__(self, refresh_token: str):
        self.refresh_token = refresh_token


class TokenResponse:
    """Модель ответа с токенами"""

    def __init__(self, access_token: str, refresh_token: Optional[str] = None, token_type: str = "bearer"):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.token_type = token_type


@router.post("/refresh")
async def refresh_token(
        refresh_token: str,
        db: Session = Depends(get_db)
):
    """
    Обновление access токена с использованием refresh токена

    - Принимает действительный refresh токен
    - Проверяет его в базе данных
    - Выпускает новую пару токенов (access + refresh)
    - Старый refresh токен помечается как отозванный (revoked)
    """
    try:
        # Ищем refresh токен в базе данных
        db_refresh_token = db.query(RefreshToken).filter(
            RefreshToken.token == refresh_token,
            RefreshToken.revoked == False,  # Токен не должен быть отозван
            RefreshToken.expires_at > datetime.utcnow()  # Токен должен быть действительным
        ).first()

        if not db_refresh_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Недействительный или истекший refresh токен",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Получаем пользователя
        user = db.query(User).filter(User.id == db_refresh_token.user_id).first()
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Пользователь не найден или неактивен",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Помечаем старый refresh токен как отозванный (одноразовое использование)
        db_refresh_token.revoked = True
        db.commit()

        # Создаем новые токены
        access_token = create_access_token(data={"sub": user.email})
        new_refresh_token = create_refresh_token(data={"sub": user.email})

        # Сохраняем новый refresh токен в базе данных
        db_refresh_token_new = RefreshToken(
            token=new_refresh_token,
            user_id=user.id,
            expires_at=datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
            created_at=datetime.utcnow(),
            revoked=False
        )
        db.add(db_refresh_token_new)
        db.commit()

        return {
            "access_token": access_token,
            "refresh_token": new_refresh_token,
            "token_type": "bearer"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при обновлении токена: {str(e)}"
        )


@router.post("/logout")
async def logout(
        refresh_token: str,
        db: Session = Depends(get_db)
):
    """
    Выход из системы - отзыв refresh токена

    - Принимает refresh токен
    - Помечает его как отозванный (revoked)
    - Токен больше нельзя использовать для обновления
    """
    try:
        # Ищем refresh токен в базе данных
        db_refresh_token = db.query(RefreshToken).filter(
            RefreshToken.token == refresh_token,
            RefreshToken.revoked == False
        ).first()

        if db_refresh_token:
            # Помечаем токен как отозванный
            db_refresh_token.revoked = True
            db.commit()
            return {"message": "Успешный выход из системы"}
        else:
            return {"message": "Токен уже недействителен"}

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при выходе из системы: {str(e)}"
        )


@router.post("/logout-all")
async def logout_all(
        current_user: User = Depends(oauth2_scheme),
        db: Session = Depends(get_db)
):
    """
    Выход из всех устройств - отзыв всех refresh токенов пользователя

    - Требует валидный access токен
    - Помечает ВСЕ refresh токены пользователя как отозванные
    - Полезно при подозрении на компрометацию аккаунта
    """
    try:
        # Получаем email пользователя из токена
        payload = jwt.decode(current_user, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Недействительный токен"
            )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Недействительный токен"
        )

    # Находим пользователя
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден"
        )

    # Отзываем все активные refresh токены пользователя
    db.query(RefreshToken).filter(
        RefreshToken.user_id == user.id,
        RefreshToken.revoked == False
    ).update({"revoked": True})

    db.commit()

    return {"message": "Все сессии завершены"}


def cleanup_expired_tokens(db: Session):
    """
    Очистка истекших токенов (можно запускать по расписанию)
    Удаляет все истекшие токены из базы данных
    """
    try:
        deleted_count = db.query(RefreshToken).filter(
            RefreshToken.expires_at < datetime.utcnow()
        ).delete()
        db.commit()
        return {"deleted_tokens": deleted_count}
    except Exception as e:
        db.rollback()
        raise Exception(f"Ошибка при очистке токенов: {str(e)}")
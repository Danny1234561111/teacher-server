# dependencies.py
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from services.auth_service import AuthService
from database.database import get_db

security = HTTPBearer()
auth_service = AuthService()


def get_current_user(
        credentials: HTTPAuthorizationCredentials = Depends(security),
        db: Session = Depends(get_db)
) -> dict:
    """Зависимость для получения текущего пользователя"""
    token = credentials.credentials

    try:
        user = auth_service.get_current_user(token, db)
        return user
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"}
        )


def get_admin_user(
        current_user: dict = Depends(get_current_user)
) -> dict:
    """Зависимость для получения администратора"""
    if current_user.get('role') != 'admin':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Требуются права администратора"
        )
    return current_user


def get_teacher_user(
        current_user: dict = Depends(get_current_user)
) -> dict:
    """Зависимость для получения преподавателя"""
    if current_user.get('role') not in ['admin', 'teacher']:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Требуются права преподавателя или администратора"
        )
    return current_user
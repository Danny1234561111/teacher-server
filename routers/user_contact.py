from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, validator
from typing import Optional
from sqlalchemy.orm import Session
from datetime import datetime
import re

from database.database import get_db
from database.schema import User
from services.auth_service import AuthService

router = APIRouter(prefix="/api/user/contact", tags=["User Contact"])
security = HTTPBearer()
auth_service = AuthService()


class ActiveContactUpdate(BaseModel):
    contact_type: str = Field(..., description="Тип контакта: telegram, sms, call, url, other")
    contact_value: str = Field(..., description="Значение контакта: @username, +79991234567, https://...")

    @validator('contact_value')
    def validate_contact_value(cls, v, values):
        contact_type = values.get('contact_type')

        if contact_type == 'url':
            # Валидация URL
            url_pattern = re.compile(
                r'^https?://'  # http:// или https://
                r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # домен...
                r'localhost|'  # localhost...
                r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...или ip
                r'(?::\d+)?'  # опциональный порт
                r'(?:/?|[/?]\S+)$', re.IGNORECASE)

            if not url_pattern.match(v):
                raise ValueError('Неверный формат URL')

        elif contact_type == 'telegram':
            # Валидация Telegram username
            if not v.startswith('@'):
                raise ValueError('Telegram username должен начинаться с @')

        elif contact_type in ['sms', 'call']:
            # Валидация телефона
            phone_pattern = re.compile(r'^\+?[1-9]\d{10,14}$')
            cleaned = re.sub(r'[\s\-\(\)]', '', v)
            if not phone_pattern.match(cleaned):
                raise ValueError('Неверный формат номера телефона')

        return v


class ActiveContactResponse(BaseModel):
    contact_type: Optional[str]
    contact_value: Optional[str]
    updated_at: Optional[datetime]


async def get_current_user(
        credentials: HTTPAuthorizationCredentials = Depends(security),
        db: Session = Depends(get_db)
) -> User:
    token = credentials.credentials
    user_data = auth_service.get_user_by_token(token, db)

    user = db.query(User).filter(User.id == user_data['id']).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Пользователь неактивен")

    return user


@router.post("/set", response_model=ActiveContactResponse)
async def set_active_contact(
        contact_data: ActiveContactUpdate,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """Установить активный контакт для пользователя"""

    valid_types = ['telegram', 'sms', 'call', 'url', 'other']
    if contact_data.contact_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Неверный тип контакта. Допустимые: {', '.join(valid_types)}"
        )

    current_user.active_contact = contact_data.contact_value
    current_user.active_contact_type = contact_data.contact_type
    current_user.active_contact_updated_at = datetime.utcnow()

    db.commit()
    db.refresh(current_user)

    return ActiveContactResponse(
        contact_type=current_user.active_contact_type,
        contact_value=current_user.active_contact,
        updated_at=current_user.active_contact_updated_at
    )


@router.get("/get", response_model=Optional[ActiveContactResponse])
async def get_active_contact(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """Получить активный контакт пользователя"""
    if not current_user.active_contact:
        return None

    return ActiveContactResponse(
        contact_type=current_user.active_contact_type,
        contact_value=current_user.active_contact,
        updated_at=current_user.active_contact_updated_at
    )


@router.delete("/delete")
async def delete_active_contact(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """Удалить активный контакт пользователя"""
    current_user.active_contact = None
    current_user.active_contact_type = None
    current_user.active_contact_updated_at = None

    db.commit()

    return {"message": "Активный контакт удален"}
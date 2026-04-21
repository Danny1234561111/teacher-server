from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from typing import Optional
from sqlalchemy.orm import Session
from datetime import datetime

from database.database import get_db
from database.schema import User
from services.auth_service import AuthService

router = APIRouter(prefix="/api/user/contact", tags=["User Contact"])
security = HTTPBearer()
auth_service = AuthService()


class ActiveContactUpdate(BaseModel):
    contact_type: str = Field(..., description="Тип контакта: telegram, whatsapp, sms, call")
    contact_value: str = Field(..., description="Значение контакта: @username или +79991234567")


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

    valid_types = ['telegram', 'whatsapp', 'sms', 'call']
    if contact_data.contact_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Неверный тип контакта. Допустимые: {', '.join(valid_types)}"
        )

    current_user.active_contact = contact_data.contact_value
    current_user.active_contact_type = contact_data.contact_type
    current_user.active_contact_updated_at = datetime.utcnow()

    db.commit()

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
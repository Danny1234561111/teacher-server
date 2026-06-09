# api/routes/communication.py
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, field_validator
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from datetime import datetime
import re

from database.database import get_db
from database.schema import User, Student
from services.auth_service import AuthService
from services.websocket_manager import websocket_manager

router = APIRouter()
security = HTTPBearer()
auth_service = AuthService()


class ActiveContactUpdate(BaseModel):
    contact_type: str = Field(..., description="Тип контакта: telegram, sms, call, url, vk")
    contact_value: str = Field(..., description="Значение контакта: @username, +79991234567, https://...")

    @field_validator('contact_value')
    @classmethod
    def validate_contact_value(cls, v, info):
        contact_type = info.data.get('contact_type')

        if contact_type == 'url':
            url_pattern = re.compile(
                r'^https?://'
                r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'
                r'localhost|'
                r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
                r'(?::\d+)?'
                r'(?:/?|[/?]\S+)$', re.IGNORECASE)
            if not url_pattern.match(v):
                raise ValueError('Неверный формат URL')

        elif contact_type == 'telegram':
            phone_pattern = re.compile(r'^\+?[1-9]\d{10,14}$')
            cleaned = re.sub(r'[\s\-\(\)]', '', v)
            if phone_pattern.match(cleaned):
                return v
            elif v.startswith('@'):
                if len(v) < 2:
                    raise ValueError('Telegram username слишком короткий')
                return v
            else:
                raise ValueError('Telegram контакт должен быть @username или номером телефона')

        elif contact_type == 'vk':
            if not v or len(v) < 1:
                raise ValueError('VK контакт не может быть пустым')
            return v

        elif contact_type in ['sms', 'call']:
            phone_pattern = re.compile(r'^\+?[1-9]\d{10,14}$')
            cleaned = re.sub(r'[\s\-\(\)]', '', v)
            if not phone_pattern.match(cleaned):
                raise ValueError('Неверный формат номера телефона')

        return v


class ActiveContactResponse(BaseModel):
    contact_type: Optional[str]
    contact_value: Optional[str]
    updated_at: Optional[datetime]


class CommunicationSettingsUpdate(BaseModel):
    telegram_open_on: Optional[str] = Field(None, description="Где открывать Telegram: 'pc' или 'mobile'")
    vk_open_on: Optional[str] = Field(None, description="Где открывать VK: 'pc' или 'mobile'")
    url_open_on: Optional[str] = Field(None, description="Где открывать ссылки: 'pc' или 'mobile'")

    @field_validator('telegram_open_on', 'vk_open_on', 'url_open_on')
    @classmethod
    def validate_open_on(cls, v):
        if v is not None and v not in ['pc', 'mobile']:
            raise ValueError("Значение должно быть 'pc' или 'mobile'")
        return v


class CommunicationSettingsResponse(BaseModel):
    telegram_open_on: str
    vk_open_on: str
    url_open_on: str


class CallRequest(BaseModel):
    student_id: int
    phone_number: str


class SmsRequest(BaseModel):
    student_id: int
    phone_number: str
    message_text: Optional[str] = None


class TelegramRequest(BaseModel):
    student_id: int
    telegram_contact: str


class VkRequest(BaseModel):
    student_id: int
    vk_contact: str


class UrlRequest(BaseModel):
    student_id: int
    url: str


class CommunicationResponse(BaseModel):
    success: bool
    action: str
    target_device: str
    message: str
    student_name: Optional[str] = None
    data: Optional[Dict] = None
    fallback: Optional[str] = None


async def get_current_user_mobile(
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


async def get_current_user_web(
        request: Request,
        db: Session = Depends(get_db)
) -> User:
    user_data = auth_service.get_current_user_web(request, db)
    user = db.query(User).filter(User.id == user_data['id']).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Пользователь неактивен")
    return user


async def get_student_by_id(student_id: int, db: Session) -> Optional[Dict]:
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        return None
    return {
        'id': student.id,
        'full_name': student.full_name,
        'phone': student.phone,
        'additional_contacts': student.additional_contacts
    }


def determine_target_device(contact_type: str, user: User) -> str:
    if contact_type in ['call', 'sms']:
        return 'mobile'

    settings_map = {
        'telegram': user.telegram_open_on or 'pc',
        'vk': user.vk_open_on or 'pc',
        'url': user.url_open_on or 'pc'
    }
    return settings_map.get(contact_type, 'pc')


@router.post("/active/set", response_model=ActiveContactResponse)
async def mobile_set_active_contact(
        contact_data: ActiveContactUpdate,
        current_user: User = Depends(get_current_user_mobile),
        db: Session = Depends(get_db)
):
    valid_types = ['telegram', 'sms', 'call', 'url', 'vk']
    if contact_data.contact_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Неверный тип. Допустимые: {', '.join(valid_types)}"
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


@router.post("/web/active/set", response_model=ActiveContactResponse)
async def web_set_active_contact(
        request: Request,
        contact_data: ActiveContactUpdate,
        db: Session = Depends(get_db)
):
    current_user = await get_current_user_web(request, db)

    valid_types = ['telegram', 'sms', 'call', 'url', 'vk']
    if contact_data.contact_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Неверный тип. Допустимые: {', '.join(valid_types)}"
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


@router.get("/active/get", response_model=Optional[ActiveContactResponse])
async def mobile_get_active_contact(
        current_user: User = Depends(get_current_user_mobile),
        db: Session = Depends(get_db)
):
    if not current_user.active_contact:
        return None

    return ActiveContactResponse(
        contact_type=current_user.active_contact_type,
        contact_value=current_user.active_contact,
        updated_at=current_user.active_contact_updated_at
    )


@router.get("/web/active/get", response_model=Optional[ActiveContactResponse])
async def web_get_active_contact(
        request: Request,
        db: Session = Depends(get_db)
):
    current_user = await get_current_user_web(request, db)

    if not current_user.active_contact:
        return None

    return ActiveContactResponse(
        contact_type=current_user.active_contact_type,
        contact_value=current_user.active_contact,
        updated_at=current_user.active_contact_updated_at
    )


@router.delete("/active/delete")
async def mobile_delete_active_contact(
        current_user: User = Depends(get_current_user_mobile),
        db: Session = Depends(get_db)
):
    current_user.active_contact = None
    current_user.active_contact_type = None
    current_user.active_contact_updated_at = None

    db.commit()
    return {"message": "Активный контакт удален"}


@router.delete("/web/active/delete")
async def web_delete_active_contact(
        request: Request,
        db: Session = Depends(get_db)
):
    current_user = await get_current_user_web(request, db)

    current_user.active_contact = None
    current_user.active_contact_type = None
    current_user.active_contact_updated_at = None

    db.commit()
    return {"message": "Активный контакт удален"}


@router.post("/active/use")
async def mobile_use_active_contact(
        student_id: int,
        current_user: User = Depends(get_current_user_mobile),
        db: Session = Depends(get_db)
):
    student = await get_student_by_id(student_id, db)
    if not student:
        raise HTTPException(status_code=404, detail="Студент не найден")

    if not current_user.active_contact or not current_user.active_contact_type:
        raise HTTPException(status_code=400, detail="Активный контакт не установлен")

    contact_type = current_user.active_contact_type
    contact_value = current_user.active_contact
    target_device = determine_target_device(contact_type, current_user)

    command = {
        "action": contact_type,
        "student_id": student['id'],
        "student_name": student['full_name'],
        "contact_value": contact_value,
    }

    if contact_type == 'call':
        command["type"] = "make_call"
        command["phone_number"] = contact_value
    elif contact_type == 'sms':
        command["type"] = "send_sms"
        command["phone_number"] = contact_value
        command["message_text"] = f"Здравствуйте, {student['full_name']}!"
    elif contact_type == 'telegram':
        command["type"] = "open_telegram"
        command["telegram_contact"] = contact_value
    elif contact_type == 'vk':
        command["type"] = "open_vk"
        command["vk_contact"] = contact_value
    elif contact_type == 'url':
        command["type"] = "open_url"
        command["url"] = contact_value

    if target_device == "mobile":
        if not websocket_manager.is_connected(current_user.id):
            return CommunicationResponse(
                success=False,
                action=contact_type,
                target_device="mobile",
                message="Мобильное устройство не подключено",
                student_name=student['full_name'],
                fallback=f"{contact_type}:{contact_value}"
            )

        sent = await websocket_manager.send_command(current_user.id, command)
        if sent:
            return CommunicationResponse(
                success=True,
                action=contact_type,
                target_device="mobile",
                message="Команда отправлена на телефон",
                student_name=student['full_name']
            )
        else:
            return CommunicationResponse(
                success=False,
                action=contact_type,
                target_device="mobile",
                message="Не удалось отправить команду",
                student_name=student['full_name']
            )
    else:
        url = contact_value
        if contact_type == 'telegram':
            url = f"https://web.telegram.org/k/#@{contact_value.replace('@', '')}"
        elif contact_type == 'vk':
            url = f"https://vk.com/{contact_value}"

        return CommunicationResponse(
            success=True,
            action=contact_type,
            target_device="pc",
            message="Открыть на компьютере",
            student_name=student['full_name'],
            data={"url": url}
        )


@router.post("/web/active/use")
async def web_use_active_contact(
        request: Request,
        student_id: int,
        db: Session = Depends(get_db)
):
    current_user = await get_current_user_web(request, db)

    student = await get_student_by_id(student_id, db)
    if not student:
        raise HTTPException(status_code=404, detail="Студент не найден")

    if not current_user.active_contact or not current_user.active_contact_type:
        raise HTTPException(status_code=400, detail="Активный контакт не установлен")

    contact_type = current_user.active_contact_type
    contact_value = current_user.active_contact
    target_device = determine_target_device(contact_type, current_user)

    command = {
        "action": contact_type,
        "student_id": student['id'],
        "student_name": student['full_name'],
        "contact_value": contact_value,
    }

    if contact_type == 'call':
        command["type"] = "make_call"
        command["phone_number"] = contact_value
    elif contact_type == 'sms':
        command["type"] = "send_sms"
        command["phone_number"] = contact_value
        command["message_text"] = f"Здравствуйте, {student['full_name']}!"
    elif contact_type == 'telegram':
        command["type"] = "open_telegram"
        command["telegram_contact"] = contact_value
    elif contact_type == 'vk':
        command["type"] = "open_vk"
        command["vk_contact"] = contact_value
    elif contact_type == 'url':
        command["type"] = "open_url"
        command["url"] = contact_value

    if target_device == "mobile":
        if not websocket_manager.is_connected(current_user.id):
            return CommunicationResponse(
                success=False,
                action=contact_type,
                target_device="mobile",
                message="Мобильное устройство не подключено",
                student_name=student['full_name'],
                fallback=f"{contact_type}:{contact_value}"
            )

        sent = await websocket_manager.send_command(current_user.id, command)
        if sent:
            return CommunicationResponse(
                success=True,
                action=contact_type,
                target_device="mobile",
                message="Команда отправлена на телефон",
                student_name=student['full_name']
            )
        else:
            return CommunicationResponse(
                success=False,
                action=contact_type,
                target_device="mobile",
                message="Не удалось отправить команду",
                student_name=student['full_name']
            )
    else:
        url = contact_value
        if contact_type == 'telegram':
            url = f"https://web.telegram.org/k/#@{contact_value.replace('@', '')}"
        elif contact_type == 'vk':
            url = f"https://vk.com/{contact_value}"

        return CommunicationResponse(
            success=True,
            action=contact_type,
            target_device="pc",
            message="Открыть на компьютере",
            student_name=student['full_name'],
            data={"url": url}
        )


@router.get("/settings", response_model=CommunicationSettingsResponse)
async def mobile_get_communication_settings(
        current_user: User = Depends(get_current_user_mobile),
        db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == current_user.id).first()

    return CommunicationSettingsResponse(
        telegram_open_on=user.telegram_open_on or "pc",
        vk_open_on=user.vk_open_on or "pc",
        url_open_on=user.url_open_on or "pc"
    )


@router.get("/web/settings", response_model=CommunicationSettingsResponse)
async def web_get_communication_settings(
        request: Request,
        db: Session = Depends(get_db)
):
    current_user = await get_current_user_web(request, db)
    user = db.query(User).filter(User.id == current_user.id).first()

    return CommunicationSettingsResponse(
        telegram_open_on=user.telegram_open_on or "pc",
        vk_open_on=user.vk_open_on or "pc",
        url_open_on=user.url_open_on or "pc"
    )


@router.put("/settings", response_model=CommunicationSettingsResponse)
async def mobile_update_communication_settings(
        settings: CommunicationSettingsUpdate,
        current_user: User = Depends(get_current_user_mobile),
        db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == current_user.id).first()

    if settings.telegram_open_on is not None:
        user.telegram_open_on = settings.telegram_open_on
    if settings.vk_open_on is not None:
        user.vk_open_on = settings.vk_open_on
    if settings.url_open_on is not None:
        user.url_open_on = settings.url_open_on

    db.commit()

    return CommunicationSettingsResponse(
        telegram_open_on=user.telegram_open_on or "pc",
        vk_open_on=user.vk_open_on or "pc",
        url_open_on=user.url_open_on or "pc"
    )


@router.put("/web/settings", response_model=CommunicationSettingsResponse)
async def web_update_communication_settings(
        request: Request,
        settings: CommunicationSettingsUpdate,
        db: Session = Depends(get_db)
):
    current_user = await get_current_user_web(request, db)
    user = db.query(User).filter(User.id == current_user.id).first()

    if settings.telegram_open_on is not None:
        user.telegram_open_on = settings.telegram_open_on
    if settings.vk_open_on is not None:
        user.vk_open_on = settings.vk_open_on
    if settings.url_open_on is not None:
        user.url_open_on = settings.url_open_on

    db.commit()

    return CommunicationSettingsResponse(
        telegram_open_on=user.telegram_open_on or "pc",
        vk_open_on=user.vk_open_on or "pc",
        url_open_on=user.url_open_on or "pc"
    )


@router.post("/call", response_model=CommunicationResponse)
async def mobile_make_call(
        request_data: CallRequest,
        current_user: User = Depends(get_current_user_mobile),
        db: Session = Depends(get_db)
):
    student = await get_student_by_id(request_data.student_id, db)
    if not student:
        raise HTTPException(status_code=404, detail="Студент не найден")

    if not websocket_manager.is_connected(current_user.id):
        return CommunicationResponse(
            success=False,
            action="call",
            target_device="mobile",
            message="Мобильное устройство не подключено",
            student_name=student['full_name'],
            fallback=f"tel:{request_data.phone_number}"
        )

    command = {
        "type": "make_call",
        "action": "call",
        "student_id": student['id'],
        "student_name": student['full_name'],
        "phone_number": request_data.phone_number,
    }

    sent = await websocket_manager.send_command(current_user.id, command)

    if sent:
        return CommunicationResponse(
            success=True,
            action="call",
            target_device="mobile",
            message="Звонок инициирован на телефоне",
            student_name=student['full_name']
        )
    else:
        return CommunicationResponse(
            success=False,
            action="call",
            target_device="mobile",
            message="Не удалось отправить команду",
            student_name=student['full_name']
        )


@router.post("/web/call", response_model=CommunicationResponse)
async def web_make_call(
        request: Request,
        request_data: CallRequest,
        db: Session = Depends(get_db)
):
    current_user = await get_current_user_web(request, db)

    student = await get_student_by_id(request_data.student_id, db)
    if not student:
        raise HTTPException(status_code=404, detail="Студент не найден")

    if not websocket_manager.is_connected(current_user.id):
        return CommunicationResponse(
            success=False,
            action="call",
            target_device="mobile",
            message="Мобильное устройство не подключено",
            student_name=student['full_name'],
            fallback=f"tel:{request_data.phone_number}"
        )

    command = {
        "type": "make_call",
        "action": "call",
        "student_id": student['id'],
        "student_name": student['full_name'],
        "phone_number": request_data.phone_number,
    }

    sent = await websocket_manager.send_command(current_user.id, command)

    if sent:
        return CommunicationResponse(
            success=True,
            action="call",
            target_device="mobile",
            message="Звонок инициирован на телефоне",
            student_name=student['full_name']
        )
    else:
        return CommunicationResponse(
            success=False,
            action="call",
            target_device="mobile",
            message="Не удалось отправить команду",
            student_name=student['full_name']
        )
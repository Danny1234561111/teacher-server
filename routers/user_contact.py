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


# ===== МОДЕЛИ =====

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


# ===== УНИВЕРСАЛЬНАЯ АУТЕНТИФИКАЦИЯ =====

async def get_current_user_universal(
        request: Request,
        credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
        db: Session = Depends(get_db)
) -> User:
    """Универсальная аутентификация: Bearer (мобилка) или Cookie (веб)"""
    token = None

    # 1. Пробуем Bearer token (мобильное приложение)
    if credentials and credentials.credentials:
        token = credentials.credentials

    # 2. Если нет Bearer, пробуем Cookie (веб-приложение)
    if not token:
        token = request.cookies.get("access_token")

    if not token:
        raise HTTPException(status_code=401, detail="Токен не найден")

    try:
        user_data = auth_service.get_user_by_token(token, db)
        user = db.query(User).filter(User.id == user_data['id']).first()
        if not user:
            raise HTTPException(status_code=404, detail="Пользователь не найден")
        if not user.is_active:
            raise HTTPException(status_code=403, detail="Пользователь неактивен")
        return user
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


async def get_student_by_id(student_id: int, db: Session) -> Optional[Dict]:
    """Получение студента по ID"""
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
    """Определяет, на какое устройство отправлять команду"""
    if contact_type in ['call', 'sms']:
        return 'mobile'
    settings_map = {
        'telegram': user.telegram_open_on or 'pc',
        'vk': user.vk_open_on or 'pc',
        'url': user.url_open_on or 'pc'
    }
    return settings_map.get(contact_type, 'pc')


# ===== 1. АКТИВНЫЙ КОНТАКТ =====

@router.post("/active/set", response_model=ActiveContactResponse)
async def set_active_contact(
        request: Request,
        contact_data: ActiveContactUpdate,
        current_user: User = Depends(get_current_user_universal),
        db: Session = Depends(get_db)
):
    """Установить активный контакт"""
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
async def get_active_contact(
        request: Request,
        current_user: User = Depends(get_current_user_universal),
        db: Session = Depends(get_db)
):
    """Получить активный контакт"""
    if not current_user.active_contact:
        return None

    return ActiveContactResponse(
        contact_type=current_user.active_contact_type,
        contact_value=current_user.active_contact,
        updated_at=current_user.active_contact_updated_at
    )


@router.delete("/active/delete")
async def delete_active_contact(
        request: Request,
        current_user: User = Depends(get_current_user_universal),
        db: Session = Depends(get_db)
):
    """Удалить активный контакт"""
    current_user.active_contact = None
    current_user.active_contact_type = None
    current_user.active_contact_updated_at = None

    db.commit()
    return {"message": "Активный контакт удален"}


@router.post("/active/use")
async def use_active_contact(
        request: Request,
        student_id: int,
        current_user: User = Depends(get_current_user_universal),
        db: Session = Depends(get_db)
):
    """Использовать активный контакт для связи со студентом"""
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


# ===== 2. НАСТРОЙКИ КОММУНИКАЦИИ =====

@router.get("/settings", response_model=CommunicationSettingsResponse)
async def get_communication_settings(
        request: Request,
        current_user: User = Depends(get_current_user_universal),
        db: Session = Depends(get_db)
):
    """Получить настройки коммуникации пользователя"""
    user = db.query(User).filter(User.id == current_user.id).first()

    return CommunicationSettingsResponse(
        telegram_open_on=user.telegram_open_on or "pc",
        vk_open_on=user.vk_open_on or "pc",
        url_open_on=user.url_open_on or "pc"
    )


@router.put("/settings", response_model=CommunicationSettingsResponse)
async def update_communication_settings(
        request: Request,
        settings: CommunicationSettingsUpdate,
        current_user: User = Depends(get_current_user_universal),
        db: Session = Depends(get_db)
):
    """Обновить настройки коммуникации пользователя"""
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


# ===== 3. ПРЯМАЯ КОММУНИКАЦИЯ =====

@router.post("/call", response_model=CommunicationResponse)
async def make_call(
        request: Request,
        call_request: CallRequest,
        current_user: User = Depends(get_current_user_universal),
        db: Session = Depends(get_db)
):
    """Позвонить студенту (всегда на телефон)"""
    student = await get_student_by_id(call_request.student_id, db)
    if not student:
        raise HTTPException(status_code=404, detail="Студент не найден")

    if not websocket_manager.is_connected(current_user.id):
        return CommunicationResponse(
            success=False,
            action="call",
            target_device="mobile",
            message="Мобильное устройство не подключено",
            student_name=student['full_name'],
            fallback=f"tel:{call_request.phone_number}"
        )

    command = {
        "type": "make_call",
        "action": "call",
        "student_id": student['id'],
        "student_name": student['full_name'],
        "phone_number": call_request.phone_number,
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


@router.post("/sms", response_model=CommunicationResponse)
async def send_sms(
        request: Request,
        sms_request: SmsRequest,
        current_user: User = Depends(get_current_user_universal),
        db: Session = Depends(get_db)
):
    """Отправить SMS студенту (всегда на телефон)"""
    student = await get_student_by_id(sms_request.student_id, db)
    if not student:
        raise HTTPException(status_code=404, detail="Студент не найден")

    if not websocket_manager.is_connected(current_user.id):
        return CommunicationResponse(
            success=False,
            action="sms",
            target_device="mobile",
            message="Мобильное устройство не подключено",
            student_name=student['full_name'],
            fallback=f"sms:{sms_request.phone_number}"
        )

    command = {
        "type": "send_sms",
        "action": "sms",
        "student_id": student['id'],
        "student_name": student['full_name'],
        "phone_number": sms_request.phone_number,
        "message_text": sms_request.message_text or f"Здравствуйте, {student['full_name']}!"
    }

    sent = await websocket_manager.send_command(current_user.id, command)

    if sent:
        return CommunicationResponse(
            success=True,
            action="sms",
            target_device="mobile",
            message="SMS открыта на телефоне",
            student_name=student['full_name']
        )
    else:
        return CommunicationResponse(
            success=False,
            action="sms",
            target_device="mobile",
            message="Не удалось отправить команду",
            student_name=student['full_name']
        )


@router.post("/telegram", response_model=CommunicationResponse)
async def open_telegram(
        request: Request,
        telegram_request: TelegramRequest,
        current_user: User = Depends(get_current_user_universal),
        db: Session = Depends(get_db)
):
    """Открыть Telegram (по настройкам пользователя)"""
    student = await get_student_by_id(telegram_request.student_id, db)
    if not student:
        raise HTTPException(status_code=404, detail="Студент не найден")

    user = db.query(User).filter(User.id == current_user.id).first()
    target_device = determine_target_device("telegram", user)

    if target_device == "mobile" and websocket_manager.is_connected(current_user.id):
        command = {
            "type": "open_telegram",
            "action": "telegram",
            "student_id": student['id'],
            "student_name": student['full_name'],
            "telegram_contact": telegram_request.telegram_contact,
        }
        sent = await websocket_manager.send_command(current_user.id, command)
        if sent:
            return CommunicationResponse(
                success=True,
                action="telegram",
                target_device="mobile",
                message="Telegram открывается на телефоне",
                student_name=student['full_name']
            )

    username = telegram_request.telegram_contact.replace('@', '').strip()
    url = f"https://web.telegram.org/k/#@{username}"

    return CommunicationResponse(
        success=True,
        action="telegram",
        target_device="pc",
        message="Открыть Telegram в браузере",
        student_name=student['full_name'],
        data={"url": url}
    )


@router.post("/vk", response_model=CommunicationResponse)
async def open_vk(
        request: Request,
        vk_request: VkRequest,
        current_user: User = Depends(get_current_user_universal),
        db: Session = Depends(get_db)
):
    """Открыть VK (по настройкам пользователя)"""
    student = await get_student_by_id(vk_request.student_id, db)
    if not student:
        raise HTTPException(status_code=404, detail="Студент не найден")

    user = db.query(User).filter(User.id == current_user.id).first()
    target_device = determine_target_device("vk", user)

    if target_device == "mobile" and websocket_manager.is_connected(current_user.id):
        command = {
            "type": "open_vk",
            "action": "vk",
            "student_id": student['id'],
            "student_name": student['full_name'],
            "vk_contact": vk_request.vk_contact,
        }
        sent = await websocket_manager.send_command(current_user.id, command)
        if sent:
            return CommunicationResponse(
                success=True,
                action="vk",
                target_device="mobile",
                message="VK открывается на телефоне",
                student_name=student['full_name']
            )

    url = f"https://vk.com/{vk_request.vk_contact}"

    return CommunicationResponse(
        success=True,
        action="vk",
        target_device="pc",
        message="Открыть VK в браузере",
        student_name=student['full_name'],
        data={"url": url}
    )


@router.post("/url", response_model=CommunicationResponse)
async def open_url(
        request: Request,
        url_request: UrlRequest,
        current_user: User = Depends(get_current_user_universal),
        db: Session = Depends(get_db)
):
    """Открыть URL (по настройкам пользователя)"""
    student = await get_student_by_id(url_request.student_id, db)
    if not student:
        raise HTTPException(status_code=404, detail="Студент не найден")

    user = db.query(User).filter(User.id == current_user.id).first()
    target_device = determine_target_device("url", user)

    if target_device == "mobile" and websocket_manager.is_connected(current_user.id):
        command = {
            "type": "open_url",
            "action": "url",
            "student_id": student['id'],
            "student_name": student['full_name'],
            "url": url_request.url,
        }
        sent = await websocket_manager.send_command(current_user.id, command)
        if sent:
            return CommunicationResponse(
                success=True,
                action="url",
                target_device="mobile",
                message="Ссылка открывается на телефоне",
                student_name=student['full_name']
            )

    return CommunicationResponse(
        success=True,
        action="url",
        target_device="pc",
        message="Открыть ссылку в браузере",
        student_name=student['full_name'],
        data={"url": url_request.url}
    )
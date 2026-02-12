from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional, Dict, Any
from datetime import date
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from services.auth_service import AuthService
from schemas import AuthResponse, LoginRequest, RegisterRequest, TeacherRegistrationRequest
from database.database import get_db
from sqlalchemy.orm import Session

router = APIRouter(tags=["authentication"])

# Создаем экземпляр сервиса
auth_service = AuthService()
security = HTTPBearer()


# Модели запросов (убрана Firebase)
class UserRegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6)
    full_name: str = Field(..., min_length=2)
    phone: Optional[str] = None
    role: Optional[str] = "teacher"
    date_of_birth: Optional[date] = None
    max_students: Optional[int] = 20


# Модели ответов
class TeacherRequestResponse(BaseModel):
    message: str
    details: str
    request_id: str
    status: str = "pending"


class RegistrationResponse(BaseModel):
    message: str
    details: Optional[str] = None
    request_id: Optional[str] = None


@router.post("/login", response_model=AuthResponse)
async def login(login_data: LoginRequest, db: Session = Depends(get_db)):
    """Вход пользователя (традиционный) с улучшенными ошибками"""
    try:
        result = auth_service.login_with_email_password(
            email=login_data.email,
            password=login_data.password,
            db=db
        )

        # Добавляем user_id если его нет
        if 'user_id' not in result and 'user' in result:
            result['user_id'] = result['user'].get('id', '')

        return result
    except ValueError as e:
        error_msg = str(e)
        error_mapping = {
            "EMAIL_NOT_FOUND": "❌ Пользователь с таким email не найден",
            "INVALID_PASSWORD": "❌ Неверный пароль",
            "USER_DISABLED": "❌ Аккаунт отключен администратором",
            "TOO_MANY_ATTEMPTS_TRY_LATER": "❌ Слишком много попыток. Попробуйте позже",
            "INVALID_ID_TOKEN": "❌ Недействительный токен",
            "TOKEN_EXPIRED": "❌ Срок действия токена истек",
            "Пользователь не найден": "❌ Пользователь не найден",
            "Пользователь неактивен": "❌ Ваш аккаунт не активирован. Ожидайте одобрения администратора",
            "Аккаунт ожидает активации": "❌ Ваш аккаунт ожидает активации администратором"
        }

        detail = error_mapping.get(error_msg, f"❌ Ошибка входа: {error_msg}")

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail
        )
    except Exception as e:
        print(f"❌ Ошибка входа: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"❌ Внутренняя ошибка сервера при входе"
        )


@router.post("/register", response_model=dict)
async def register(register_data: RegisterRequest, db: Session = Depends(get_db)):
    """Регистрация пользователя (традиционная)"""
    try:
        # Если регистрируется преподаватель - создаем заявку
        if register_data.role == "teacher":
            request_data = register_data.dict()
            request_data['message'] = f"Запрос на регистрацию преподавателя {register_data.full_name}"

            result = auth_service.register_teacher_request(request_data, db)

            # Возвращаем правильный формат ответа для заявки преподавателя
            return {
                "message": "✅ Заявка на регистрацию отправлена!",
                "details": "Ваша заявка отправлена администратору. Вы получите email с данными для входа после одобрения.",
                "request_id": result.get('request_id'),
                "status": "pending"
            }

        # Для студентов и админов - обычная регистрация
        # Конвертируем Pydantic model в dict
        request_dict = register_data.dict()

        # Для студентов тоже создаем заявку
        if register_data.role == "student":
            # Здесь будет логика создания заявки на регистрацию студента
            # Пока используем обычную регистрацию
            result = auth_service.register(request_dict, db)
        else:
            # Для админов - прямая регистрация
            result = auth_service.register(request_dict, db)

        # Добавляем user_id если его нет
        if 'user_id' not in result and 'user' in result:
            result['user_id'] = result['user'].get('id', '')

        return result
    except ValueError as e:
        error_msg = str(e)
        error_mapping = {
            "EMAIL_EXISTS": "❌ Пользователь с таким email уже существует",
            "WEAK_PASSWORD": "❌ Пароль должен содержать минимум 6 символов",
            "INVALID_EMAIL": "❌ Неверный формат email",
            "Неверный формат email": "❌ Неверный формат email",
            "Пароль должен содержать минимум 6 символов": "❌ Пароль должен содержать минимум 6 символов",
            "Имя должно содержать минимум 2 символа": "❌ Имя должно содержать минимум 2 символа"
        }

        detail = error_mapping.get(error_msg, f"❌ Ошибка регистрации: {error_msg}")

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail
        )
    except Exception as e:
        print(f"❌ Ошибка регистрации: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"❌ Внутренняя ошибка сервера при регистрации"
        )


@router.post("/register/teacher-request", response_model=TeacherRequestResponse)
async def register_teacher_request(register_data: TeacherRegistrationRequest, db: Session = Depends(get_db)):
    """Запрос на регистрацию преподавателя (с дополнительной информация)"""
    try:
        request_dict = register_data.dict()

        result = auth_service.register_teacher_request(request_dict, db)

        return {
            "message": "✅ Заявка успешно отправлена!",
            "details": "Ваша заявка на регистрацию в качестве преподавателя отправлена администратору. Вы получите уведомление по email после рассмотрения заявки.",
            "request_id": result.get('request_id'),
            "status": "pending"
        }
    except ValueError as e:
        error_msg = str(e)
        error_mapping = {
            "Пользователь с таким email уже существует": "❌ Пользователь с таким email уже существует",
            "EMAIL_EXISTS": "❌ Пользователь с таким email уже существует",
            "Заявка уже отправлена и ожидает рассмотрения": "❌ Заявка уже отправлена и ожидает рассмотрения",
            "Заявка уже одобрена": "❌ Заявка уже одобрена. Проверьте ваш email.",
            "Заявка была отклонена": "❌ Заявка была отклонена. Обратитесь к администратору."
        }

        detail = error_mapping.get(error_msg, f"❌ Ошибка: {error_msg}")

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail
        )
    except Exception as e:
        print(f"❌ Ошибка отправки заявки: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"❌ Внутренняя ошибка сервера при отправке заявки"
        )


@router.get("/me")
async def get_current_user(
        credentials: HTTPAuthorizationCredentials = Depends(security),
        db: Session = Depends(get_db)
):
    """Получение текущего пользователя по токену из заголовка"""
    try:
        token = credentials.credentials
        user = auth_service.get_current_user(token, db)
        return {"user": user}
    except ValueError as e:
        error_msg = str(e)
        error_mapping = {
            "Срок действия токена истек": "❌ Срок действия токена истек",
            "Токен был отозван": "❌ Токен был отозван",
            "Недействительный токен": "❌ Недействительный токен",
            "Пользователь не найден": "❌ Пользователь не найден",
            "Пользователь неактивен": "❌ Пользователь неактивен"
        }

        detail = error_mapping.get(error_msg, f"❌ Ошибка аутентификации: {error_msg}")

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail
        )
    except Exception as e:
        print(f"❌ Ошибка получения пользователя: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"❌ Внутренняя ошибка сервера при получении данных пользователя"
        )


@router.post("/validate-token")
async def validate_token(
        credentials: HTTPAuthorizationCredentials = Depends(security),
        db: Session = Depends(get_db)
):
    """Проверка валидности токена"""
    try:
        token = credentials.credentials
        is_valid = auth_service.validate_token(token, db)
        return {"valid": is_valid}
    except Exception as e:
        print(f"❌ Ошибка проверки токена: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"❌ Внутренняя ошибка сервера при проверке токена"
        )


@router.post("/logout")
async def logout(
        credentials: HTTPAuthorizationCredentials = Depends(security),
        db: Session = Depends(get_db)
):
    """Выход пользователя"""
    try:
        token = credentials.credentials
        # Для логаута нужен refresh токен, но в текущей реализации
        # мы просто отзываем все токены пользователя
        user = auth_service.get_current_user(token, db)
        result = auth_service.logout_all_devices(user['id'], db)
        return result
    except Exception as e:
        print(f"❌ Ошибка выхода: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"❌ Внутренняя ошибка сервера при выходе"
        )


@router.post("/refresh")
async def refresh_token(refresh_token: str, db: Session = Depends(get_db)):
    """Обновление JWT токена"""
    try:
        result = auth_service.refresh_tokens(refresh_token, db)
        return result
    except ValueError as e:
        error_msg = str(e)
        error_mapping = {
            "Не удалось обновить токен": "❌ Не удалось обновить токен",
            "Пользователь не найден": "❌ Пользователь не найден"
        }

        detail = error_mapping.get(error_msg, f"❌ Ошибка обновления токена: {error_msg}")

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail
        )
    except Exception as e:
        print(f"❌ Ошибка обновления токена: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"❌ Внутренняя ошибка сервера при обновлении токена"
        )


@router.post("/reset-password")
async def reset_password(email: str, db: Session = Depends(get_db)):
    """Сброс пароля (отправка письма)"""
    try:
        result = auth_service.reset_password_request(email, db)
        return result
    except ValueError as e:
        error_msg = str(e)
        error_mapping = {
            "EMAIL_NOT_FOUND": "❌ Пользователь с таким email не найден"
        }

        detail = error_mapping.get(error_msg, f"❌ Ошибка сброса пароля: {error_msg}")

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail
        )
    except Exception as e:
        print(f"❌ Ошибка сброса пароля: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"❌ Внутренняя ошибка сервера при сбросе пароля"
        )


@router.post("/change-password")
async def change_password(
        new_password: str,
        credentials: HTTPAuthorizationCredentials = Depends(security),
        db: Session = Depends(get_db)
):
    """Смена пароля текущего пользователя"""
    try:
        token = credentials.credentials
        # В текущей реализации нужно знать старый пароль
        # Пока возвращаем сообщение о необходимости реализации
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Для смены пароля используйте reset-password"
        )
    except ValueError as e:
        error_msg = str(e)
        error_mapping = {
            "Не удалось определить пользователя": "❌ Не удалось определить пользователя"
        }

        detail = error_mapping.get(error_msg, f"❌ Ошибка смены пароля: {error_msg}")

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail
        )
    except Exception as e:
        print(f"❌ Ошибка смены пароля: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"❌ Внутренняя ошибка сервера при смене пароля"
        )


@router.get("/check-status/{email}")
async def check_registration_status(email: str, db: Session = Depends(get_db)):
    """Проверка статуса регистрации пользователя"""
    try:
        result = auth_service.check_registration_status(email, db)
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        print(f"❌ Ошибка проверки статуса: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"❌ Внутренняя ошибка сервера при проверки статуса"
        )


@router.get("/admin/teacher-requests")
async def get_teacher_requests(status: Optional[str] = None, db: Session = Depends(get_db)):
    """Получение списка заявок преподавателей (для администраторов)"""
    try:
        requests = auth_service.get_teacher_requests(status, db)
        return {"requests": requests, "count": len(requests)}
    except Exception as e:
        print(f"❌ Ошибка получения заявок преподавателей: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"❌ Внутренняя ошибка сервера при получении заявок"
        )


@router.post("/admin/approve-teacher/{request_id}")
async def approve_teacher_request(
        request_id: str,
        departments: Optional[list] = None,
        credentials: HTTPAuthorizationCredentials = Depends(security),
        db: Session = Depends(get_db)
):
    """Одобрение заявки преподавателя (только для администраторов)"""
    try:
        token = credentials.credentials
        admin_user = auth_service.get_current_user(token, db)

        if admin_user.get('role') != 'admin':
            raise HTTPException(status_code=403, detail="Требуются права администратора")

        result = auth_service.approve_teacher_request(
            request_id=request_id,
            admin_id=admin_user['id'],
            departments=departments,
            db=db
        )

        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"❌ Ошибка одобрения заявки: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"❌ Внутренняя ошибка сервера"
        )


@router.post("/admin/reject-teacher/{request_id}")
async def reject_teacher_request(
        request_id: str,
        reason: str = "",
        credentials: HTTPAuthorizationCredentials = Depends(security),
        db: Session = Depends(get_db)
):
    """Отклонение заявки преподавателя (только для администраторов)"""
    try:
        token = credentials.credentials
        admin_user = auth_service.get_current_user(token, db)

        if admin_user.get('role') != 'admin':
            raise HTTPException(status_code=403, detail="Требуются права администратора")

        result = auth_service.reject_teacher_request(
            request_id=request_id,
            admin_id=admin_user['id'],
            reason=reason,
            db=db
        )

        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"❌ Ошибка отклонения заявки: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"❌ Внутренняя ошибка сервера"
        )
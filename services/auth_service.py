import os
import uuid
import bcrypt
import jwt
from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from database.schema import User, TeacherRequest, RefreshToken
import secrets
import string


class AuthService:
    """Сервис аутентификации с собственной JWT реализацией"""

    def __init__(self):
        """Инициализация сервиса аутентификации"""
        self.secret_key = os.environ.get("JWT_SECRET_KEY", "your-super-secret-jwt-key-change-in-production")
        self.algorithm = "HS256"
        self.access_token_expire_minutes = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", 60 * 24))  # 24 часа
        self.refresh_token_expire_days = int(os.environ.get("REFRESH_TOKEN_EXPIRE_DAYS", 30))
        self.password_reset_token_expire_minutes = 30

    def _hash_password(self, password: str) -> str:
        """Хеширование пароля с bcrypt"""
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
        return hashed.decode('utf-8')

    def _verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Проверка пароля"""
        return bcrypt.checkpw(
            plain_password.encode('utf-8'),
            hashed_password.encode('utf-8')
        )

    def _generate_temporary_password(self, length: int = 10) -> str:
        """Генерация временного пароля"""
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
        return ''.join(secrets.choice(alphabet) for _ in range(length))

    def _create_access_token(self, data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
        """Создание JWT access токена"""
        to_encode = data.copy()

        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=self.access_token_expire_minutes)

        to_encode.update({
            "exp": expire,
            "iat": datetime.utcnow(),
            "type": "access",
            "jti": str(uuid.uuid4())  # Уникальный идентификатор токена
        })

        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        return encoded_jwt

    def _create_refresh_token(self, user_id: str, device_info: Dict[str, Any] = None) -> Tuple[str, str]:
        """Создание refresh токена и сохранение в БД"""
        refresh_token_id = str(uuid.uuid4())
        expires_at = datetime.utcnow() + timedelta(days=self.refresh_token_expire_days)

        token_data = {
            "sub": user_id,
            "jti": refresh_token_id,
            "exp": expires_at,
            "iat": datetime.utcnow(),
            "type": "refresh"
        }

        encoded_token = jwt.encode(token_data, self.secret_key, algorithm=self.algorithm)

        return encoded_token, refresh_token_id

    def _save_refresh_token(self, db: Session, user_id: str, token_id: str,
                            device_info: Dict[str, Any] = None, expires_at: datetime = None):
        """Сохранение refresh токена в базе данных"""
        if not expires_at:
            expires_at = datetime.utcnow() + timedelta(days=self.refresh_token_expire_days)

        refresh_token = RefreshToken(
            id=token_id,
            user_id=user_id,
            token_hash=self._hash_token(token_id),
            device_info=device_info or {},
            expires_at=expires_at,
            created_at=datetime.utcnow(),
            is_revoked=False
        )

        db.add(refresh_token)
        db.commit()

    def _hash_token(self, token: str) -> str:
        """Хеширование токена для безопасного хранения"""
        return bcrypt.hashpw(token.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    def _verify_token_hash(self, token: str, hashed_token: str) -> bool:
        """Проверка хеша токена"""
        return bcrypt.checkpw(token.encode('utf-8'), hashed_token.encode('utf-8'))

    def decode_token(self, token: str) -> Dict[str, Any]:
        """Декодирование JWT токена"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            return payload
        except jwt.ExpiredSignatureError:
            raise ValueError("Срок действия токена истек")
        except jwt.InvalidTokenError as e:
            raise ValueError(f"Недействительный токен: {str(e)}")

    def login_with_email_password(self, email: str, password: str, db: Session,
                                  device_info: Dict[str, Any] = None) -> Dict[str, Any]:
        """Вход по email и паролю"""
        try:
            print(f"🔐 Вход пользователя: {email}")

            # Ищем пользователя в базе данных
            user = db.query(User).filter(User.email == email).first()

            if not user:
                raise ValueError("Пользователь с таким email не найден")

            # Проверяем активность пользователя
            if not user.is_active:
                # Проверяем, есть ли заявка на регистрацию
                teacher_request = db.query(TeacherRequest).filter(
                    TeacherRequest.email == email
                ).first()

                if teacher_request:
                    if teacher_request.status == 'pending':
                        raise ValueError("Аккаунт ожидает активации администратором")
                    elif teacher_request.status == 'rejected':
                        raise ValueError("Ваша заявка была отклонена администратором")

                raise ValueError("Пользователь неактивен. Обратитесь к администратору.")

            # Проверяем пароль
            if not self._verify_password(password, user.password_hash):
                raise ValueError("Неверный пароль")

            # Обновляем время последнего входа
            user.last_login = datetime.utcnow()
            db.commit()

            # Создаем токены
            token_data = {
                "sub": user.id,
                "email": user.email,
                "role": user.role,
                "name": user.full_name,
                "permissions": self._get_user_permissions(user)
            }

            access_token = self._create_access_token(token_data)
            refresh_token, refresh_token_id = self._create_refresh_token(user.id, device_info)

            # Сохраняем refresh токен в БД
            self._save_refresh_token(db, user.id, refresh_token_id, device_info)

            # Подготавливаем данные пользователя
            user_data = {
                "id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "phone": user.phone,
                "role": user.role,
                "date_of_birth": user.date_of_birth,
                "max_students": user.max_students,
                "current_students_count": user.current_students_count,
                "assigned_departments": user.assigned_departments or [],
                "assigned_specialities": user.assigned_specialities or [],
                "is_active": user.is_active,
                "created_at": user.created_at,
                "last_login": user.last_login,
                "permissions": self._get_user_permissions(user)
            }

            response_data = {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": "bearer",
                "expires_in": self.access_token_expire_minutes * 60,  # в секундах
                "user": user_data,
                "message": "Вход выполнен успешно"
            }

            return response_data

        except ValueError as e:
            raise e
        except Exception as e:
            print(f"❌ Ошибка входа: {e}")
            raise ValueError(f"Ошибка входа: {str(e)}")

    def register(self, user_data: Dict[str, Any], db: Session,
                 device_info: Dict[str, Any] = None) -> Dict[str, Any]:
        """Регистрация нового пользователя"""
        try:
            email = user_data.get('email', '').strip().lower()
            password = user_data.get('password', '')
            full_name = user_data.get('full_name', '').strip()
            role = user_data.get('role', 'teacher')

            # Валидация
            if not email or '@' not in email:
                raise ValueError("Неверный формат email")

            if not password or len(password) < 6:
                raise ValueError("Пароль должен содержать минимум 6 символов")

            if not full_name or len(full_name) < 2:
                raise ValueError("Имя должно содержать минимум 2 символа")

            print(f"📝 Регистрация пользователя: {email}, роль: {role}")

            # Проверяем, существует ли пользователь
            existing_user = db.query(User).filter(User.email == email).first()
            if existing_user:
                raise ValueError("Пользователь с таким email уже существует")

            # Хешируем пароль
            password_hash = self._hash_password(password)

            # Создаем пользователя
            user = User(
                id=str(uuid.uuid4()),
                email=email,
                full_name=full_name,
                phone=user_data.get('phone', ''),
                role=role,
                date_of_birth=user_data.get('date_of_birth'),
                max_students=user_data.get('max_students', 20),
                current_students_count=0,
                assigned_departments=user_data.get('assigned_departments', []),
                assigned_specialities=user_data.get('assigned_specialities', []),
                password_hash=password_hash,
                is_active=False if role == 'teacher' else True,  # Преподавателей активирует админ
                experience=user_data.get('experience'),
                education=user_data.get('education'),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )

            db.add(user)
            db.commit()

            # Если это студент - создаем заявку (если нужно)
            if role == 'student':
                # TODO: Реализовать создание заявки студента
                pass

            # Автоматически логиним пользователя
            login_result = self.login_with_email_password(email, password, db, device_info)

            # Для преподавателей меняем сообщение
            if role == 'teacher':
                login_result['message'] = "Регистрация успешна. Ожидайте активации администратором."
            else:
                login_result['message'] = "Регистрация успешна. Аккаунт активирован."

            return login_result

        except ValueError as e:
            raise e
        except Exception as e:
            db.rollback()
            print(f"❌ Ошибка регистрации: {e}")
            raise ValueError(f"Ошибка регистрации: {str(e)}")

    def register_teacher_request(self, user_data: Dict[str, Any], db: Session) -> Dict[str, Any]:
        """Создание заявки на регистрацию преподавателя"""
        try:
            email = user_data.get('email', '').strip().lower()
            full_name = user_data.get('full_name', '').strip()

            # Валидация
            if not email or '@' not in email:
                raise ValueError("Неверный формат email")

            if not full_name or len(full_name) < 2:
                raise ValueError("Имя должно содержать минимум 2 символа")

            # Проверяем, не существует ли уже пользователь
            existing_user = db.query(User).filter(User.email == email).first()
            if existing_user:
                raise ValueError("Пользователь с таким email уже существует")

            # Проверяем, не существует ли уже заявка
            existing_request = db.query(TeacherRequest).filter(
                TeacherRequest.email == email
            ).first()

            if existing_request:
                status = existing_request.status
                if status == 'pending':
                    raise ValueError("Заявка уже отправлена и ожидает рассмотрения")
                elif status == 'approved':
                    raise ValueError("Заявка уже одобрена. Проверьте ваш email.")
                elif status == 'rejected':
                    raise ValueError("Заявка была отклонена. Обратитесь к администратору.")

            print(f"📝 Создание заявки на регистрацию преподавателя: {email}")

            # Создаем заявку
            request_id = str(uuid.uuid4())

            request = TeacherRequest(
                id=request_id,
                full_name=full_name,
                email=email,
                phone=user_data.get('phone', ''),
                max_students=user_data.get('max_students', 20),
                status='pending',
                requested_at=datetime.utcnow(),
                message=user_data.get('message', ''),
                assigned_departments=user_data.get('departments', []),
                experience=user_data.get('experience', ''),
                education=user_data.get('education', '')
            )

            db.add(request)
            db.commit()

            print(f"✅ Заявка создана: {request_id}")

            return {
                'message': '✅ Заявка на регистрацию отправлена!',
                'details': 'Ваша заявка отправлена администратору. Вы получите email с данными для входа после одобрения.',
                'request_id': request_id,
                'status': 'pending'
            }

        except ValueError as e:
            raise e
        except Exception as e:
            db.rollback()
            print(f"❌ Ошибка создания заявки: {e}")
            raise ValueError(f"Ошибка создания заявки: {str(e)}")

    def get_current_user(self, token: str, db: Session) -> Dict[str, Any]:
        """Получение текущего пользователя по JWT токену"""
        try:
            # Декодируем токен
            payload = self.decode_token(token)

            if payload.get('type') != 'access':
                raise ValueError("Неверный тип токена")

            user_id = payload.get('sub')
            if not user_id:
                raise ValueError("Неверный токен")

            # Проверяем, не отозван ли токен (по jti)
            token_jti = payload.get('jti')
            if token_jti and self._is_token_revoked(token_jti, db):
                raise ValueError("Токен был отозван")

            # Ищем пользователя в базе данных
            user = db.query(User).filter(User.id == user_id).first()

            if not user:
                raise ValueError("Пользователь не найден")

            # Проверяем активность
            if not user.is_active:
                raise ValueError("Пользователь неактивен")

            return self._user_to_dict(user)

        except Exception as e:
            raise ValueError(f"Ошибка получения пользователя: {str(e)}")

    def _is_token_revoked(self, jti: str, db: Session) -> bool:
        """Проверка, отозван ли токен"""
        # Проверяем в базе данных
        revoked_token = db.query(RefreshToken).filter(
            RefreshToken.id == jti,
            RefreshToken.is_revoked == True
        ).first()
        return revoked_token is not None

    def validate_token(self, token: str, db: Session) -> bool:
        """Проверка валидности токена"""
        try:
            self.get_current_user(token, db)
            return True
        except:
            return False

    def refresh_token(self, refresh_token: str, db: Session) -> Dict[str, Any]:
        """Обновление access токена (упрощенная версия для API)"""
        return self.refresh_tokens(refresh_token, db)

    def refresh_tokens(self, refresh_token: str, db: Session,
                       device_info: Dict[str, Any] = None) -> Dict[str, Any]:
        """Обновление access токена по refresh токену"""
        try:
            print("🔄 Обновление токенов...")

            # Декодируем refresh токен
            payload = self.decode_token(refresh_token)

            if payload.get('type') != 'refresh':
                raise ValueError("Неверный тип токена")

            user_id = payload.get('sub')
            token_jti = payload.get('jti')

            if not user_id or not token_jti:
                raise ValueError("Неверный токен")

            # Проверяем refresh токен в базе данных
            stored_token = db.query(RefreshToken).filter(
                RefreshToken.id == token_jti,
                RefreshToken.user_id == user_id,
                RefreshToken.is_revoked == False,
                RefreshToken.expires_at > datetime.utcnow()
            ).first()

            if not stored_token:
                raise ValueError("Refresh токен не найден или истек")

            # Получаем пользователя
            user = db.query(User).filter(User.id == user_id).first()
            if not user or not user.is_active:
                raise ValueError("Пользователь не найден или неактивен")

            # Создаем новые токены
            token_data = {
                "sub": user.id,
                "email": user.email,
                "role": user.role,
                "name": user.full_name,
                "permissions": self._get_user_permissions(user)
            }

            new_access_token = self._create_access_token(token_data)
            new_refresh_token, new_refresh_token_id = self._create_refresh_token(user.id, device_info)

            # Отзываем старый refresh токен
            stored_token.is_revoked = True
            stored_token.revoked_at = datetime.utcnow()

            # Сохраняем новый refresh токен
            self._save_refresh_token(db, user.id, new_refresh_token_id, device_info)

            db.commit()

            return {
                "access_token": new_access_token,
                "refresh_token": new_refresh_token,
                "token_type": "bearer",
                "expires_in": self.access_token_expire_minutes * 60,
                "user": self._user_to_dict(user),
                "message": "Токены успешно обновлены"
            }

        except Exception as e:
            raise ValueError(f"Ошибка обновления токенов: {str(e)}")

    def logout(self, token: str, db: Session) -> Dict[str, str]:
        """Выход пользователя (отзыв текущего refresh токена)"""
        try:
            # Получаем пользователя из токена
            user = self.get_current_user(token, db)
            user_id = user['id']

            # Отзываем все refresh токены пользователя
            return self.logout_all_devices(user_id, db)

        except Exception as e:
            raise ValueError(f"Ошибка выхода: {str(e)}")

    def logout_all_devices(self, user_id: str, db: Session) -> Dict[str, str]:
        """Выход со всех устройств (отзыв всех refresh токенов)"""
        try:
            # Отмечаем все refresh токены пользователя как отозванные
            db.query(RefreshToken).filter(
                RefreshToken.user_id == user_id,
                RefreshToken.is_revoked == False
            ).update({
                'is_revoked': True,
                'revoked_at': datetime.utcnow()
            })

            db.commit()

            return {
                'message': 'Выполнен выход со всех устройств'
            }

        except Exception as e:
            raise ValueError(f"Ошибка выхода со всех устройств: {str(e)}")

    def change_password(self, token: str, new_password: str, db: Session) -> Dict[str, str]:
        """Смена пароля текущего пользователя"""
        try:
            # Получаем текущего пользователя
            current_user = self.get_current_user(token, db)
            user_id = current_user.get('id')

            if not user_id:
                raise ValueError("Не удалось определить пользователя")

            # Получаем пользователя из БД
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                raise ValueError("Пользователь не найден")

            # Проверяем новый пароль
            if len(new_password) < 6:
                raise ValueError("Новый пароль должен содержать минимум 6 символов")

            # Хешируем новый пароль
            user.password_hash = self._hash_password(new_password)
            user.updated_at = datetime.utcnow()

            # Отзываем все refresh токены пользователя (выход со всех устройств)
            self.logout_all_devices(user_id, db)

            db.commit()

            return {
                'message': 'Пароль успешно изменен. Выполнен выход со всех устройств.'
            }

        except ValueError as e:
            raise e
        except Exception as e:
            db.rollback()
            raise ValueError(f"Ошибка смены пароля: {str(e)}")

    def reset_password(self, email: str, db: Session) -> Dict[str, str]:
        """Сброс пароля (упрощенная версия - возвращает токен)"""
        return self.reset_password_request(email, db)

    def reset_password_request(self, email: str, db: Session) -> Dict[str, str]:
        """Запрос на сброс пароля"""
        try:
            # Проверяем существование пользователя
            user = db.query(User).filter(User.email == email).first()

            if not user:
                raise ValueError("Пользователь с таким email не найден")

            # Создаем токен для сброса пароля
            reset_token_data = {
                "sub": user.id,
                "type": "password_reset",
                "exp": datetime.utcnow() + timedelta(minutes=self.password_reset_token_expire_minutes),
                "iat": datetime.utcnow()
            }

            reset_token = jwt.encode(reset_token_data, self.secret_key, algorithm=self.algorithm)

            # TODO: Отправить email с токеном сброса пароля
            # В реальном приложении здесь должна быть отправка email

            print(f"📧 Токен сброса пароля для {email}: {reset_token}")

            return {
                'message': 'Письмо для сброса пароля отправлено на email',
                'reset_token': reset_token  # В реальном приложении не возвращаем токен
            }

        except Exception as e:
            raise ValueError(f"Ошибка запроса сброса пароля: {str(e)}")

    def reset_password_with_token(self, reset_token: str, new_password: str, db: Session) -> Dict[str, str]:
        """Сброс пароля по токену"""
        try:
            # Декодируем токен
            try:
                payload = jwt.decode(reset_token, self.secret_key, algorithms=[self.algorithm])
            except jwt.ExpiredSignatureError:
                raise ValueError("Токен сброса пароля истек")
            except jwt.InvalidTokenError:
                raise ValueError("Недействительный токен сброса пароля")

            if payload.get('type') != 'password_reset':
                raise ValueError("Неверный тип токена")

            user_id = payload.get('sub')
            if not user_id:
                raise ValueError("Неверный токен")

            # Получаем пользователя
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                raise ValueError("Пользователь не найден")

            # Проверяем новый пароль
            if len(new_password) < 6:
                raise ValueError("Новый пароль должен содержать минимум 6 символов")

            # Хешируем новый пароль
            user.password_hash = self._hash_password(new_password)
            user.updated_at = datetime.utcnow()

            # Отзываем все refresh токены пользователя
            self.logout_all_devices(user_id, db)

            db.commit()

            return {
                'message': 'Пароль успешно сброшен. Выполнен выход со всех устройств.'
            }

        except ValueError as e:
            raise e
        except Exception as e:
            db.rollback()
            raise ValueError(f"Ошибка сброса пароля: {str(e)}")

    def approve_teacher_request(self, request_id: str, admin_id: str,
                                departments: List[str] = None, db: Session = None) -> Dict[str, Any]:
        """Одобрение заявки преподавателя"""
        try:
            # Получаем заявку
            request = db.query(TeacherRequest).filter(
                TeacherRequest.id == request_id,
                TeacherRequest.status == 'pending'
            ).first()

            if not request:
                raise ValueError("Заявка не найдена или уже обработана")

            # Генерируем временный пароль
            temp_password = self._generate_temporary_password()

            # Создаем пользователя
            user = User(
                id=str(uuid.uuid4()),
                email=request.email,
                full_name=request.full_name,
                phone=request.phone,
                role='teacher',
                max_students=request.max_students,
                current_students_count=0,
                assigned_departments=departments or request.assigned_departments or [],
                assigned_specialities=[],
                password_hash=self._hash_password(temp_password),
                is_active=True,
                experience=request.experience,
                education=request.education,
                approved_by=admin_id,
                approved_at=datetime.utcnow(),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )

            db.add(user)

            # Обновляем статус заявки
            request.status = 'approved'
            request.approved_by = admin_id
            request.approved_at = datetime.utcnow()
            request.user_id = user.id

            if departments:
                request.assigned_departments = departments

            db.commit()

            # TODO: Отправить email с данными для входа
            print(f"📧 Данные для входа преподавателя {request.email}: пароль - {temp_password}")

            return {
                'user_id': user.id,
                'temp_password': temp_password,
                'email': request.email,
                'message': 'Преподаватель успешно зарегистрирован. Данные для входа отправлены на email.'
            }

        except Exception as e:
            db.rollback()
            raise ValueError(f"Ошибка одобрения заявки: {str(e)}")

    def reject_teacher_request(self, request_id: str, admin_id: str, reason: str = "", db: Session = None) -> Dict[
        str, Any]:
        """Отклонение заявки преподавателя"""
        try:
            request = db.query(TeacherRequest).filter(
                TeacherRequest.id == request_id,
                TeacherRequest.status == 'pending'
            ).first()

            if not request:
                raise ValueError("Заявка не найдена или уже обработана")

            # Обновляем статус заявки
            request.status = 'rejected'
            request.rejected_by = admin_id
            request.rejected_at = datetime.utcnow()
            request.rejection_reason = reason

            db.commit()

            # TODO: Отправить email с отказом
            print(f"📧 Отказ в регистрации преподавателя {request.email}: {reason}")

            return {
                'message': 'Заявка отклонена',
                'email': request.email
            }

        except Exception as e:
            db.rollback()
            raise ValueError(f"Ошибка отклонения заявки: {str(e)}")

    def get_teacher_requests(self, status: str = None, db: Session = None) -> List[Dict[str, Any]]:
        """Получение списка заявок преподавателей"""
        try:
            query = db.query(TeacherRequest)

            if status:
                query = query.filter(TeacherRequest.status == status)

            requests = query.order_by(TeacherRequest.requested_at.desc()).all()

            return [self._teacher_request_to_dict(req) for req in requests]
        except Exception as e:
            print(f"❌ Ошибка получения заявок преподавателей: {e}")
            return []

    def check_registration_status(self, email: str, db: Session) -> Dict[str, Any]:
        """Проверка статуса регистрации пользователя"""
        try:
            # Проверяем существующего пользователя
            user = db.query(User).filter(User.email == email).first()

            if user:
                return {
                    'status': 'registered',
                    'is_active': user.is_active,
                    'role': user.role,
                    'user_id': user.id
                }

            # Проверяем заявки преподавателя
            teacher_request = db.query(TeacherRequest).filter(
                TeacherRequest.email == email
            ).first()

            if teacher_request:
                return {
                    'status': 'requested',
                    'request_type': 'teacher',
                    'request_status': teacher_request.status,
                    'request_id': teacher_request.id
                }

            return {
                'status': 'not_found',
                'message': 'Пользователь не найден'
            }

        except Exception as e:
            raise ValueError(f"Ошибка проверки статуса: {str(e)}")

    def _get_user_permissions(self, user: User) -> Dict[str, bool]:
        """Получение прав пользователя"""
        permissions = {
            'can_view_students': False,
            'can_edit_students': False,
            'can_create_students': False,
            'can_delete_students': False,
            'can_view_communications': False,
            'can_create_communications': False,
            'can_edit_communications': False,
            'can_delete_communications': False,
            'can_manage_teachers': False,
            'can_manage_departments': False,
            'can_manage_system': False
        }

        if user.role == 'admin':
            # Администратор имеет все права
            for key in permissions:
                permissions[key] = True
        elif user.role == 'teacher':
            # Преподаватель имеет ограниченные права
            permissions.update({
                'can_view_students': True,
                'can_create_students': True,
                'can_edit_students': True,
                'can_view_communications': True,
                'can_create_communications': True,
                'can_edit_communications': True
            })
        elif user.role == 'student':
            # Студент имеет минимальные права
            permissions.update({
                'can_view_students': True,  # только своих данных
                'can_view_communications': True  # только свои коммуникации
            })

        return permissions

    def _user_to_dict(self, user: User) -> Dict[str, Any]:
        """Конвертация пользователя в словарь"""
        if not user:
            return {}

        return {
            'id': user.id,
            'email': user.email,
            'full_name': user.full_name,
            'phone': user.phone,
            'role': user.role,
            'date_of_birth': user.date_of_birth,
            'max_students': user.max_students,
            'current_students_count': user.current_students_count,
            'assigned_departments': user.assigned_departments or [],
            'assigned_specialities': user.assigned_specialities or [],
            'experience': user.experience,
            'education': user.education,
            'is_active': user.is_active,
            'approved_by': user.approved_by,
            'approved_at': user.approved_at,
            'created_at': user.created_at,
            'updated_at': user.updated_at,
            'last_login': user.last_login,
            'permissions': self._get_user_permissions(user)
        }

    def _teacher_request_to_dict(self, request: TeacherRequest) -> Dict[str, Any]:
        """Конвертация заявки преподавателя в словарь"""
        if not request:
            return {}

        return {
            'id': request.id,
            'full_name': request.full_name,
            'email': request.email,
            'phone': request.phone,
            'max_students': request.max_students,
            'status': request.status,
            'requested_at': request.requested_at,
            'message': request.message,
            'assigned_departments': request.assigned_departments or [],
            'experience': request.experience,
            'education': request.education,
            'approved_by': request.approved_by,
            'approved_at': request.approved_at,
            'rejected_by': request.rejected_by,
            'rejected_at': request.rejected_at,
            'rejection_reason': request.rejection_reason,
            'user_id': request.user_id
        }
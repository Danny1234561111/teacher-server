# services/auth_service.py
import os
import uuid
import bcrypt
import jwt
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from fastapi import Request, Response

from database.schema import User


class AuthService:
    def __init__(self):
        self.secret_key = os.environ.get("JWT_SECRET_KEY", "your-secret-key")
        self.algorithm = "HS256"
        self.token_expire_minutes = 60 * 24

    def _hash_password(self, password: str) -> str:
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

    def _verify_password(self, plain_password: str, hashed_password: str) -> bool:
        return bcrypt.checkpw(
            plain_password.encode('utf-8'),
            hashed_password.encode('utf-8')
        )

    def _create_token(self, user_id: str) -> str:
        expire = datetime.utcnow() + timedelta(minutes=self.token_expire_minutes)
        payload = {
            "sub": user_id,
            "exp": expire,
            "iat": datetime.utcnow()
        }
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    def decode_token(self, token: str) -> Dict[str, Any]:
        try:
            return jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
        except jwt.ExpiredSignatureError:
            raise ValueError("Токен истек")
        except jwt.InvalidTokenError:
            raise ValueError("Недействительный токен")

    def login_for_mobile(self, email: str, password: str, db: Session) -> Dict[str, Any]:
        user = db.query(User).filter(User.email == email).first()

        if not user:
            raise ValueError("Пользователь не найден")

        if not user.is_active:
            raise ValueError("Пользователь неактивен")

        if not self._verify_password(password, user.hashed_password):
            raise ValueError("Неверный пароль")

        user.last_login = datetime.utcnow()
        db.commit()

        token = self._create_token(user.id)

        return {
            "access_token": token,
            "token_type": "bearer",
            "user": self._user_to_dict(user),
            "message": "Вход выполнен успешно"
        }

    def login_for_web(self, email: str, password: str, response: Response, db: Session) -> Dict[str, Any]:
        user = db.query(User).filter(User.email == email).first()

        if not user:
            raise ValueError("Пользователь не найден")

        if not user.is_active:
            raise ValueError("Пользователь неактивен")

        if not self._verify_password(password, user.hashed_password):
            raise ValueError("Неверный пароль")

        user.last_login = datetime.utcnow()
        db.commit()

        token = self._create_token(user.id)

        response.set_cookie(
            key="access_token",
            value=token,
            httponly=True,
            secure=False,
            samesite="lax",
            max_age=self.token_expire_minutes * 60,
            path="/"
        )

        return {
            "user": self._user_to_dict(user),
            "message": "Вход выполнен успешно"
        }

    def get_user_by_token(self, token: str, db: Session) -> Dict[str, Any]:
        payload = self.decode_token(token)
        user_id = payload.get('sub')

        if not user_id:
            raise ValueError("Недействительный токен")

        user = db.query(User).filter(User.id == user_id).first()

        if not user:
            raise ValueError("Пользователь не найден")

        if not user.is_active:
            raise ValueError("Пользователь неактивен")

        return self._user_to_dict(user)

    def get_current_user_web(self, request: Request, db: Session) -> Dict[str, Any]:
        token = request.cookies.get("access_token")

        if not token:
            raise ValueError("Токен не найден")

        return self.get_user_by_token(token, db)

    def logout_for_web(self, response: Response) -> Dict[str, Any]:
        response.delete_cookie("access_token", path="/")
        return {"message": "Выход выполнен успешно"}

    def _user_to_dict(self, user: User) -> Dict[str, Any]:
        return {
            'id': user.id,
            'email': user.email,
            'full_name': user.full_name,
            'role': user.role,
            'is_active': user.is_active
        }
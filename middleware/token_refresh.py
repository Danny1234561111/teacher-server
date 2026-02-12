# middleware/token_refresh.py
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from datetime import datetime, timedelta
import jwt
import os
from typing import Optional


class TokenRefreshMiddleware:
    def __init__(self, app):
        self.app = app
        self.secret_key = os.environ.get("JWT_SECRET_KEY")
        self.algorithm = "HS256"
        self.access_token_expire_minutes = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", 1440))
        self.refresh_threshold_minutes = 5  # Обновлять токен если осталось меньше 5 минут

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        request = Request(scope, receive)

        # Пропускаем эндпоинты аутентификации
        if request.url.path.startswith("/api/auth/") and request.url.path not in ["/api/auth/refresh"]:
            return await self.app(scope, receive, send)

        # Проверяем наличие токена
        auth_header = request.headers.get("authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return await self.app(scope, receive, send)

        token = auth_header.split(" ")[1]

        try:
            # Декодируем токен без проверки срока действия
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
                options={"verify_exp": False}
            )

            # Проверяем тип токена
            if payload.get("type") != "access":
                return await self.app(scope, receive, send)

            # Проверяем время истечения
            exp_timestamp = payload.get("exp")
            if exp_timestamp:
                exp_time = datetime.fromtimestamp(exp_timestamp)
                time_until_expiry = exp_time - datetime.utcnow()

                # Если токен истекает скоро, обновляем его
                if time_until_expiry < timedelta(minutes=self.refresh_threshold_minutes):
                    # Здесь можно добавить логику автоматического обновления
                    # Например, вернуть новый токен в заголовках ответа
                    pass

        except jwt.InvalidTokenError:
            pass

        return await self.app(scope, receive, send)
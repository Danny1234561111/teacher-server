# services/websocket_manager.py
from fastapi import WebSocket
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)


class WebSocketManager:
    """Сервис для управления WebSocket соединениями"""

    def __init__(self):
        self._mobile_connections: Dict[int, WebSocket] = {}

    async def connect(self, user_id: int, websocket: WebSocket):
        """Подключить мобильное устройство"""
        await websocket.accept()
        self._mobile_connections[user_id] = websocket
        logger.info(f"📱 Мобильное устройство подключено: user_id={user_id}")

    def disconnect(self, user_id: int):
        """Отключить мобильное устройство"""
        if user_id in self._mobile_connections:
            del self._mobile_connections[user_id]
            logger.info(f"📱 Мобильное устройство отключено: user_id={user_id}")

    async def send_command(self, user_id: int, command: dict) -> bool:
        if user_id in self._mobile_connections:
            try:
                await self._mobile_connections[user_id].send_json(command)
                logger.debug(f"📤 Команда отправлена user_id={user_id}: {command.get('type')}")
                return True
            except Exception as e:
                logger.error(f"Ошибка отправки: {e}")
                self.disconnect(user_id)
        return False

    def is_connected(self, user_id: int) -> bool:
        """Проверить, подключено ли мобильное устройство"""
        return user_id in self._mobile_connections


# Глобальный экземпляр
websocket_manager = WebSocketManager()


async def handle_mobile_websocket(websocket: WebSocket, user_id: int):
    """Обработчик WebSocket соединения для мобильного устройства"""
    await websocket_manager.connect(user_id, websocket)

    try:
        # Отправляем подтверждение
        await websocket.send_json({
            "type": "connected",
            "message": "Мобильное устройство подключено",
            "user_id": user_id
        })

        # Держим соединение открытым
        while True:
            try:
                data = await websocket.receive_json()

                # Обработка heartbeat
                if data.get('type') == 'heartbeat':
                    await websocket.send_json({"type": "pong"})
                else:
                    logger.info(f"Получено от мобильного: {data}")

            except ValueError:  # JSON decode error
                continue

    except Exception as e:
        logger.error(f"Ошибка WebSocket: {e}")
        websocket_manager.disconnect(user_id)
# services/websocket_manager.py
from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict
import logging
import asyncio

logger = logging.getLogger(__name__)


class WebSocketManager:
    """Сервис для управления WebSocket соединениями"""

    def __init__(self):
        self._mobile_connections: Dict[int, WebSocket] = {}
        self._lock = asyncio.Lock()

    async def connect(self, user_id: int, websocket: WebSocket):
        """Подключить мобильное устройство (НЕ принимаем соединение здесь)"""
        async with self._lock:
            self._mobile_connections[user_id] = websocket
            logger.info(f"📱 Мобильное устройство подключено: user_id={user_id}, всего: {len(self._mobile_connections)}")

    def disconnect(self, user_id: int):
        """Отключить мобильное устройство"""
        if user_id in self._mobile_connections:
            del self._mobile_connections[user_id]
            logger.info(
                f"📱 Мобильное устройство отключено: user_id={user_id}, осталось: {len(self._mobile_connections)}")

    async def send_command(self, user_id: int, command: dict) -> bool:
        """Отправить команду мобильному устройству"""
        if user_id in self._mobile_connections:
            try:
                await self._mobile_connections[user_id].send_json(command)
                logger.debug(f"📤 Команда отправлена user_id={user_id}: {command.get('type')}")
                return True
            except Exception as e:
                logger.error(f"Ошибка отправки команды user_id={user_id}: {e}")
                self.disconnect(user_id)
        return False

    def is_connected(self, user_id: int) -> bool:
        """Проверить, подключено ли мобильное устройство"""
        return user_id in self._mobile_connections

    def get_connection_count(self) -> int:
        """Получить количество активных подключений"""
        return len(self._mobile_connections)


# Глобальный экземпляр
websocket_manager = WebSocketManager()


async def handle_mobile_websocket(websocket: WebSocket, user_id: int):
    """Обработчик WebSocket соединения для мобильного устройства"""
    # Принимаем соединение ЗДЕСЬ (только один раз!)
    await websocket.accept()
    logger.info(f"🔌 WebSocket соединение принято для user_id={user_id}")

    # Подключаем к менеджеру
    await websocket_manager.connect(user_id, websocket)

    try:
        # Отправляем подтверждение
        await websocket.send_json({
            "type": "connected",
            "message": "Мобильное устройство подключено",
            "user_id": user_id,
            "timestamp": __import__('datetime').datetime.now().isoformat()
        })
        logger.info(f"✅ Отправлено подтверждение подключения user_id={user_id}")

        # Держим соединение открытым и слушаем сообщения
        while True:
            try:
                # Ждем сообщения от клиента
                data = await websocket.receive_json()

                # Обработка heartbeat
                if data.get('type') == 'heartbeat':
                    await websocket.send_json(
                        {"type": "pong", "timestamp": __import__('datetime').datetime.now().isoformat()})
                    logger.debug(f"💓 Heartbeat от user_id={user_id}")
                else:
                    logger.info(f"📨 Получено сообщение от user_id={user_id}: {data}")

                    # Эхо-ответ для тестирования
                    await websocket.send_json({
                        "type": "echo",
                        "received": data,
                        "timestamp": __import__('datetime').datetime.now().isoformat()
                    })

            except WebSocketDisconnect:
                logger.info(f"🔌 WebSocket разрыв соединения user_id={user_id}")
                break
            except ValueError as e:
                # Ошибка JSON декодирования
                logger.warning(f"⚠️ Ошибка JSON от user_id={user_id}: {e}")
                continue
            except Exception as e:
                logger.error(f"❌ Ошибка при получении сообщения от user_id={user_id}: {e}")
                continue

    except WebSocketDisconnect:
        logger.info(f"🔌 WebSocket отключение user_id={user_id}")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка в WebSocket для user_id={user_id}: {e}", exc_info=True)
    finally:
        # Отключаем пользователя
        websocket_manager.disconnect(user_id)
        logger.info(f"🏁 Завершена обработка WebSocket для user_id={user_id}")
# main.py
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
import os

# Импортируем роутеры из папки routers (не api.routes)
from routers import auth, admin, students, user_contact, excel_import
from database.database import init_db, get_db
from services.scheduler import scheduler
from services.auth_service import AuthService
from services.websocket_manager import websocket_manager, handle_mobile_websocket

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

auth_service = AuthService()

ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://localhost:5173,http://localhost:8080,http://158.160.67.3:3000,http://158.160.67.3:5173"
).split(",")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения"""
    print("=" * 50)
    print("🚀 ЗАПУСК ПРИЛОЖЕНИЯ")
    print("=" * 50)

    # Инициализация базы данных
    print("📦 Инициализация базы данных...")
    if init_db():
        print("✅ База данных успешно инициализирована")

        # Запускаем планировщик парсера
        print("⏰ Запуск планировщика парсера...")
        scheduler.start()

        # Запускаем первый парсинг сразу
        print("🚀 Запуск первого парсинга...")
        scheduler.run_now()
    else:
        print("❌ Не удалось инициализировать базу данных")

    print("=" * 50)
    yield

    # Остановка при завершении
    print("🛑 Остановка планировщика...")
    scheduler.stop()
    print("🛑 Остановка приложения...")


app = FastAPI(
    title="University Admissions API",
    description="API для приемной комиссии университета",
    version="5.0.0",
    lifespan=lifespan
)

# CORS - настройки для поддержки cookies
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключаем HTTP роутеры
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(admin.router, prefix="/api/admin", tags=["Administration"])
app.include_router(students.router, prefix="/api/students", tags=["Students"])
app.include_router(user_contact.router, prefix="/api/user/contact", tags=["User Contact"])
app.include_router(excel_import.router, prefix="/api/excel-import", tags=["Excel Import"])


# ===== WEBSOCKET ЭНДПОИНТ =====
@app.websocket("/ws/mobile/{token}")
async def websocket_mobile_endpoint(websocket: WebSocket, token: str):
    """WebSocket для мобильного приложения"""
    db = None
    user_id = None

    logger.info(f"🔌 Новое WebSocket соединение")

    try:
        # Создаем сессию БД
        db = next(get_db())

        # Декодируем токен
        try:
            payload = auth_service.decode_token(token)
            user_id = payload.get('sub')

            if not user_id:
                logger.error(f"❌ WebSocket: В токене нет поля 'sub'")
                await websocket.close(code=1008, reason="Invalid token: missing user id")
                return

            logger.info(f"✅ WebSocket: Токен декодирован, user_id={user_id}")

        except ValueError as e:
            error_msg = str(e)
            logger.error(f"❌ WebSocket: Ошибка декодирования токена: {error_msg}")
            await websocket.close(code=1008, reason=f"Invalid token: {error_msg}")
            return
        except Exception as e:
            logger.error(f"❌ WebSocket: Неожиданная ошибка при декодировании: {e}", exc_info=True)
            await websocket.close(code=1011, reason="Internal error")
            return

        # Проверяем пользователя в БД
        try:
            user_data = auth_service.get_user_by_token(token, db)
            if not user_data:
                logger.error(f"❌ WebSocket: Пользователь с id={user_id} не найден")
                await websocket.close(code=1008, reason="User not found")
                return

            if not user_data.get('is_active', False):
                logger.error(f"❌ WebSocket: Пользователь {user_id} неактивен")
                await websocket.close(code=1008, reason="User is inactive")
                return

            logger.info(f"✅ WebSocket: Пользователь {user_id} найден и активен")

        except ValueError as e:
            logger.error(f"❌ WebSocket: Ошибка получения пользователя: {e}")
            await websocket.close(code=1008, reason=str(e))
            return
        except Exception as e:
            logger.error(f"❌ WebSocket: Неожиданная ошибка при получении пользователя: {e}", exc_info=True)
            await websocket.close(code=1011, reason="Internal error")
            return

        # Передаем управление обработчику WebSocket
        logger.info(f"🚀 Передача управления обработчику WebSocket для user_id={user_id}")
        await handle_mobile_websocket(websocket, user_id)

    except WebSocketDisconnect:
        logger.info(f"🔌 WebSocket разрыв соединения")
    except Exception as e:
        logger.error(f"💥 Критическая ошибка в WebSocket эндпоинте: {e}", exc_info=True)
        try:
            await websocket.close(code=1011, reason="Internal server error")
        except:
            pass
    finally:
        if db:
            db.close()


@app.get("/")
async def root():
    return {
        "message": "University Admissions API",
        "version": "5.0.0",
        "status": "running",
        "database": "initialized",
        "cors": {
            "allowed_origins": ALLOWED_ORIGINS,
            "credentials_supported": True
        },
        "websocket": {
            "mobile": "ws://localhost:8000/ws/mobile/{token}"
        },
        "parser": {
            "status": "running" if scheduler.is_running else "stopped",
            "interval_hours": scheduler.interval_hours,
            "last_run": scheduler.last_run.isoformat() if scheduler.last_run else None,
            "last_stats": scheduler.last_stats
        },
        "active_connections": websocket_manager.get_connection_count() if hasattr(websocket_manager, 'get_connection_count') else 0
    }


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "database": "connected",
        "parser": "running" if scheduler.is_running else "stopped",
        "websocket_connections": websocket_manager.get_connection_count() if hasattr(websocket_manager, 'get_connection_count') else 0,
        "version": "5.0.0"
    }


@app.post("/api/parser/run")
async def run_parser_manually():
    scheduler.run_now()
    return {"status": "running", "message": "Парсер запущен"}
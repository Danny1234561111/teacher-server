# main.py
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

# Импортируем роутеры
from routers import auth, admin, students, user_contact
from database.database import init_db
from services.scheduler import scheduler
from services.auth_service import AuthService
from services.websocket_manager import handle_mobile_websocket
from routers import excel_import

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

auth_service = AuthService()


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

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://158.160.67.3:3000",
        "http://localhost:3000",
        "http://158.160.67.3",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["Content-Type", "Authorization", "Cookie", "Set-Cookie", "Accept"],
    expose_headers=["Set-Cookie"],
)

# Подключаем HTTP роутеры
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(admin.router, prefix="/api/admin", tags=["Administration"])
app.include_router(students.router, prefix="/api/students", tags=["Students"])
app.include_router(user_contact.router, prefix="/api/user/contact", tags=["User Contact"])
app.include_router(excel_import.router,prefix="/api/excel-import",)


# ===== WEBSOCKET ЭНДПОИНТ =====
@app.websocket("/ws/mobile/{token}")
async def websocket_mobile_endpoint(websocket: WebSocket, token: str):
    """WebSocket для мобильного приложения"""
    from database.database import get_db
    db = next(get_db())

    try:
        user_data = auth_service.get_user_by_token(token, db)
        if not user_data:
            await websocket.close(code=1008, reason="Invalid token")
            return

        user_id = user_data['id']
        await handle_mobile_websocket(websocket, user_id)

    except Exception as e:
        logger.error(f"Ошибка WebSocket: {e}")
        await websocket.close(code=1011, reason="Internal error")
    finally:
        db.close()


@app.get("/")
async def root():
    return {
        "message": "University Admissions API",
        "version": "5.0.0",
        "status": "running",
        "database": "initialized",
        "websocket": {
            "mobile": "ws://localhost:8000/ws/mobile/{token}"
        },
        "parser": {
            "status": "running" if scheduler.is_running else "stopped",
            "interval_hours": scheduler.interval_hours,
            "last_run": scheduler.last_run.isoformat() if scheduler.last_run else None,
            "last_stats": scheduler.last_stats
        }
    }


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "database": "connected",
        "parser": "running" if scheduler.is_running else "stopped",
        "version": "5.0.0"
    }


@app.post("/api/parser/run")
async def run_parser_manually():
    scheduler.run_now()
    return {"status": "running", "message": "Парсер запущен"}
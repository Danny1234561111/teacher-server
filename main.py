from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
# Импортируем роутеры
from routers import auth, admin,students,user_contact
from database.database import init_db
from services.scheduler import scheduler

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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

# CORS - настройки
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключаем роутеры
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(admin.router, prefix="/api/admin", tags=["Administration"])
app.include_router(students.router, prefix="/api/students", tags=["Administration"])
app.include_router(user_contact.router)


@app.get("/")
async def root():
    return {
        "message": "University Admissions API",
        "version": "5.0.0",
        "status": "running",
        "database": "initialized",
        "parser": {
            "status": "running" if scheduler.is_running else "stopped",
            "interval_hours": scheduler.interval_hours,
            "last_run": scheduler.last_run.isoformat() if scheduler.last_run else None,
            "last_stats": scheduler.last_stats
        }
    }


@app.get("/health")
async def health_check():
    """Простая проверка здоровья"""
    return {
        "status": "healthy",
        "database": "connected",
        "parser": "running" if scheduler.is_running else "stopped",
        "version": "5.0.0"
    }


@app.post("/api/parser/run")
async def run_parser_manually():
    """Ручной запуск парсера (только для админов)"""
    scheduler.run_now()
    return {"status": "running", "message": "Парсер запущен"}
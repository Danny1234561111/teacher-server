# main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from routers import students, auth, admin
from database.database import init_db, get_db
from services.database_service import DatabaseService


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения"""
    # Инициализация базы данных при запуске
    print("🚀 Инициализация базы данных...")
    init_db()

    # Создаем администратора по умолчанию если нет пользователей
    db = next(get_db())
    from services.auth_service import AuthService
    from database.schema import User

    try:
        admin_exists = db.query(User).filter(User.role == 'admin').first()
        if not admin_exists:
            auth_service = AuthService()
            # Создаем администратора по умолчанию
            import uuid
            from datetime import datetime

            admin_user = User(
                id=str(uuid.uuid4()),
                email="admin@university.com",
                full_name="Администратор Системы",
                role='admin',
                password_hash=auth_service._hash_password("admin123"),
                is_active=True,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )

            db.add(admin_user)
            db.commit()
            print("✅ Создан администратор по умолчанию: admin@university.com / admin123")
    except Exception as e:
        print(f"⚠️ Ошибка создания администратора: {e}")

    print("✅ База данных инициализирована")
    yield
    # Очистка при завершении
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
app.include_router(students.router, prefix="/api/students", tags=["Students"])
app.include_router(admin.router, prefix="/api/admin", tags=["Administration"])


@app.get("/")
async def root():
    return {
        "message": "University Admissions API",
        "version": "5.0.0",
        "features": [
            "PostgreSQL база данных",
            "Собственная JWT аутентификация",
            "Двухэтапная регистрация преподавателей",
            "Управление направлениями и специальностями",
            "Распределение студентов по факультетам",
            "История коммуникаций",
            "Административная панель",
            "Refresh токены с автоматическим обновлением"
        ],
        "database": "PostgreSQL",
        "authentication": "JWT + bcrypt"
    }


@app.get("/health")
async def health_check():
    """Проверка здоровья приложения"""
    try:
        db_service = DatabaseService()
        db_status = db_service.check_connection()

        return {
            "status": "healthy",
            "database": "connected" if db_status else "disconnected",
            "authentication": "JWT",
            "version": "5.0.0"
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "database": "error",
            "error": str(e)
        }
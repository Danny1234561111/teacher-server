# database/database.py
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import sessionmaker, Session
import os
from typing import Generator
from dotenv import load_dotenv
import socket
from urllib.parse import urlparse

from .schema import Base

# Загрузка переменных окружения
load_dotenv()

print("=" * 50)
print("🔍 НАЧАЛО ИНИЦИАЛИЗАЦИИ БАЗЫ ДАННЫХ")
print("=" * 50)

# Получение DATABASE_URL из .env
DATABASE_URL = os.getenv("DATABASE_URL")
print(f"📦 DATABASE_URL из .env (сырой): '{DATABASE_URL}'")

# Если DATABASE_URL не найден или пустой, создаем из отдельных переменных
if not DATABASE_URL:
    print("⚠️  DATABASE_URL не найден, создаем из отдельных переменных")

    DB_USER = os.getenv("POSTGRES_USER", "postgres")
    DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "password")
    DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
    DB_PORT = os.getenv("POSTGRES_PORT", "5432")
    DB_NAME = os.getenv("POSTGRES_DB", "university_admissions")

    print(f"   POSTGRES_USER: {DB_USER}")
    print(f"   POSTGRES_PASSWORD: {'*' * len(DB_PASSWORD) if DB_PASSWORD else 'не указан'}")
    print(f"   POSTGRES_HOST: {DB_HOST}")
    print(f"   POSTGRES_PORT: {DB_PORT}")
    print(f"   POSTGRES_DB: {DB_NAME}")

    if DB_HOST == "localhost":
        try:
            DB_HOST = socket.gethostbyname('localhost')
            print(f"   🔄 localhost преобразован в IPv4: {DB_HOST}")
        except:
            DB_HOST = "127.0.0.1"
            print(f"   🔄 Используем 127.0.0.1 вместо localhost")

    DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    print(f"   📝 Создан DATABASE_URL: {DATABASE_URL.replace(DB_PASSWORD, '***')}")

# Очищаем URL от возможных кавычек и пробелов
original_url = DATABASE_URL
DATABASE_URL = DATABASE_URL.strip().strip('"').strip("'").strip()

if original_url != DATABASE_URL:
    print(f"   🧹 Очищен URL от лишних символов")
    print(f"   Было: '{original_url}'")
    print(f"   Стало: '{DATABASE_URL}'")

# Разбираем URL для отладки
try:
    parsed_url = urlparse(DATABASE_URL)
    print(f"   🔍 Разбор URL:")
    print(f"      Схема: {parsed_url.scheme}")
    print(f"      Хост: {parsed_url.hostname}")
    print(f"      Порт: {parsed_url.port}")
    print(f"      База: {parsed_url.path.lstrip('/')}")
    print(f"      Пользователь: {parsed_url.username}")
except Exception as e:
    print(f"   ❌ Ошибка разбора URL: {e}")

print(
    f"📦 Финальный DATABASE_URL: {DATABASE_URL.replace(DB_PASSWORD, '***') if 'DB_PASSWORD' in locals() else DATABASE_URL}")

# Создание движка SQLAlchemy
try:
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_recycle=300,
        pool_size=10,
        max_overflow=20,
        echo_pool=True,
        connect_args={
            "connect_timeout": 10,
            "application_name": "university_admissions_app",
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 10,
            "keepalives_count": 5,
        }
    )
    print("✅ Движок SQLAlchemy создан успешно")
except Exception as e:
    print(f"❌ Ошибка создания движка SQLAlchemy: {e}")
    raise

# Создание фабрики сессий
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False
)

print(f"✅ Фабрика сессий создана")
print("=" * 50)


def init_db():
    """Инициализация базы данных - создание таблиц"""
    print("🔄 Начало создания таблиц...")

    try:
        Base.metadata.create_all(bind=engine)
        print("✅ Таблицы базы данных созданы успешно")

        with engine.connect() as conn:
            result = conn.execute(text("SELECT version()"))
            version = result.fetchone()[0]
            print(f"✅ Подключено к PostgreSQL: {version}")

            result = conn.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
            """))
            tables = [row[0] for row in result.fetchall()]
            print(f"📊 Таблицы в базе: {tables}")

    except Exception as e:
        print(f"❌ Ошибка при создании таблиц: {e}")
        return False

    return True


def ensure_schema_up_to_date():
    """Проверяет и добавляет отсутствующие колонки в таблицы users и students"""
    print("🔄 Проверка схемы базы данных...")

    try:
        inspector = inspect(engine)

        # ========== ОБНОВЛЕНИЕ ТАБЛИЦЫ users ==========
        if 'users' in inspector.get_table_names():
            existing_columns = [col['name'] for col in inspector.get_columns('users')]

            if 'active_contact' not in existing_columns:
                print("➕ Добавление поля active_contact в users...")
                with engine.connect() as conn:
                    conn.execute(text("ALTER TABLE users ADD COLUMN active_contact VARCHAR(500) NULL"))
                    conn.commit()
                print("✅ Поле active_contact добавлено")
            else:
                print("✅ Поле active_contact уже существует")

            if 'active_contact_type' not in existing_columns:
                print("➕ Добавление поля active_contact_type в users...")
                with engine.connect() as conn:
                    conn.execute(text("ALTER TABLE users ADD COLUMN active_contact_type VARCHAR(50) NULL"))
                    conn.commit()
                print("✅ Поле active_contact_type добавлено")
            else:
                print("✅ Поле active_contact_type уже существует")

            if 'active_contact_updated_at' not in existing_columns:
                print("➕ Добавление поля active_contact_updated_at в users...")
                with engine.connect() as conn:
                    conn.execute(text("ALTER TABLE users ADD COLUMN active_contact_updated_at TIMESTAMP NULL"))
                    conn.commit()
                print("✅ Поле active_contact_updated_at добавлено")
            else:
                print("✅ Поле active_contact_updated_at уже существует")

        # ========== ОБНОВЛЕНИЕ ТАБЛИЦЫ students ==========
        if 'students' in inspector.get_table_names():
            existing_columns = [col['name'] for col in inspector.get_columns('students')]

            # Добавляем поле meeting_status (был на сборе/не был)
            if 'meeting_status' not in existing_columns:
                print("➕ Добавление поля meeting_status в students...")
                with engine.connect() as conn:
                    conn.execute(text("""
                        ALTER TABLE students 
                        ADD COLUMN meeting_status VARCHAR(50) DEFAULT 'not_met'
                    """))
                    conn.commit()
                print("✅ Поле meeting_status добавлено")
            else:
                print("✅ Поле meeting_status уже существует")

            # Добавляем поле call_status (дозвонились/нет)
            if 'call_status' not in existing_columns:
                print("➕ Добавление поля call_status в students...")
                with engine.connect() as conn:
                    conn.execute(text("""
                        ALTER TABLE students 
                        ADD COLUMN call_status VARCHAR(50) DEFAULT 'not_reached'
                    """))
                    conn.commit()
                print("✅ Поле call_status добавлено")
            else:
                print("✅ Поле call_status уже существует")

            # Добавляем поле decision_status (решил/думает)
            if 'decision_status' not in existing_columns:
                print("➕ Добавление поля decision_status в students...")
                with engine.connect() as conn:
                    conn.execute(text("""
                        ALTER TABLE students 
                        ADD COLUMN decision_status VARCHAR(50) DEFAULT 'thinking'
                    """))
                    conn.commit()
                print("✅ Поле decision_status добавлено")
            else:
                print("✅ Поле decision_status уже существует")

            # Добавляем поле documents_status (статус документов)
            if 'documents_status' not in existing_columns:
                print("➕ Добавление поля documents_status в students...")
                with engine.connect() as conn:
                    conn.execute(text("""
                        ALTER TABLE students 
                        ADD COLUMN documents_status VARCHAR(50) DEFAULT 'not_submitted'
                    """))
                    conn.commit()
                print("✅ Поле documents_status добавлено")
            else:
                print("✅ Поле documents_status уже существует")

            # Обновляем существующие записи значениями по умолчанию
            print("🔄 Обновление существующих студентов значениями по умолчанию...")
            with engine.connect() as conn:
                conn.execute(text("""
                    UPDATE students 
                    SET meeting_status = 'not_met' 
                    WHERE meeting_status IS NULL
                """))
                conn.execute(text("""
                    UPDATE students 
                    SET call_status = 'not_reached' 
                    WHERE call_status IS NULL
                """))
                conn.execute(text("""
                    UPDATE students 
                    SET decision_status = 'thinking' 
                    WHERE decision_status IS NULL
                """))
                conn.execute(text("""
                    UPDATE students 
                    SET documents_status = 'not_submitted' 
                    WHERE documents_status IS NULL
                """))
                conn.commit()
            print("✅ Существующие студенты обновлены")

    except Exception as e:
        print(f"⚠️ Ошибка при обновлении схемы: {e}")
        import traceback
        traceback.print_exc()


def get_db() -> Generator[Session, None, None]:
    """Зависимость для получения сессии базы данных"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_connection() -> bool:
    """Проверка соединения с базой данных"""
    print("🔌 Проверка соединения с БД...")

    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            data = result.fetchone()
            if data and data[0] == 1:
                print("✅ Подключение к БД успешно")
                return True
            else:
                print("❌ Неожиданный результат от БД")
                return False
    except Exception as e:
        print(f"❌ Ошибка подключения к базе данных: {e}")

        if "password authentication failed" in str(e):
            print("   🔐 ОШИБКА АУТЕНТИФИКАЦИИ:")
            print("   Проверьте пароль в .env файле")
        elif "Connection refused" in str(e):
            print("   🔌 ОШИБКА ПОДКЛЮЧЕНИЯ:")
            print("   Проверьте что PostgreSQL запущен")
            print("   Команда: docker ps | grep postgres")
        elif "could not translate host name" in str(e):
            print("   🌐 ОШИБКА ХОСТА:")
            print("   Проверьте POSTGRES_HOST в .env")

        return False


# Автоматическая проверка при импорте
if __name__ != "__main__":
    print("🔧 АВТОМАТИЧЕСКАЯ ПРОВЕРКА ПРИ ИМПОРТЕ")
    connection_ok = check_connection()

    if connection_ok:
        print("🚀 Попытка автоматической инициализации таблиц...")
        try:
            init_db()
            print("✅ Автоматическая инициализация завершена")
            ensure_schema_up_to_date()
        except Exception as e:
            print(f"⚠️ Ошибка при автоматической инициализации: {e}")
    else:
        print("⚠️ Невозможно подключиться к БД, пропускаем инициализацию")

    print("=" * 50)

if __name__ == "__main__":
    print("🧪 ТЕСТОВЫЙ РЕЖИМ database.py")
    print("=" * 50)

    if check_connection():
        print("\n✅ Тест подключения пройден успешно!")
        response = input("\nСоздать таблицы? (y/n): ")
        if response.lower() == 'y':
            init_db()
            ensure_schema_up_to_date()
    else:
        print("\n❌ Тест подключения не пройден")

    print("\n" + "=" * 50)
    print("Тест завершен")
# database/database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.orm import DeclarativeBase
import os
from typing import Generator
from dotenv import load_dotenv
import socket
from urllib.parse import urlparse

# Импортируем Base здесь чтобы избежать циклических импортов
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
    DB_HOST = os.getenv("POSTGRES_HOST", "postgres")
    DB_PORT = os.getenv("POSTGRES_PORT", "5432")
    DB_NAME = os.getenv("POSTGRES_DB", "university_admissions")

    print(f"   POSTGRES_USER: {DB_USER}")
    print(f"   POSTGRES_PASSWORD: {'*' * len(DB_PASSWORD) if DB_PASSWORD else 'не указан'}")
    print(f"   POSTGRES_HOST: {DB_HOST}")
    print(f"   POSTGRES_PORT: {DB_PORT}")
    print(f"   POSTGRES_DB: {DB_NAME}")

    # Преобразование localhost для Windows
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

print(f"📦 Финальный DATABASE_URL: {DATABASE_URL.replace('password', '***')}")

# Создание движка SQLAlchemy с подробными настройками
try:
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,  # Проверка соединения перед использованием
        pool_recycle=300,  # Пересоздание соединений каждые 300 секунд
        pool_size=10,  # Максимум 10 соединений в пуле
        max_overflow=20,  # Дополнительно 20 соединений при нагрузке
        echo=True,  # Включаем логирование SQL (отладка)
        echo_pool=True,  # Логирование пула соединений
        # Параметры для Windows и лучшей совместимости
        connect_args={
            "connect_timeout": 10,  # Таймаут подключения 10 секунд
            "application_name": "university_admissions_app",
            "keepalives": 1,  # Включить keepalive
            "keepalives_idle": 30,  # 30 секунд бездействия
            "keepalives_interval": 10,  # Интервал проверки 10 секунд
            "keepalives_count": 5,  # Количество попыток
        }
    )
    print("✅ Движок SQLAlchemy создан успешно")
except Exception as e:
    print(f"❌ Ошибка создания движка SQLAlchemy: {e}")
    print("   Проверьте формат DATABASE_URL")
    raise

# Создание фабрики сессий
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False  # Не истекать после коммита (лучше для FastAPI)
)

print(f"✅ Фабрика сессий создана")
print("=" * 50)


def init_db():
    """Инициализация базы данных - создание таблиц"""
    print("🔄 Начало создания таблиц...")

    try:
        from sqlalchemy import text
        # Создаем все таблицы из моделей
        Base.metadata.create_all(bind=engine)
        print("✅ Таблицы базы данных созданы успешно")

        # Проверяем соединение и версию PostgreSQL
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version()"))
            version = result.fetchone()[0]
            print(f"✅ Подключено к PostgreSQL: {version}")

            # Проверяем существующие таблицы
            result = conn.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
            """)
            tables = [row[0] for row in result.fetchall()]
            print(f"📊 Таблицы в базе: {tables}")

    except Exception as e:
        print(f"❌ Ошибка при создании таблиц: {e}")
        print("\n🔍 ДИАГНОСТИКА:")
        print(f"   DATABASE_URL: {DATABASE_URL.replace('password', '***')}")

        # Проверяем доступность хоста и порта
        import subprocess
        try:
            # Проверяем доступность порта
            result = subprocess.run(
                ["netstat", "-an", "|", "findstr", ":5432"],
                capture_output=True,
                text=True,
                shell=True
            )
            if "5432" in result.stdout:
                print("   ✅ Порт 5432 прослушивается")
            else:
                print("   ❌ Порт 5432 не прослушивается")
        except:
            pass

        print("⚠️  Продолжаем без инициализации БД...")
        return False

    return True


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
            # Простой запрос для проверки
            result =conn.execute(text("SELECT 1"))
            data = result.fetchone()
            if data and data[0] == 1:
                print("✅ Подключение к БД успешно")
                return True
            else:
                print("❌ Неожиданный результат от БД")
                return False
    except Exception as e:
        print(f"❌ Ошибка подключения к базе данных: {e}")

        # Подробная информация об ошибке
        if "password authentication failed" in str(e):
            print("   🔐 ОШИБКА АУТЕНТИФИКАЦИИ:")
            print("   Проверьте пароль в .env файле")
            print("   Должен совпадать с POSTGRES_PASSWORD в docker-compose.yml")
        elif "Connection refused" in str(e):
            print("   🔌 ОШИБКА ПОДКЛЮЧЕНИЯ:")
            print("   Проверьте что PostgreSQL запущен")
            print("   Команда: docker ps | grep postgres")
        elif "could not translate host name" in str(e):
            print("   🌐 ОШИБКА ХОСТА:")
            print("   Проверьте POSTGRES_HOST в .env")
            print("   Для Windows попробуйте: localhost, 127.0.0.1 или host.docker.internal")

        print(f"   URL: {DATABASE_URL.replace('password', '***')}")
        return False


# Автоматическая проверка при импорте (только для отладки)
if __name__ != "__main__":
    print("🔧 АВТОМАТИЧЕСКАЯ ПРОВЕРКА ПРИ ИМПОРТЕ")
    connection_ok = check_connection()

    if connection_ok:
        print("🚀 Попытка автоматической инициализации таблиц...")
        try:
            init_db()
            print("✅ Автоматическая инициализация завершена")
        except Exception as e:
            print(f"⚠️  Ошибка при автоматической инициализации: {e}")
            print("⚠️  Продолжаем без инициализации БД...")
    else:
        print("⚠️  Невозможно подключиться к БД, пропускаем инициализацию")

    print("=" * 50)

# Тестовая функция для запуска из командной строки
if __name__ == "__main__":
    print("🧪 ТЕСТОВЫЙ РЕЖИМ database.py")
    print("=" * 50)

    if check_connection():
        print("\n✅ Тест подключения пройден успешно!")

        # Спросим пользователя, создавать ли таблицы
        response = input("\nСоздать таблицы? (y/n): ")
        if response.lower() == 'y':
            init_db()
    else:
        print("\n❌ Тест подключения не пройден")

    print("\n" + "=" * 50)
    print("Тест завершен")# database/database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.orm import DeclarativeBase
import os
from typing import Generator
from dotenv import load_dotenv
import socket
from urllib.parse import urlparse

# Импортируем Base здесь чтобы избежать циклических импортов
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

    # Преобразование localhost для Windows
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

print(f"📦 Финальный DATABASE_URL: {DATABASE_URL.replace('password', '***')}")

# Создание движка SQLAlchemy с подробными настройками
try:
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,        # Проверка соединения перед использованием
        pool_recycle=300,          # Пересоздание соединений каждые 300 секунд
        pool_size=10,              # Максимум 10 соединений в пуле
        max_overflow=20,           # Дополнительно 20 соединений при нагрузке
        echo=True,                 # Включаем логирование SQL (отладка)
        echo_pool=True,            # Логирование пула соединений
        # Параметры для Windows и лучшей совместимости
        connect_args={
            "connect_timeout": 10,        # Таймаут подключения 10 секунд
            "application_name": "university_admissions_app",
            "keepalives": 1,              # Включить keepalive
            "keepalives_idle": 30,        # 30 секунд бездействия
            "keepalives_interval": 10,    # Интервал проверки 10 секунд
            "keepalives_count": 5,        # Количество попыток
        }
    )
    print("✅ Движок SQLAlchemy создан успешно")
except Exception as e:
    print(f"❌ Ошибка создания движка SQLAlchemy: {e}")
    print("   Проверьте формат DATABASE_URL")
    raise

# Создание фабрики сессий
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False  # Не истекать после коммита (лучше для FastAPI)
)

print(f"✅ Фабрика сессий создана")
print("=" * 50)


def init_db():
    """Инициализация базы данных - создание таблиц"""
    print("🔄 Начало создания таблиц...")

    try:
        # Создаем все таблицы из моделей
        Base.metadata.create_all(bind=engine)
        print("✅ Таблицы базы данных созданы успешно")

        # Проверяем соединение и версию PostgreSQL
        with engine.connect() as conn:
            result = conn.execute("SELECT version()")
            version = result.fetchone()[0]
            print(f"✅ Подключено к PostgreSQL: {version}")

            # Проверяем существующие таблицы
            result = conn.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
            """)
            tables = [row[0] for row in result.fetchall()]
            print(f"📊 Таблицы в базе: {tables}")

    except Exception as e:
        print(f"❌ Ошибка при создании таблиц: {e}")
        print("\n🔍 ДИАГНОСТИКА:")
        print(f"   DATABASE_URL: {DATABASE_URL.replace('password', '***')}")

        # Проверяем доступность хоста и порта
        import subprocess
        try:
            # Проверяем доступность порта
            result = subprocess.run(
                ["netstat", "-an", "|", "findstr", ":5432"],
                capture_output=True,
                text=True,
                shell=True
            )
            if "5432" in result.stdout:
                print("   ✅ Порт 5432 прослушивается")
            else:
                print("   ❌ Порт 5432 не прослушивается")
        except:
            pass

        print("⚠️  Продолжаем без инициализации БД...")
        return False

    return True


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
            # Простой запрос для проверки
            result = conn.execute("SELECT 1 as test")
            data = result.fetchone()
            if data and data[0] == 1:
                print("✅ Подключение к БД успешно")
                return True
            else:
                print("❌ Неожиданный результат от БД")
                return False
    except Exception as e:
        print(f"❌ Ошибка подключения к базе данных: {e}")

        # Подробная информация об ошибке
        if "password authentication failed" in str(e):
            print("   🔐 ОШИБКА АУТЕНТИФИКАЦИИ:")
            print("   Проверьте пароль в .env файле")
            print("   Должен совпадать с POSTGRES_PASSWORD в docker-compose.yml")
        elif "Connection refused" in str(e):
            print("   🔌 ОШИБКА ПОДКЛЮЧЕНИЯ:")
            print("   Проверьте что PostgreSQL запущен")
            print("   Команда: docker ps | grep postgres")
        elif "could not translate host name" in str(e):
            print("   🌐 ОШИБКА ХОСТА:")
            print("   Проверьте POSTGRES_HOST в .env")
            print("   Для Windows попробуйте: localhost, 127.0.0.1 или host.docker.internal")

        print(f"   URL: {DATABASE_URL.replace('password', '***')}")
        return False


# Автоматическая проверка при импорте (только для отладки)
if __name__ != "__main__":
    print("🔧 АВТОМАТИЧЕСКАЯ ПРОВЕРКА ПРИ ИМПОРТЕ")
    connection_ok = check_connection()

    if connection_ok:
        print("🚀 Попытка автоматической инициализации таблиц...")
        try:
            init_db()
            print("✅ Автоматическая инициализация завершена")
        except Exception as e:
            print(f"⚠️  Ошибка при автоматической инициализации: {e}")
            print("⚠️  Продолжаем без инициализации БД...")
    else:
        print("⚠️  Невозможно подключиться к БД, пропускаем инициализацию")

    print("=" * 50)


# Тестовая функция для запуска из командной строки
if __name__ == "__main__":
    print("🧪 ТЕСТОВЫЙ РЕЖИМ database.py")
    print("=" * 50)

    if check_connection():
        print("\n✅ Тест подключения пройден успешно!")

        # Спросим пользователя, создавать ли таблицы
        response = input("\nСоздать таблицы? (y/n): ")
        if response.lower() == 'y':
            init_db()
    else:
        print("\n❌ Тест подключения не пройден")

    print("\n" + "=" * 50)
    print("Тест завершен")
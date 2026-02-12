# check_env.py
import os
from dotenv import load_dotenv

load_dotenv()

print("Проверка переменных окружения:")
print("=" * 50)

# Все переменные
env_vars = [
    "POSTGRES_HOST",
    "POSTGRES_PORT",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DB",
    "DATABASE_URL",
    "JWT_SECRET_KEY"
]

for var in env_vars:
    value = os.getenv(var)
    if value:
        # Маскируем пароль
        if "PASSWORD" in var or "SECRET" in var:
            masked = value[:3] + "*" * (len(value) - 3) if len(value) > 3 else "***"
            print(f"{var}: {masked}")
        else:
            print(f"{var}: {value}")
    else:
        print(f"{var}: ❌ НЕ НАЙДЕН")

print("\n" + "=" * 50)
print("Проверка длины DATABASE_URL:")
url = os.getenv("DATABASE_URL")
if url:
    print(f"Длина: {len(url)} символов")
    print(f"Начинается с: '{url[:30]}...'")

    # Проверьте есть ли кавычки
    if '"' in url or "'" in url:
        print("⚠️  ВНИМАНИЕ: В URL есть кавычки!")
    if url.startswith('"') or url.startswith("'"):
        print("⚠️  ВНИМАНИЕ: URL начинается с кавычки!")
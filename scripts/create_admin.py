# scripts/create_admin.py
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.database import SessionLocal
from database.schema import User
from services.auth_service import AuthService
import uuid
from datetime import datetime


def create_admin_user(email: str, password: str, full_name: str = "Администратор"):
    """Создание администратора через скрипт"""
    db = SessionLocal()

    try:
        # Проверяем, существует ли уже администратор
        existing_admin = db.query(User).filter(User.role == 'admin').first()
        if existing_admin:
            print(f"⚠️ Администратор уже существует: {existing_admin.email}")
            return

        auth_service = AuthService()

        admin_user = User(
            id=str(uuid.uuid4()),
            email=email,
            full_name=full_name,
            role='admin',
            password_hash=auth_service._hash_password(password),
            is_active=True,
            max_students=1000,
            current_students_count=0,
            assigned_departments=['all'],
            assigned_specialities=['all'],
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        db.add(admin_user)
        db.commit()

        print(f"✅ Администратор создан:")
        print(f"   Email: {email}")
        print(f"   Пароль: {password}")
        print(f"   Имя: {full_name}")

    except Exception as e:
        print(f"❌ Ошибка создания администратора: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    # Использование по умолчанию
    create_admin_user(
        email="admin@university.com",
        password="admin123",
        full_name="Администратор Системы"
    )
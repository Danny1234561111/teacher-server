# scripts/create_admin.py
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.database import SessionLocal
from database.schema import User
from services.auth_service import AuthService


def create_admin_user(email: str = "admin@university.com",
                      password: str = "admin123",
                      full_name: str = "Администратор Системы этой"):
    """Создание администратора"""
    db = SessionLocal()
    auth_service = AuthService()

    try:
        # Проверяем, существует ли пользователь с таким email
        existing_user = db.query(User).filter(User.email == email).first()
        if existing_user:
            print(f"⚠️ Пользователь {email} уже существует")
            print(f"   ID: {existing_user.id}")
            print(f"   Роль: {existing_user.role}")
            return

        # Создаем администратора - НЕ УКАЗЫВАЕМ ID!
        admin_user = User(
            email=email,
            full_name=full_name,
            role="ADMIN",
            hashed_password=auth_service._hash_password(password),
            is_active=True
        )

        db.add(admin_user)
        db.commit()

        print(f"✅ Администратор создан:")
        print(f"   Email: {email}")
        print(f"   Пароль: {password}")
        print(f"   Имя: {full_name}")
        print(f"   ID: {admin_user.id} (сгенерирован автоматически)")

    except Exception as e:
        print(f"❌ Ошибка создания администратора: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Создание администратора')
    parser.add_argument('--email', default='admin@university.com', help='Email администратора')
    parser.add_argument('--password', default='admin123', help='Пароль администратора')
    parser.add_argument('--name', default='Администратор Системы этой', help='Имя администратора')

    args = parser.parse_args()
    create_admin_user(args.email, args.password, args.name)
# scripts/create_initial_data.py
import sys
import os
import uuid
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.database import SessionLocal
from database.schema import (
    User, Department, Speciality, Profile, Student,
    UserRole, StudentStatus, ApplicationStatus, ContactStatus,
    StudyLevel, StudyForm, StudyBasis
)
from services.auth_service import AuthService


def create_initial_department(db):
    """Создание направления (факультета)"""
    existing = db.query(Department).filter(Department.code == "09.03.03").first()
    if existing:
        print(f"⚠️ Направление уже существует: {existing.name} (ID: {existing.id})")
        return existing

    department = Department(
        code="09.03.03",
        name="Информатика и вычислительная техника",
        faculty="Факультет бизнес-коммуникаций и информатики"
    )
    db.add(department)
    db.flush()
    print(f"✅ Создано направление: {department.name} (ID: {department.id})")
    return department


def create_initial_speciality(db, department_id):
    """Создание специальности"""
    existing = db.query(Speciality).filter(
        Speciality.code == "09.03.03",
        Speciality.department_id == department_id
    ).first()
    if existing:
        print(f"⚠️ Специальность уже существует: {existing.name} (ID: {existing.id})")
        return existing

    speciality = Speciality(
        code="09.03.03",
        name="Прикладная информатика",
        department_id=department_id
    )
    db.add(speciality)
    db.flush()
    print(f"✅ Создана специальность: {speciality.name} (ID: {speciality.id})")
    return speciality


def create_initial_profile(db, speciality_id):
    """Создание профиля"""
    existing = db.query(Profile).filter(
        Profile.name == "Разработка программного обеспечения",
        Profile.speciality_id == speciality_id
    ).first()
    if existing:
        print(f"⚠️ Профиль уже существует: {existing.name} (ID: {existing.id})")
        return existing

    profile = Profile(
        name="Разработка программного обеспечения",
        code="09.03.03-01",
        speciality_id=speciality_id,
        study_level=StudyLevel.BACHELOR,
        study_form=StudyForm.FULL_TIME,
        study_basis=StudyBasis.BUDGET,
        budget_places=30,
        paid_places=20
    )
    db.add(profile)
    db.flush()
    print(f"✅ Создан профиль: {profile.name} (ID: {profile.id})")
    return profile


def create_initial_user(db):
    """Создание первого преподавателя"""
    auth_service = AuthService()
    email = "teacher@university.com"

    existing = db.query(User).filter(User.email == email).first()
    if existing:
        print(f"⚠️ Пользователь {email} уже существует (ID: {existing.id})")
        return existing

    user = User(
        email=email,
        full_name="Иванов Иван Иванович",
        phone="+7 (999) 123-45-67",
        role=UserRole.TEACHER,
        hashed_password=auth_service._hash_password("teacher123"),
        is_active=True,
        assigned_departments=[1],  # ID направления
        assigned_specialities=[1],  # ID специальности
        assigned_profiles=[1]  # ID профиля
    )
    db.add(user)
    db.flush()
    print(f"✅ Создан преподаватель: {user.full_name} (ID: {user.id})")
    return user


def create_test_students(db):
    """Создание тестовых студентов для парсинга"""
    auth_service = AuthService()
    students_data = [
        {
            "russian_student_id": 4335892,
            "full_name": "Пробный абитуриент 1",
            "phone": "89842740339"
        },
        {
            "russian_student_id": 4667059,
            "full_name": "Пробный абитуриент 2",
            "phone": "89842740339"
        },
        {
            "russian_student_id": 4291132,
            "full_name": "Пробный абитуриент 3",
            "phone": "89842740339"
        }
    ]

    created_count = 0
    for data in students_data:
        existing = db.query(Student).filter(
            Student.russian_student_id == data["russian_student_id"]
        ).first()

        if existing:
            print(f"⚠️ Студент с ID {data['russian_student_id']} уже существует")
            continue

        student = Student(
            russian_student_id=data["russian_student_id"],
            full_name=data["full_name"],
            phone=data["phone"],
            kurator_id=1,  # ID преподавателя
            status=StudentStatus.ACTIVE.name,
            application_status=ApplicationStatus.PENDING.name,
            contact_status=ContactStatus.NEW.name,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.add(student)
        created_count += 1

    db.flush()
    print(f"✅ Создано студентов: {created_count}")
    return created_count


def create_initial_data():
    """Главная функция создания всех начальных данных"""
    db = SessionLocal()

    try:
        print("=" * 60)
        print("🚀 СОЗДАНИЕ НАЧАЛЬНЫХ ДАННЫХ")
        print("=" * 60)

        # 1. Создаем направление
        department = create_initial_department(db)
        if not department:
            print("❌ Не удалось создать направление")
            return

        # 2. Создаем специальность
        speciality = create_initial_speciality(db, department.id)
        if not speciality:
            print("❌ Не удалось создать специальность")
            return

        # 3. Создаем профиль
        profile = create_initial_profile(db, speciality.id)
        if not profile:
            print("❌ Не удалось создать профиль")
            return

        # 4. Создаем преподавателя
        user = create_initial_user(db)
        if not user:
            print("❌ Не удалось создать преподавателя")
            return

        # 5. Создаем тестовых студентов
        create_test_students(db)

        # Сохраняем все изменения
        db.commit()

        print("\n" + "=" * 60)
        print("✅ ВСЕ НАЧАЛЬНЫЕ ДАННЫЕ УСПЕШНО СОЗДАНЫ")
        print("=" * 60)
        print("\n📊 ИТОГИ:")
        print(f"   Направление: Информатика и вычислительная техника (ID: {department.id})")
        print(f"   Специальность: Прикладная информатика (ID: {speciality.id})")
        print(f"   Профиль: Разработка программного обеспечения (ID: {profile.id})")
        print(f"   Преподаватель: Иванов Иван Иванович (teacher@university.com / teacher123)")
        print(f"   Тестовые студенты: 3 шт.")

    except Exception as e:
        print(f"❌ Ошибка создания данных: {e}")
        db.rollback()
    finally:
        db.close()


def create_single_student(russian_id: int, full_name: str, phone: str = ""):
    """Создание одного студента по ID (для добавления вручную)"""
    db = SessionLocal()

    try:
        existing = db.query(Student).filter(
            Student.russian_student_id == russian_id
        ).first()

        if existing:
            print(f"⚠️ Студент с ID {russian_id} уже существует")
            return

        student = Student(
            russian_student_id=russian_id,
            full_name=full_name,
            phone=phone,
            kurator_id=1,
            status=StudentStatus.ACTIVE.name,
            application_status=ApplicationStatus.PENDING.name,
            contact_status=ContactStatus.NEW.name,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        db.add(student)
        db.commit()
        print(f"✅ Студент создан: {full_name} (ID: {russian_id})")

    except Exception as e:
        print(f"❌ Ошибка создания студента: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Создание начальных данных')
    parser.add_argument('--only-student', action='store_true',
                        help='Создать только одного студента')
    parser.add_argument('--russian-id', type=int,
                        help='Российский ID студента')
    parser.add_argument('--name', type=str,
                        help='ФИО студента')
    parser.add_argument('--phone', type=str, default="",
                        help='Телефон студента')

    args = parser.parse_args()

    if args.only_student:
        if not args.russian_id or not args.name:
            print("❌ Для создания студента укажите --russian-id и --name")
        else:
            create_single_student(args.russian_id, args.name, args.phone)
    else:
        create_initial_data()
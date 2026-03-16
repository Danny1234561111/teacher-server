# services/admin_service.py
import uuid
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from database.schema import User, Department, Speciality, Profile
from services.auth_service import AuthService


class AdminService:
    """Сервис для административных операций (упрощенная версия)"""

    def __init__(self):
        self.auth_service = AuthService()

    # ===== УПРАВЛЕНИЕ ПОЛЬЗОВАТЕЛЯМИ =====

    def get_all_users(self, db: Session) -> List[Dict[str, Any]]:
        """Получение списка всех пользователей"""
        users = db.query(User).all()
        return [self._user_to_dict(u) for u in users]

    def create_user(self, user_data: Dict[str, Any], db: Session) -> Dict[str, Any]:
        """Создание нового пользователя"""
        # Проверяем, существует ли пользователь с таким email
        existing = db.query(User).filter(User.email == user_data['email']).first()
        if existing:
            raise ValueError("Пользователь с таким email уже существует")

        # Создаем пользователя (без max_students)
        new_user = User(
            id=str(uuid.uuid4()),
            email=user_data['email'],
            full_name=user_data['full_name'],
            phone=user_data.get('phone'),
            role=user_data['role'],
            hashed_password=self.auth_service._hash_password(user_data['password']),
            is_active=True
        )

        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        return self._user_to_dict(new_user)

    def delete_user(self, user_id: int, db: Session) -> bool:
        """Удаление пользователя"""
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return False

        db.delete(user)
        db.commit()
        return True

    # ===== УПРАВЛЕНИЕ ФАКУЛЬТЕТАМИ (DEPARTMENTS) =====

    def get_all_departments(self, db: Session) -> List[Dict[str, Any]]:
        """Получение всех факультетов"""
        departments = db.query(Department).all()
        return [self._department_to_dict(d) for d in departments]

    def create_department(self, department_data: Dict[str, Any], db: Session) -> Dict[str, Any]:
        """Создание факультета"""
        # Проверяем, существует ли факультет с таким кодом
        existing = db.query(Department).filter(Department.code == department_data['code']).first()
        if existing:
            raise ValueError("Факультет с таким кодом уже существует")

        department = Department(
            code=department_data['code'],
            name=department_data['name'],
            faculty=department_data['faculty']
        )

        db.add(department)
        db.commit()
        db.refresh(department)

        return self._department_to_dict(department)

    def delete_department(self, department_id: int, db: Session) -> bool:
        """Удаление факультета"""
        department = db.query(Department).filter(Department.id == department_id).first()
        if not department:
            return False

        db.delete(department)
        db.commit()
        return True

    # ===== УПРАВЛЕНИЕ СПЕЦИАЛЬНОСТЯМИ (SPECIALITIES) =====

    def get_all_specialities(self, db: Session) -> List[Dict[str, Any]]:
        """Получение всех специальностей"""
        specialities = db.query(Speciality).all()
        return [self._speciality_to_dict(s) for s in specialities]

    def create_speciality(self, speciality_data: Dict[str, Any], db: Session) -> Dict[str, Any]:
        """Создание специальности"""
        # Проверяем существование факультета
        department = db.query(Department).filter(Department.id == speciality_data['department_id']).first()
        if not department:
            raise ValueError("Указанный факультет не существует")

        # Проверяем уникальность кода
        existing = db.query(Speciality).filter(Speciality.code == speciality_data['code']).first()
        if existing:
            raise ValueError("Специальность с таким кодом уже существует")

        speciality = Speciality(
            code=speciality_data['code'],
            name=speciality_data['name'],
            department_id=speciality_data['department_id']
        )

        db.add(speciality)
        db.commit()
        db.refresh(speciality)

        return self._speciality_to_dict(speciality)

    def delete_speciality(self, speciality_id: int, db: Session) -> bool:
        """Удаление специальности"""
        speciality = db.query(Speciality).filter(Speciality.id == speciality_id).first()
        if not speciality:
            return False

        db.delete(speciality)
        db.commit()
        return True

    # ===== УПРАВЛЕНИЕ ПРОФИЛЯМИ (PROFILES) =====

    def get_all_profiles(self, db: Session) -> List[Dict[str, Any]]:
        """Получение всех профилей"""
        profiles = db.query(Profile).all()
        return [self._profile_to_dict(p) for p in profiles]

    def create_profile(self, profile_data: Dict[str, Any], db: Session) -> Dict[str, Any]:
        """Создание профиля"""
        # Проверяем существование специальности
        speciality = db.query(Speciality).filter(Speciality.id == profile_data['speciality_id']).first()
        if not speciality:
            raise ValueError("Указанная специальность не существует")

        profile = Profile(
            name=profile_data['name'],
            speciality_id=profile_data['speciality_id'],
            code=profile_data.get('code'),
            budget_places=profile_data.get('budget_places'),
            paid_places=profile_data.get('paid_places')
        )

        db.add(profile)
        db.commit()
        db.refresh(profile)

        return self._profile_to_dict(profile)

    def delete_profile(self, profile_id: int, db: Session) -> bool:
        """Удаление профиля"""
        profile = db.query(Profile).filter(Profile.id == profile_id).first()
        if not profile:
            return False

        db.delete(profile)
        db.commit()
        return True

    # ===== СТАТИСТИКА =====

    def get_system_stats(self, db: Session) -> Dict[str, Any]:
        """Получение статистики системы"""
        total_users = db.query(User).count()
        total_admins = db.query(User).filter(User.role == 'admin').count()
        total_teachers = db.query(User).filter(User.role == 'teacher').count()
        total_students_db = db.query(User).filter(User.role == 'student').count()

        from database.schema import Student
        total_students = db.query(Student).count()
        total_departments = db.query(Department).count()
        total_specialities = db.query(Speciality).count()
        total_profiles = db.query(Profile).count()

        return {
            "users": {
                "total": total_users,
                "admins": total_admins,
                "teachers": total_teachers,
                "students_accounts": total_students_db
            },
            "students": {
                "total_in_system": total_students
            },
            "education": {
                "departments": total_departments,
                "specialities": total_specialities,
                "profiles": total_profiles
            }
        }

    # ===== ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ =====

    def _user_to_dict(self, user: User) -> Dict[str, Any]:
        """Конвертация пользователя в словарь"""
        if not user:
            return None
        return {
            'id': user.id,
            'email': user.email,
            'full_name': user.full_name,
            'phone': user.phone,
            'role': user.role.value if hasattr(user.role, 'value') else user.role,
            'is_active': user.is_active
            # УБРАНО: 'max_students' - этого поля нет в модели User
        }

    def _department_to_dict(self, department: Department) -> Dict[str, Any]:
        """Конвертация факультета в словарь"""
        if not department:
            return None
        return {
            'id': department.id,
            'code': department.code,
            'name': department.name,
            'faculty': department.faculty
        }

    def _speciality_to_dict(self, speciality: Speciality) -> Dict[str, Any]:
        """Конвертация специальности в словарь"""
        if not speciality:
            return None
        return {
            'id': speciality.id,
            'code': speciality.code,
            'name': speciality.name,
            'department_id': speciality.department_id
        }

    def _profile_to_dict(self, profile: Profile) -> Dict[str, Any]:
        """Конвертация профиля в словарь"""
        if not profile:
            return None
        return {
            'id': profile.id,
            'code': profile.code,
            'name': profile.name,
            'speciality_id': profile.speciality_id,
            'budget_places': profile.budget_places,
            'paid_places': profile.paid_places
        }
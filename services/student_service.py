# services/student_service.py
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from datetime import datetime

from database.schema import (
    Student, User, Communication, Department, Speciality, Profile,
    StudentStatus, ApplicationStatus, ContactStatus
)


class StudentService:
    """Сервис для работы с абитуриентами"""

    def __init__(self):
        pass

    def get_available_students(
            self,
            user_id: int,
            db: Session,
            skip: int = 0,
            limit: int = 100,
            status: Optional[str] = None,
            application_status: Optional[str] = None,  # ДОБАВЛЕНО
            contact_status: Optional[str] = None,  # ДОБАВЛЕНО
            consent_status: Optional[bool] = None,  # ДОБАВЛЕНО
            department_id: Optional[int] = None,
            speciality_id: Optional[int] = None,
            search: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Получение списка абитуриентов, доступных пользователю"""
        query = db.query(Student)

        # Фильтр по куратору или доступным направлениям
        user = db.query(User).filter(User.id == user_id).first()
        if user.role == 'admin':
            # Админ видит всех
            pass
        else:
            # Преподаватель видит только своих или по назначенным направлениям
            if user.assigned_departments:
                query = query.filter(Student.department_id.in_(user.assigned_departments))
            else:
                query = query.filter(Student.kurator_id == user_id)

        # Дополнительные фильтры по статусам
        if status:
            try:
                status_enum = StudentStatus(status)
                query = query.filter(Student.status == status_enum)
            except ValueError:
                pass

        # ДОБАВЛЕНО: фильтр по application_status
        if application_status:
            try:
                app_status_enum = ApplicationStatus(application_status)
                query = query.filter(Student.application_status == app_status_enum)
            except ValueError:
                pass

        # ДОБАВЛЕНО: фильтр по contact_status
        if contact_status:
            try:
                contact_status_enum = ContactStatus(contact_status)
                query = query.filter(Student.contact_status == contact_status_enum)
            except ValueError:
                pass

        # ДОБАВЛЕНО: фильтр по consent_status
        if consent_status is not None:
            query = query.filter(Student.consent_status == consent_status)

        if department_id:
            query = query.filter(Student.department_id == department_id)
        if speciality_id:
            query = query.filter(Student.speciality_id == speciality_id)
        if search:
            query = query.filter(
                (Student.full_name.ilike(f"%{search}%")) |
                (Student.phone.ilike(f"%{search}%")) |
                (Student.russian_student_id.cast(str).ilike(f"%{search}%"))
            )

        students = query.offset(skip).limit(limit).all()
        return [self._student_to_dict(s, db) for s in students]

    def get_student_by_id(self, student_id: int, user_id: int, db: Session) -> Optional[Dict[str, Any]]:
        """Получение абитуриента по ID с проверкой доступа"""
        student = db.query(Student).filter(Student.id == student_id).first()
        if not student:
            return None

        # Проверка доступа
        if not self._can_access_student(student, user_id, db):
            return None

        return self._student_to_dict(student, db)

    def create_student(self, student_data: Dict[str, Any], user_id: int, db: Session) -> Dict[str, Any]:
        """Создание нового абитуриента"""
        # Проверяем, не существует ли уже абитуриент с таким russian_student_id
        if student_data.get('russian_student_id'):
            existing = db.query(Student).filter(
                Student.russian_student_id == student_data['russian_student_id']
            ).first()
            if existing:
                raise ValueError("Абитуриент с таким ID уже существует")

        # Создаем абитуриента
        new_student = Student(
            russian_student_id=student_data.get('russian_student_id'),
            full_name=student_data['full_name'],
            phone=student_data.get('phone'),
            additional_contacts=student_data.get('additional_contacts'),
            prior_contact=student_data.get('prior_contact'),
            department_id=student_data.get('department_id'),
            speciality_id=student_data.get('speciality_id'),
            profile_id=student_data.get('profile_id'),
            study_level=student_data.get('study_level'),
            study_form=student_data.get('study_form'),
            study_basis=student_data.get('study_basis'),
            status=StudentStatus.ACTIVE.name,
            application_status=ApplicationStatus.PENDING.name,
            contact_status=ContactStatus.NEW.name,
            contact_type=student_data.get('contact_type'),  # ДОБАВЛЕНО
            consent_status=student_data.get('consent_status'),  # ДОБАВЛЕНО
            total_score=student_data.get('total_score'),
            kurator_id=user_id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        db.add(new_student)
        db.commit()
        db.refresh(new_student)

        return self._student_to_dict(new_student, db)

    def update_student(
            self,
            student_id: int,
            update_data: Dict[str, Any],
            user_id: int,
            db: Session
    ) -> Optional[Dict[str, Any]]:
        """Обновление данных абитуриента"""
        student = db.query(Student).filter(Student.id == student_id).first()
        if not student:
            return None

        # Проверка доступа
        if not self._can_access_student(student, user_id, db):
            raise PermissionError("Нет доступа к этому абитуриенту")

        # Обновляем поля
        for field, value in update_data.items():
            if value is None:
                continue

            if hasattr(student, field):
                # Для Enum полей преобразуем строку в соответствующий Enum
                if field == 'status' and isinstance(value, str):
                    try:
                        setattr(student, field, StudentStatus(value))
                    except ValueError:
                        pass
                elif field == 'application_status' and isinstance(value, str):
                    try:
                        setattr(student, field, ApplicationStatus(value))
                    except ValueError:
                        pass
                elif field == 'contact_status' and isinstance(value, str):
                    try:
                        setattr(student, field, ContactStatus(value))
                    except ValueError:
                        pass
                elif field == 'study_level' and isinstance(value, str):
                    from database.schema import StudyLevel
                    try:
                        setattr(student, field, StudyLevel(value))
                    except ValueError:
                        pass
                elif field == 'study_form' and isinstance(value, str):
                    from database.schema import StudyForm
                    try:
                        setattr(student, field, StudyForm(value))
                    except ValueError:
                        pass
                elif field == 'study_basis' and isinstance(value, str):
                    from database.schema import StudyBasis
                    try:
                        setattr(student, field, StudyBasis(value))
                    except ValueError:
                        pass
                elif field == 'prior_contact' and isinstance(value, str):
                    from database.schema import PriorContact
                    try:
                        setattr(student, field, PriorContact(value))
                    except ValueError:
                        pass
                elif field == 'contact_type' and isinstance(value, str):
                    from database.schema import ContactType  # ДОБАВЛЕНО
                    try:
                        setattr(student, field, ContactType(value))
                    except ValueError:
                        pass
                elif field == 'consent_status':  # ДОБАВЛЕНО
                    setattr(student, field, value)
                else:
                    # Обычные поля
                    setattr(student, field, value)

        student.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(student)

        return self._student_to_dict(student, db)

    def delete_student(self, student_id: int, user_id: int, db: Session) -> bool:
        """Удаление абитуриента"""
        student = db.query(Student).filter(Student.id == student_id).first()
        if not student:
            return False

        # Проверка доступа
        if not self._can_access_student(student, user_id, db):
            raise PermissionError("Нет доступа к этому абитуриенту")

        db.delete(student)
        db.commit()
        return True

    def _can_access_student(self, student: Student, user_id: int, db: Session) -> bool:
        """Проверка доступа пользователя к абитуриенту"""
        user = db.query(User).filter(User.id == user_id).first()

        # Админ имеет доступ ко всем
        if user.role == 'admin':
            return True

        # Свой куратор
        if student.kurator_id == user_id:
            return True

        # Если у преподавателя есть назначенные направления
        if user.assigned_departments and student.department_id in user.assigned_departments:
            return True

        return False

    def _student_to_dict(self, student: Student, db: Session) -> Dict[str, Any]:
        """Конвертация абитуриента в словарь - ВСЕ ПОЛЯ"""
        if not student:
            return None

        # Получаем связанные данные
        department = db.query(Department).filter(Department.id == student.department_id).first()
        speciality = db.query(Speciality).filter(Speciality.id == student.speciality_id).first()
        profile = db.query(Profile).filter(Profile.id == student.profile_id).first()

        # Получаем последнюю коммуникацию
        last_comm = db.query(Communication).filter(
            Communication.student_id == student.id
        ).order_by(Communication.date_time.desc()).first()

        # ДОБАВЛЕНО: все поля студента
        return {
            'id': student.id,
            'russian_student_id': student.russian_student_id,
            'full_name': student.full_name,
            'phone': student.phone,
            'additional_contacts': student.additional_contacts,
            'prior_contact': student.prior_contact.value if student.prior_contact else None,
            'department_id': student.department_id,
            'department_name': department.name if department else None,
            'speciality_id': student.speciality_id,
            'speciality_name': speciality.name if speciality else None,
            'profile_id': student.profile_id,
            'profile_name': profile.name if profile else None,
            'study_level': student.study_level.value if student.study_level else None,
            'study_form': student.study_form.value if student.study_form else None,
            'study_basis': student.study_basis.value if student.study_basis else None,
            'status': student.status.value if student.status else None,
            'application_status': student.application_status.value if student.application_status else None,
            'contact_status': student.contact_status.value if student.contact_status else None,
            'contact_type': student.contact_type.value if student.contact_type else None,  # ДОБАВЛЕНО
            'consent_status': student.consent_status,  # ДОБАВЛЕНО (уже boolean)
            'total_score': student.total_score,
            'last_communication': last_comm.date_time if last_comm else None,
            'last_communication_note': last_comm.notes if last_comm else None,
            'kurator_id': student.kurator_id,
            'created_at': student.created_at,
            'updated_at': student.updated_at
        }
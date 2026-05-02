# services/student_service.py
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session, joinedload
from datetime import datetime

from database.schema import (
    Student, User, Communication, Department, Speciality, Profile, StudentApplication,
    StudentStatus, ApplicationStatus, ContactStatus, PriorContact, ContactType,
    StudyLevel, StudyForm, StudyBasis
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
            application_status: Optional[str] = None,
            contact_status: Optional[str] = None,
            consent_status: Optional[bool] = None,
            department_id: Optional[int] = None,
            speciality_id: Optional[int] = None,
            search: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Получение списка абитуриентов, доступных пользователю"""
        query = db.query(Student)

        # Фильтр по куратору или доступным направлениям
        user = db.query(User).filter(User.id == user_id).first()
        if user.role == 'admin':
            pass
        else:
            if user.assigned_departments:
                # Ищем студентов у которых есть заявление на assigned_departments
                query = query.join(StudentApplication).filter(
                    StudentApplication.department_id.in_(user.assigned_departments)
                ).distinct()
            else:
                query = query.filter(Student.kurator_id == user_id)

        # Фильтры по статусам
        if status:
            try:
                query = query.filter(Student.status == StudentStatus(status))
            except ValueError:
                pass

        if contact_status:
            try:
                query = query.filter(Student.contact_status == ContactStatus(contact_status))
            except ValueError:
                pass

        if consent_status is not None:
            query = query.filter(Student.consent_status == consent_status)

        if department_id:
            query = query.join(StudentApplication).filter(StudentApplication.department_id == department_id).distinct()

        if speciality_id:
            query = query.join(StudentApplication).filter(StudentApplication.speciality_id == speciality_id).distinct()

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

        if not self._can_access_student(student, user_id, db):
            return None

        return self._student_to_dict(student, db)

    def get_student_applications(self, student_id: int, db: Session) -> List[Dict[str, Any]]:
        """Получение всех заявлений студента"""
        applications = db.query(StudentApplication).filter(
            StudentApplication.student_id == student_id
        ).all()

        result = []
        for app in applications:
            department = db.query(Department).filter(Department.id == app.department_id).first()
            speciality = db.query(Speciality).filter(Speciality.id == app.speciality_id).first()
            profile = db.query(Profile).filter(Profile.id == app.profile_id).first()

            result.append({
                'id': app.id,
                'department_id': app.department_id,
                'department_name': department.name if department else None,
                'speciality_id': app.speciality_id,
                'speciality_name': speciality.name if speciality else None,
                'profile_id': app.profile_id,
                'profile_name': profile.name if profile else None,
                'position': app.position,
                'priority': app.priority,
                'total_score': app.total_score,
                'application_status': app.application_status.value if app.application_status else None,
                'consent_status': app.consent_status,
                'participation': app.participation,
                'is_main_contest': app.is_main_contest,
            })

        return result

    def create_student(self, student_data: Dict[str, Any], user_id: int, db: Session) -> Dict[str, Any]:
        """Создание нового абитуриента"""
        if student_data.get('russian_student_id'):
            existing = db.query(Student).filter(
                Student.russian_student_id == student_data['russian_student_id']
            ).first()
            if existing:
                raise ValueError("Абитуриент с таким ID уже существует")

        new_student = Student(
            russian_student_id=student_data.get('russian_student_id'),
            full_name=student_data['full_name'],
            phone=student_data.get('phone'),
            additional_contacts=student_data.get('additional_contacts'),
            prior_contact=PriorContact(student_data['prior_contact']) if student_data.get('prior_contact') else None,
            study_level=StudyLevel(student_data['study_level']) if student_data.get('study_level') else None,
            study_form=StudyForm(student_data['study_form']) if student_data.get('study_form') else None,
            study_basis=StudyBasis(student_data['study_basis']) if student_data.get('study_basis') else None,
            status=StudentStatus.ACTIVE,
            contact_status=ContactStatus.NEW,
            contact_type=ContactType(student_data['contact_type']) if student_data.get('contact_type') else None,
            kurator_id=user_id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        db.add(new_student)
        db.commit()
        db.refresh(new_student)

        # Если есть данные о специальности - создаем заявление
        if student_data.get('department_id') and student_data.get('speciality_id'):
            application = StudentApplication(
                student_id=new_student.id,
                department_id=student_data.get('department_id'),
                speciality_id=student_data.get('speciality_id'),
                profile_id=student_data.get('profile_id'),
                total_score=student_data.get('total_score'),
                application_status=ApplicationStatus(student_data['application_status']) if student_data.get(
                    'application_status') else ApplicationStatus.PENDING,
                consent_status=student_data.get('consent_status', False)
            )
            db.add(application)
            db.commit()

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

        if not self._can_access_student(student, user_id, db):
            raise PermissionError("Нет доступа к этому абитуриенту")

        for field, value in update_data.items():
            if value is None:
                continue

            if hasattr(student, field):
                if field == 'prior_contact' and isinstance(value, str):
                    if value:
                        try:
                            setattr(student, field, PriorContact(value))
                        except ValueError as e:
                            print(f"⚠️ Ошибка: {e}")
                    else:
                        setattr(student, field, None)
                elif field == 'status' and isinstance(value, str):
                    try:
                        setattr(student, field, StudentStatus(value))
                    except ValueError:
                        pass
                elif field == 'contact_status' and isinstance(value, str):
                    try:
                        setattr(student, field, ContactStatus(value))
                    except ValueError:
                        pass
                elif field == 'contact_type' and isinstance(value, str):
                    try:
                        setattr(student, field, ContactType(value))
                    except ValueError:
                        pass
                elif field == 'study_level' and isinstance(value, str):
                    try:
                        setattr(student, field, StudyLevel(value))
                    except ValueError:
                        pass
                elif field == 'study_form' and isinstance(value, str):
                    try:
                        setattr(student, field, StudyForm(value))
                    except ValueError:
                        pass
                elif field == 'study_basis' and isinstance(value, str):
                    try:
                        setattr(student, field, StudyBasis(value))
                    except ValueError:
                        pass
                else:
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

        if not self._can_access_student(student, user_id, db):
            raise PermissionError("Нет доступа к этому абитуриенту")

        db.delete(student)
        db.commit()
        return True

    def _can_access_student(self, student: Student, user_id: int, db: Session) -> bool:
        """Проверка доступа пользователя к абитуриенту"""
        user = db.query(User).filter(User.id == user_id).first()

        if user.role == 'admin':
            return True

        if student.kurator_id == user_id:
            return True

        if user.assigned_departments:
            # Проверяем, есть ли у студента заявление на assigned_departments
            application = db.query(StudentApplication).filter(
                StudentApplication.student_id == student.id,
                StudentApplication.department_id.in_(user.assigned_departments)
            ).first()
            if application:
                return True

        return False

    def _student_to_dict(self, student: Student, db: Session) -> Dict[str, Any]:
        """Конвертация абитуриента в словарь"""
        if not student:
            return None

        # Получаем основное заявление (с наивысшим приоритетом или первое)
        main_application = db.query(StudentApplication).filter(
            StudentApplication.student_id == student.id
        ).order_by(StudentApplication.priority.asc(), StudentApplication.id.asc()).first()

        # Получаем связанные данные из основного заявления
        department = None
        speciality = None
        profile = None
        total_score = None
        application_status = None
        consent_status = None
        position = None

        if main_application:
            department = db.query(Department).filter(Department.id == main_application.department_id).first()
            speciality = db.query(Speciality).filter(Speciality.id == main_application.speciality_id).first()
            profile = db.query(Profile).filter(Profile.id == main_application.profile_id).first()
            total_score = main_application.total_score
            application_status = main_application.application_status.value if main_application.application_status else None
            consent_status = main_application.consent_status
            position = main_application.position

        # Получаем последнюю коммуникацию
        last_comm = db.query(Communication).filter(
            Communication.student_id == student.id
        ).order_by(Communication.date_time.desc()).first()

        return {
            'id': student.id,
            'russian_student_id': student.russian_student_id,
            'full_name': student.full_name,
            'phone': student.phone,
            'additional_contacts': student.additional_contacts,
            'prior_contact': student.prior_contact.value if student.prior_contact else None,
            'department_id': main_application.department_id if main_application else None,
            'department_name': department.name if department else None,
            'speciality_id': main_application.speciality_id if main_application else None,
            'speciality_name': speciality.name if speciality else None,
            'profile_id': main_application.profile_id if main_application else None,
            'profile_name': profile.name if profile else None,
            'study_level': student.study_level.value if student.study_level else None,
            'study_form': student.study_form.value if student.study_form else None,
            'study_basis': student.study_basis.value if student.study_basis else None,
            'status': student.status.value if student.status else None,
            'application_status': application_status,
            'contact_status': student.contact_status.value if student.contact_status else None,
            'contact_type': student.contact_type.value if student.contact_type else None,
            'consent_status': consent_status,
            'total_score': total_score,
            'position': position,
            'last_communication': last_comm.date_time if last_comm else None,
            'last_communication_note': last_comm.notes if last_comm else None,
            'kurator_id': student.kurator_id,
            'created_at': student.created_at,
            'updated_at': student.updated_at
        }
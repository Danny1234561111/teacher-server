# services/student_service.py
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session, joinedload
from datetime import datetime

from database.schema import (
    Student, User, Communication, Department, Speciality, Profile, StudentApplication,
    StudentStatus, ApplicationStatus, ContactStatus, PriorContact, ContactType,
    StudyLevel, StudyForm, StudyBasis, MeetingStatus, CallStatus, DecisionStatus, DocumentsStatus
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
            study_form: Optional[str] = None,
            study_basis: Optional[str] = None,
            search: Optional[str] = None,
            meeting_status: Optional[str] = None,
            call_status: Optional[str] = None,
            decision_status: Optional[str] = None,
            documents_status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Получение списка абитуриентов, доступных пользователю"""

        # Начинаем с базового запроса
        query = db.query(Student)

        # Получаем пользователя
        user = db.query(User).filter(User.id == user_id).first()

        if not user:
            # Если пользователь не найден, возвращаем пустой список
            return []

        # ПРОВЕРКА РОЛИ - приводим к верхнему регистру для сравнения
        user_role = user.role.upper() if hasattr(user.role, 'upper') else str(user.role).upper()

        # Админ видит всех студентов
        if user_role == 'ADMIN':
            # Админ видит всех - ничего не фильтруем
            pass
        else:
            # Для TEACHER - показываем только своих студентов
            query = query.filter(Student.kurator_id == user_id)

        # Применяем остальные фильтры
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

        if meeting_status:
            try:
                query = query.filter(Student.meeting_status == MeetingStatus(meeting_status))
            except ValueError:
                pass

        if call_status:
            try:
                query = query.filter(Student.call_status == CallStatus(call_status))
            except ValueError:
                pass

        if decision_status:
            try:
                query = query.filter(Student.decision_status == DecisionStatus(decision_status))
            except ValueError:
                pass

        if documents_status:
            try:
                query = query.filter(Student.documents_status == DocumentsStatus(documents_status))
            except ValueError:
                pass

        if consent_status is not None:
            query = query.join(StudentApplication).filter(
                StudentApplication.consent_status == consent_status
            ).distinct()

        if department_id:
            query = query.join(StudentApplication).filter(
                StudentApplication.department_id == department_id
            ).distinct()

        if speciality_id:
            query = query.join(StudentApplication).filter(
                StudentApplication.speciality_id == speciality_id
            ).distinct()

        if study_form:
            query = query.join(StudentApplication).filter(
                StudentApplication.study_form == study_form
            ).distinct()

        if study_basis:
            query = query.join(StudentApplication).filter(
                StudentApplication.study_basis == study_basis
            ).distinct()

        if application_status:
            try:
                status_enum = ApplicationStatus(application_status)
                query = query.join(StudentApplication).filter(
                    StudentApplication.application_status == status_enum
                ).distinct()
            except ValueError:
                pass

        if search:
            query = query.filter(
                (Student.full_name.ilike(f"%{search}%")) |
                (Student.phone.ilike(f"%{search}%")) |
                (Student.russian_student_id.cast(str).ilike(f"%{search}%"))
            )

        # Выполняем запрос
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
                'study_form': app.study_form.value if app.study_form else None,
                'study_basis': app.study_basis.value if app.study_basis else None,
                'study_level': app.study_level.value if app.study_level else None,
                'budget_places_total': app.budget_places_total,
                'budget_places_filled': app.budget_places_filled,
                'paid_places_total': app.paid_places_total,
                'paid_places_filled': app.paid_places_filled,
                'target_places_total': app.target_places_total,
                'target_places_filled': app.target_places_filled,
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
            meeting_status=MeetingStatus.NOT_MET,
            call_status=CallStatus.NOT_REACHED,
            decision_status=DecisionStatus.THINKING,
            documents_status=DocumentsStatus.NOT_SUBMITTED,
            kurator_id=user_id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        db.add(new_student)
        db.commit()
        db.refresh(new_student)

        if student_data.get('department_id') and student_data.get('speciality_id'):
            application = StudentApplication(
                student_id=new_student.id,
                department_id=student_data.get('department_id'),
                speciality_id=student_data.get('speciality_id'),
                profile_id=student_data.get('profile_id'),
                total_score=student_data.get('total_score'),
                application_status=ApplicationStatus(student_data['application_status']) if student_data.get(
                    'application_status') else ApplicationStatus.PENDING,
                consent_status=student_data.get('consent_status', False),
                study_form=StudyForm(student_data['study_form']) if student_data.get('study_form') else None,
                study_basis=StudyBasis(student_data['study_basis']) if student_data.get('study_basis') else None,
                study_level=StudyLevel(student_data['study_level']) if student_data.get('study_level') else None
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

            if field == 'study_form' and isinstance(value, str):
                try:
                    student.study_form = StudyForm(value)
                except ValueError:
                    pass
            elif field == 'study_basis' and isinstance(value, str):
                try:
                    student.study_basis = StudyBasis(value)
                except ValueError:
                    pass
            elif field == 'study_level' and isinstance(value, str):
                try:
                    student.study_level = StudyLevel(value)
                except ValueError:
                    pass
            elif field == 'prior_contact' and isinstance(value, str):
                if value:
                    try:
                        student.prior_contact = PriorContact(value)
                    except ValueError:
                        pass
                else:
                    student.prior_contact = None
            elif field == 'status' and isinstance(value, str):
                try:
                    student.status = StudentStatus(value)
                except ValueError:
                    pass
            elif field == 'contact_status' and isinstance(value, str):
                try:
                    student.contact_status = ContactStatus(value)
                except ValueError:
                    pass
            elif field == 'contact_type' and isinstance(value, str):
                try:
                    student.contact_type = ContactType(value)
                except ValueError:
                    pass
            elif field == 'meeting_status' and isinstance(value, str):
                try:
                    student.meeting_status = MeetingStatus(value)
                except ValueError:
                    pass
            elif field == 'call_status' and isinstance(value, str):
                try:
                    student.call_status = CallStatus(value)
                except ValueError:
                    pass
            elif field == 'decision_status' and isinstance(value, str):
                try:
                    student.decision_status = DecisionStatus(value)
                except ValueError:
                    pass
            elif field == 'documents_status' and isinstance(value, str):
                try:
                    student.documents_status = DocumentsStatus(value)
                except ValueError:
                    pass
            elif hasattr(student, field):
                setattr(student, field, value)

        if any(f in update_data for f in
               ['total_score', 'application_status', 'consent_status', 'position', 'study_form', 'study_basis']):
            main_application = db.query(StudentApplication).filter(
                StudentApplication.student_id == student_id
            ).order_by(StudentApplication.priority.asc(), StudentApplication.id.asc()).first()

            if main_application:
                if 'total_score' in update_data and update_data['total_score'] is not None:
                    main_application.total_score = update_data['total_score']
                if 'application_status' in update_data and update_data['application_status'] is not None:
                    try:
                        main_application.application_status = ApplicationStatus(update_data['application_status'])
                    except ValueError:
                        pass
                if 'consent_status' in update_data and update_data['consent_status'] is not None:
                    main_application.consent_status = update_data['consent_status']
                if 'position' in update_data and update_data['position'] is not None:
                    main_application.position = update_data['position']
                if 'study_form' in update_data and update_data['study_form'] is not None:
                    try:
                        main_application.study_form = StudyForm(update_data['study_form'])
                    except ValueError:
                        pass
                if 'study_basis' in update_data and update_data['study_basis'] is not None:
                    try:
                        main_application.study_basis = StudyBasis(update_data['study_basis'])
                    except ValueError:
                        pass

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

        if not user:
            return False

        # Приводим роль к верхнему регистру для сравнения
        user_role = user.role.upper() if hasattr(user.role, 'upper') else str(user.role).upper()

        # Админ имеет доступ ко всем студентам
        if user_role == 'ADMIN':
            return True

        # Преподаватель - только к своим
        if student.kurator_id == user_id:
            return True

        return False

    def get_competitive_info_for_student(
            self,
            student_id: int,
            db: Session,
            speciality_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Получение конкурсной информации для студента"""
        query = db.query(StudentApplication).filter(
            StudentApplication.student_id == student_id
        )

        if speciality_id:
            query = query.filter(StudentApplication.speciality_id == speciality_id)

        application = query.order_by(
            StudentApplication.priority.asc(),
            StudentApplication.id.asc()
        ).first()

        if not application:
            return {
                'position': None,
                'total_students': 0,
                'total_enrolled': 0,
                'total_submitted': 0,
                'average_score': 0,
                'min_score': 0,
                'max_score': 0,
                'passing_score': None,
                'student_score': None,
                'department_name': None,
                'speciality_name': None,
                'profile_name': None,
                'study_form': None,
                'study_basis': None,
                'budget_places_total': None,
                'budget_places_filled': None,
                'budget_places_free': None,
                'competition': None
            }

        group_query = db.query(StudentApplication).filter(
            StudentApplication.department_id == application.department_id,
            StudentApplication.speciality_id == application.speciality_id
        )

        if application.profile_id:
            group_query = group_query.filter(StudentApplication.profile_id == application.profile_id)

        if application.study_form:
            group_query = group_query.filter(StudentApplication.study_form == application.study_form)

        if application.study_basis:
            group_query = group_query.filter(StudentApplication.study_basis == application.study_basis)

        all_applications = group_query.all()

        sorted_apps = sorted(all_applications, key=lambda x: x.total_score or 0, reverse=True)

        position = 1
        for i, app in enumerate(sorted_apps, 1):
            if app.student_id == student_id:
                position = i
                break

        total_students = len(all_applications)
        enrolled_count = len([a for a in all_applications if a.application_status == ApplicationStatus.ACCEPTED])
        submitted_count = len([a for a in all_applications if a.application_status != ApplicationStatus.PENDING])

        scores = [a.total_score for a in all_applications if a.total_score and a.total_score > 0]
        avg_score = sum(scores) / len(scores) if scores else 0
        min_score = min(scores) if scores else 0
        max_score = max(scores) if scores else 0

        passing_score = None
        if enrolled_count > 0:
            enrolled_apps = [a for a in all_applications if a.application_status == ApplicationStatus.ACCEPTED]
            enrolled_sorted = sorted(enrolled_apps, key=lambda x: x.total_score or 0, reverse=True)
            if enrolled_sorted:
                passing_score = enrolled_sorted[-1].total_score

        department = db.query(Department).filter(Department.id == application.department_id).first()
        speciality = db.query(Speciality).filter(Speciality.id == application.speciality_id).first()
        profile = db.query(Profile).filter(
            Profile.id == application.profile_id).first() if application.profile_id else None

        budget_places_free = None
        if application.budget_places_total:
            filled = application.budget_places_filled or 0
            budget_places_free = application.budget_places_total - filled

        competition = None
        if application.budget_places_total and application.budget_places_total > 0:
            competition = round(total_students / application.budget_places_total, 2)

        return {
            'position': position,
            'total_students': total_students,
            'total_enrolled': enrolled_count,
            'total_submitted': submitted_count,
            'average_score': round(avg_score, 2),
            'min_score': min_score,
            'max_score': max_score,
            'passing_score': passing_score,
            'student_score': application.total_score,
            'department_name': department.name if department else None,
            'speciality_name': speciality.name if speciality else None,
            'profile_name': profile.name if profile else None,
            'study_form': application.study_form.value if application.study_form else None,
            'study_basis': application.study_basis.value if application.study_basis else None,
            'budget_places_total': application.budget_places_total,
            'budget_places_filled': application.budget_places_filled,
            'budget_places_free': budget_places_free,
            'competition': competition
        }

    def _student_to_dict(self, student: Student, db: Session) -> Dict[str, Any]:
        """Конвертация абитуриента в словарь"""
        if not student:
            return None

        main_application = db.query(StudentApplication).filter(
            StudentApplication.student_id == student.id
        ).order_by(StudentApplication.priority.asc(), StudentApplication.id.asc()).first()

        department = None
        speciality = None
        profile = None
        total_score = None
        application_status = None
        consent_status = None
        position = None
        study_form = None
        study_basis = None

        if main_application:
            department = db.query(Department).filter(Department.id == main_application.department_id).first()
            speciality = db.query(Speciality).filter(Speciality.id == main_application.speciality_id).first()
            profile = db.query(Profile).filter(Profile.id == main_application.profile_id).first()
            total_score = main_application.total_score
            application_status = main_application.application_status.value if main_application.application_status else None
            consent_status = main_application.consent_status
            position = main_application.position
            study_form = main_application.study_form.value if main_application.study_form else (
                student.study_form.value if student.study_form else None
            )
            study_basis = main_application.study_basis.value if main_application.study_basis else (
                student.study_basis.value if student.study_basis else None
            )

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
            'study_form': study_form,
            'study_basis': study_basis,
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
            'updated_at': student.updated_at,
            'meeting_status': student.meeting_status.value if student.meeting_status else "NOT_MET",
            'call_status': student.call_status.value if student.call_status else "NOT_REACHED",
            'decision_status': student.decision_status.value if student.decision_status else "THINKING",
            'documents_status': student.documents_status.value if student.documents_status else "NOT_SUBMITTED"
        }
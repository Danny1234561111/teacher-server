from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, or_, desc, asc, func, text, select
from typing import List, Dict, Any, Optional, Union
from datetime import datetime, date, timedelta
import uuid
import json

from database.database import get_db
from database.schema import (
    User, Student, Department, Speciality,
    Communication, TeacherRequest, StudentRequest,
    AdminNotification, SystemSetting, DepartmentAccessRequest
)
from schemas import (
    UserCreate, UserUpdate, StudentCreate, StudentUpdateRequest,
    DepartmentCreate, DepartmentUpdate, SpecialityCreate, SpecialityUpdate,
    CommunicationCreate, CommunicationUpdate, TeacherRegistrationRequest,
    StudentRequestCreate, StudentRequestUpdate, AdminNotificationBase
)


class DatabaseService:
    """Сервис для работы с PostgreSQL через SQLAlchemy"""

    def __init__(self):
        self.db_gen = get_db()
        self.db: Session = next(self.db_gen)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.db.close()

    def check_connection(self) -> bool:
        """Проверка соединения с базой данных"""
        try:
            self.db.execute("SELECT 1")
            return True
        except Exception:
            return False

    # ========== USERS ==========

    def create_user(self, user_data: Dict[str, Any]) -> str:
        """Создание пользователя"""
        user_id = str(uuid.uuid4())

        user = User(
            id=user_id,
            email=user_data['email'],
            full_name=user_data['full_name'],
            phone=user_data.get('phone'),
            role=user_data.get('role', 'teacher'),
            date_of_birth=user_data.get('date_of_birth'),
            max_students=user_data.get('max_students', 20),
            current_students_count=0,
            assigned_departments=user_data.get('assigned_departments', []),
            assigned_specialities=user_data.get('assigned_specialities', []),
            experience=user_data.get('experience'),
            education=user_data.get('education'),
            is_active=user_data.get('is_active', True),
            approved_by=user_data.get('approved_by'),
            approved_at=user_data.get('approved_at'),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            last_login=user_data.get('last_login')
        )

        self.db.add(user)
        self.db.commit()
        return user_id

    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Получение пользователя по ID"""
        user = self.db.query(User).filter(User.id == user_id).first()
        if user:
            return self._user_to_dict(user)
        return None

    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Получение пользователя по email"""
        user = self.db.query(User).filter(User.email == email).first()
        if user:
            return self._user_to_dict(user)
        return None

    def update_user(self, user_id: str, update_data: Dict[str, Any]) -> bool:
        """Обновление пользователя"""
        try:
            user = self.db.query(User).filter(User.id == user_id).first()
            if not user:
                return False

            for key, value in update_data.items():
                if hasattr(user, key):
                    setattr(user, key, value)

            user.updated_at = datetime.utcnow()
            self.db.commit()
            return True
        except Exception:
            self.db.rollback()
            return False

    def delete_user(self, user_id: str) -> bool:
        """Удаление пользователя"""
        try:
            user = self.db.query(User).filter(User.id == user_id).first()
            if user:
                self.db.delete(user)
                self.db.commit()
                return True
            return False
        except Exception:
            self.db.rollback()
            return False

    def get_all_users(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Получение всех пользователей"""
        users = self.db.query(User).offset(offset).limit(limit).all()
        return [self._user_to_dict(user) for user in users]

    def get_teachers(self, active_only: bool = True, limit: int = 100) -> List[Dict[str, Any]]:
        """Получение преподавателей"""
        query = self.db.query(User).filter(User.role == 'teacher')

        if active_only:
            query = query.filter(User.is_active == True)

        teachers = query.limit(limit).all()
        return [self._user_to_dict(teacher) for teacher in teachers]

    def count_teachers(self) -> int:
        """Подсчет количества преподавателей"""
        return self.db.query(User).filter(User.role == 'teacher').count()

    # ========== STUDENTS ==========

    def create_student(self, student_data: Dict[str, Any]) -> str:
        """Создание студента"""
        student_id = str(uuid.uuid4())

        # Проверка уникальности Russian Student ID
        if student_data.get('russian_student_id'):
            existing = self.get_student_by_russian_id(student_data['russian_student_id'])
            if existing:
                raise ValueError(f"Студент с Russian ID {student_data['russian_student_id']} уже существует")

        student = Student(
            id=student_id,
            russian_student_id=student_data.get('russian_student_id'),
            full_name=student_data['full_name'],
            phone=student_data['phone'],
            email=student_data.get('email'),
            date_of_birth=student_data.get('date_of_birth'),
            status=student_data.get('status', 'active'),
            application_status=student_data.get('application_status', 'pending'),
            department_id=student_data.get('department_id'),
            speciality_id=student_data.get('speciality_id'),
            priority_place=student_data.get('priority_place', 1),
            exam_scores=student_data.get('exam_scores', {}),
            additional_contacts=student_data.get('additional_contacts', []),
            notes=student_data.get('notes'),
            assigned_teacher_id=student_data.get('assigned_teacher_id'),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        self.db.add(student)

        # Обновляем счетчик у преподавателя
        if student.assigned_teacher_id:
            self._increment_teacher_student_count(student.assigned_teacher_id)

        self.db.commit()
        return student_id

    def get_student_by_id(self, student_id: str) -> Optional[Dict[str, Any]]:
        """Получение студента по ID"""
        student = self.db.query(Student).filter(Student.id == student_id).first()
        if student:
            return self._student_to_dict(student)
        return None

    def get_student_by_russian_id(self, russian_id: str) -> Optional[Dict[str, Any]]:
        """Получение студента по российскому ID"""
        student = self.db.query(Student).filter(Student.russian_student_id == russian_id).first()
        if student:
            return self._student_to_dict(student)
        return None

    def update_student(self, student_id: str, update_data: Dict[str, Any]) -> bool:
        """Обновление студента"""
        try:
            student = self.db.query(Student).filter(Student.id == student_id).first()
            if not student:
                return False

            # Сохраняем старого преподавателя для обновления счетчика
            old_teacher_id = student.assigned_teacher_id
            new_teacher_id = update_data.get('assigned_teacher_id')

            for key, value in update_data.items():
                if hasattr(student, key):
                    setattr(student, key, value)

            student.updated_at = datetime.utcnow()

            # Обновляем счетчики преподавателей
            if old_teacher_id != new_teacher_id:
                if old_teacher_id:
                    self._decrement_teacher_student_count(old_teacher_id)
                if new_teacher_id:
                    self._increment_teacher_student_count(new_teacher_id)

            self.db.commit()
            return True
        except Exception as e:
            self.db.rollback()
            print(f"Ошибка обновления студента: {e}")
            return False

    def delete_student(self, student_id: str) -> bool:
        """Удаление студента"""
        try:
            student = self.db.query(Student).filter(Student.id == student_id).first()
            if not student:
                return False

            # Уменьшаем счетчик у преподавателя
            if student.assigned_teacher_id:
                self._decrement_teacher_student_count(student.assigned_teacher_id)

            self.db.delete(student)
            self.db.commit()
            return True
        except Exception:
            self.db.rollback()
            return False

    def get_students_by_teacher(self, teacher_id: str, status: Optional[str] = None,
                                limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Получение студентов преподавателя"""
        query = self.db.query(Student).filter(Student.assigned_teacher_id == teacher_id)

        if status:
            query = query.filter(Student.status == status)

        students = query.order_by(desc(Student.created_at)).offset(offset).limit(limit).all()
        return [self._student_to_dict(student) for student in students]

    def search_students(self, search_term: str, teacher_id: Optional[str] = None,
                        limit: int = 50) -> List[Dict[str, Any]]:
        """Поиск студентов"""
        query = self.db.query(Student)

        if teacher_id:
            query = query.filter(Student.assigned_teacher_id == teacher_id)

        # Используем ILIKE для регистронезависимого поиска
        search_pattern = f"%{search_term}%"
        students = query.filter(
            or_(
                Student.full_name.ilike(search_pattern),
                Student.russian_student_id.ilike(search_pattern),
                Student.phone.ilike(search_pattern),
                Student.email.ilike(search_pattern)
            )
        ).limit(limit).all()

        return [self._student_to_dict(student) for student in students]

    def get_all_students_filtered(self, department_id: Optional[str] = None,
                                  speciality_id: Optional[str] = None,
                                  status: Optional[str] = None,
                                  limit: int = 100,
                                  offset: int = 0) -> List[Dict[str, Any]]:
        """Получение студентов с фильтрами"""
        query = self.db.query(Student)

        if department_id:
            query = query.filter(Student.department_id == department_id)
        if speciality_id:
            query = query.filter(Student.speciality_id == speciality_id)
        if status:
            query = query.filter(Student.status == status)

        students = query.order_by(desc(Student.created_at)).offset(offset).limit(limit).all()
        return [self._student_to_dict(student) for student in students]

    def get_students_by_departments(self, department_ids: List[str] = None,
                                    speciality_ids: List[str] = None,
                                    limit: int = 100,
                                    offset: int = 0) -> List[Dict[str, Any]]:
        """Получение студентов по направлениям"""
        query = self.db.query(Student)

        if department_ids and 'all' not in department_ids:
            query = query.filter(Student.department_id.in_(department_ids))
        if speciality_ids and 'all' not in speciality_ids:
            query = query.filter(Student.speciality_id.in_(speciality_ids))

        students = query.order_by(desc(Student.created_at)).offset(offset).limit(limit).all()
        return [self._student_to_dict(student) for student in students]

    def count_students_by_teacher(self, teacher_id: str) -> int:
        """Подсчет студентов преподавателя"""
        return self.db.query(Student).filter(Student.assigned_teacher_id == teacher_id).count()

    # ========== DEPARTMENTS ==========

    def create_department(self, department_data: Dict[str, Any]) -> str:
        """Создание направления"""
        department_id = f"dept_{department_data['code']}"

        department = Department(
            id=department_id,
            code=department_data['code'],
            name=department_data['name'],
            faculty=department_data.get('faculty', ''),
            description=department_data.get('description'),
            is_active=department_data.get('is_active', True),
            dean=department_data.get('dean'),
            contact_email=department_data.get('contact_email'),
            contact_phone=department_data.get('contact_phone'),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        self.db.add(department)
        self.db.commit()
        return department_id

    def get_department_by_id(self, department_id: str) -> Optional[Dict[str, Any]]:
        """Получение направления по ID"""
        department = self.db.query(Department).filter(Department.id == department_id).first()
        if department:
            return self._department_to_dict(department)
        return None

    def get_all_departments(self) -> List[Dict[str, Any]]:
        """Получение всех направлений"""
        departments = self.db.query(Department).all()
        return [self._department_to_dict(dept) for dept in departments]

    # ========== SPECIALITIES ==========

    def create_speciality(self, speciality_data: Dict[str, Any]) -> str:
        """Создание специальности"""
        # Проверяем существование направления
        department = self.db.query(Department).filter(Department.id == speciality_data['department_id']).first()
        if not department:
            raise ValueError(f"Направление {speciality_data['department_id']} не найдено")

        speciality_id = f"spec_{speciality_data['code']}"

        speciality = Speciality(
            id=speciality_id,
            code=speciality_data['code'],
            name=speciality_data['name'],
            department_id=speciality_data['department_id'],
            study_duration=speciality_data.get('study_duration', 4),
            description=speciality_data.get('description'),
            is_active=speciality_data.get('is_active', True),
            tuition_fee=speciality_data.get('tuition_fee'),
            required_exams=speciality_data.get('required_exams', []),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        self.db.add(speciality)
        self.db.commit()
        return speciality_id

    def get_speciality_by_id(self, speciality_id: str) -> Optional[Dict[str, Any]]:
        """Получение специальности по ID"""
        speciality = self.db.query(Speciality).filter(Speciality.id == speciality_id).first()
        if speciality:
            result = self._speciality_to_dict(speciality)
            # Добавляем название направления
            if speciality.department:
                result['department_name'] = speciality.department.name
            return result
        return None

    def get_all_specialities(self, department_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Получение всех специальностей"""
        query = self.db.query(Speciality)

        if department_id:
            query = query.filter(Speciality.department_id == department_id)

        specialities = query.all()
        result = []
        for spec in specialities:
            spec_dict = self._speciality_to_dict(spec)
            if spec.department:
                spec_dict['department_name'] = spec.department.name
            result.append(spec_dict)

        return result

    # ========== COMMUNICATIONS ==========

    def create_communication(self, communication_data: Dict[str, Any], user_id: str) -> str:
        """Создание записи о коммуникации"""
        communication_id = str(uuid.uuid4())

        # Проверяем существование студента
        student = self.db.query(Student).filter(Student.id == communication_data['student_id']).first()
        if not student:
            raise ValueError(f"Студент с ID {communication_data['student_id']} не найден")

        communication = Communication(
            id=communication_id,
            student_id=communication_data['student_id'],
            communication_type=communication_data.get('communication_type', 'call'),
            status=communication_data.get('status', 'completed'),
            date_time=communication_data.get('date_time', datetime.utcnow()),
            duration_minutes=communication_data.get('duration_minutes'),
            topic=communication_data['topic'],
            notes=communication_data['notes'],
            next_action=communication_data.get('next_action'),
            next_action_date=communication_data.get('next_action_date'),
            attachment_urls=communication_data.get('attachment_urls', []),
            is_important=communication_data.get('is_important', False),
            created_by=user_id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        self.db.add(communication)

        # Обновляем дату последней коммуникации у студента
        student.last_communication_date = datetime.utcnow()

        self.db.commit()
        return communication_id

    def get_communication_by_id(self, communication_id: str) -> Optional[Dict[str, Any]]:
        """Получение коммуникации по ID"""
        communication = self.db.query(Communication).filter(Communication.id == communication_id).first()
        if communication:
            return self._communication_to_dict(communication)
        return None

    def get_communications_by_student(self, student_id: str, user_id: str,
                                      limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """Получение коммуникаций по студенту"""
        # Проверяем права доступа
        student = self.db.query(Student).filter(Student.id == student_id).first()
        if not student:
            return []

        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            return []

        # Проверяем доступ для преподавателя
        if user.role == 'teacher' and student.assigned_teacher_id != user_id:
            # Проверяем доступ к направлению
            teacher_departments = user.assigned_departments or []
            if student.department_id and 'all' not in teacher_departments:
                if student.department_id not in teacher_departments:
                    return []

        communications = self.db.query(Communication).filter(
            Communication.student_id == student_id
        ).order_by(desc(Communication.date_time)).offset(offset).limit(limit).all()

        result = []
        for comm in communications:
            comm_dict = self._communication_to_dict(comm)
            comm_dict['student_name'] = student.full_name
            comm_dict['student_phone'] = student.phone
            result.append(comm_dict)

        return result

    def get_communications_by_teacher(self, teacher_id: str, limit: int = 100,
                                      offset: int = 0) -> List[Dict[str, Any]]:
        """Получение коммуникаций преподавателя"""
        # Получаем студентов преподавателя
        student_ids = [s.id for s in self.db.query(Student.id).filter(
            Student.assigned_teacher_id == teacher_id
        ).all()]

        if not student_ids:
            return []

        communications = self.db.query(Communication).filter(
            Communication.student_id.in_(student_ids)
        ).order_by(desc(Communication.date_time)).offset(offset).limit(limit).all()

        # Получаем информацию о студентах
        students = {s.id: s for s in self.db.query(Student).filter(
            Student.id.in_(student_ids)
        ).all()}

        result = []
        for comm in communications:
            comm_dict = self._communication_to_dict(comm)
            student = students.get(comm.student_id)
            if student:
                comm_dict['student_name'] = student.full_name
                comm_dict['student_phone'] = student.phone
            result.append(comm_dict)

        return result

    def update_communication(self, communication_id: str, update_data: Dict[str, Any], user_id: str) -> bool:
        """Обновление коммуникации"""
        try:
            communication = self.db.query(Communication).filter(Communication.id == communication_id).first()
            if not communication:
                return False

            # Проверяем права доступа
            user = self.db.query(User).filter(User.id == user_id).first()
            if not user:
                return False

            if user.role != 'admin' and communication.created_by != user_id:
                return False

            for key, value in update_data.items():
                if hasattr(communication, key) and key not in ['id', 'student_id', 'created_by', 'created_at']:
                    setattr(communication, key, value)

            communication.updated_at = datetime.utcnow()
            self.db.commit()
            return True
        except Exception:
            self.db.rollback()
            return False

    def delete_communication(self, communication_id: str, user_id: str) -> bool:
        """Удаление коммуникации"""
        try:
            communication = self.db.query(Communication).filter(Communication.id == communication_id).first()
            if not communication:
                return False

            # Проверяем права доступа
            user = self.db.query(User).filter(User.id == user_id).first()
            if not user:
                return False

            if user.role != 'admin' and communication.created_by != user_id:
                return False

            self.db.delete(communication)
            self.db.commit()
            return True
        except Exception:
            self.db.rollback()
            return False

    def get_communication_stats(self, teacher_id: str, days_back: int = 30) -> Dict[str, Any]:
        """Получение статистики по коммуникациям"""
        date_from = datetime.utcnow() - timedelta(days=days_back)

        # Получаем студентов преподавателя
        student_ids = [s.id for s in self.db.query(Student.id).filter(
            Student.assigned_teacher_id == teacher_id
        ).all()]

        if not student_ids:
            return {
                'total_communications': 0,
                'by_type': {},
                'by_status': {},
                'recent_communications': [],
                'upcoming_actions': []
            }

        # Получаем коммуникации
        communications = self.db.query(Communication).filter(
            Communication.student_id.in_(student_ids),
            Communication.date_time >= date_from
        ).all()

        stats = {
            'total_communications': len(communications),
            'by_type': {},
            'by_status': {},
            'recent_communications': [],
            'upcoming_actions': []
        }

        for comm in communications:
            comm_type = comm.communication_type or 'other'
            stats['by_type'][comm_type] = stats['by_type'].get(comm_type, 0) + 1

            status = comm.status or 'completed'
            stats['by_status'][status] = stats['by_status'].get(status, 0) + 1

        # Добавляем информацию о последних коммуникациях
        recent_comms = self.db.query(Communication).filter(
            Communication.student_id.in_(student_ids)
        ).order_by(desc(Communication.date_time)).limit(5).all()

        for comm in recent_comms:
            stats['recent_communications'].append({
                'id': comm.id,
                'student_id': comm.student_id,
                'date_time': comm.date_time,
                'topic': comm.topic,
                'type': comm.communication_type
            })

        return stats

    # ========== TEACHER REQUESTS ==========

    def create_teacher_request(self, request_data: Dict[str, Any]) -> str:
        """Создание заявки преподавателя"""
        request_id = str(uuid.uuid4())

        request = TeacherRequest(
            id=request_id,
            full_name=request_data['full_name'],
            email=request_data['email'],
            phone=request_data.get('phone'),
            max_students=request_data.get('max_students', 20),
            status='pending',
            requested_at=datetime.utcnow(),
            message=request_data.get('message', ''),
            assigned_departments=request_data.get('departments', []),
            experience=request_data.get('experience'),
            education=request_data.get('education')
        )

        self.db.add(request)
        self.db.commit()
        return request_id

    def get_teacher_request(self, request_id: str) -> Optional[Dict[str, Any]]:
        """Получение заявки преподавателя"""
        request = self.db.query(TeacherRequest).filter(TeacherRequest.id == request_id).first()
        if request:
            return self._teacher_request_to_dict(request)
        return None

    def get_teacher_requests(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Получение заявок преподавателей"""
        query = self.db.query(TeacherRequest)

        if status:
            query = query.filter(TeacherRequest.status == status)

        requests = query.order_by(desc(TeacherRequest.requested_at)).all()
        return [self._teacher_request_to_dict(req) for req in requests]

    def update_teacher_request(self, request_id: str, update_data: Dict[str, Any]) -> bool:
        """Обновление заявки преподавателя"""
        try:
            request = self.db.query(TeacherRequest).filter(TeacherRequest.id == request_id).first()
            if not request:
                return False

            for key, value in update_data.items():
                if hasattr(request, key):
                    setattr(request, key, value)

            self.db.commit()
            return True
        except Exception:
            self.db.rollback()
            return False

    def approve_teacher_request(self, request_id: str, admin_id: str, departments: List[str] = None) -> bool:
        """Одобрение заявки преподавателя"""
        try:
            request = self.db.query(TeacherRequest).filter(TeacherRequest.id == request_id).first()
            if not request or request.status != 'pending':
                return False

            request.status = 'approved'
            request.approved_by = admin_id
            request.approved_at = datetime.utcnow()

            if departments:
                request.assigned_departments = departments

            self.db.commit()
            return True
        except Exception:
            self.db.rollback()
            return False

    def reject_teacher_request(self, request_id: str, admin_id: str, reason: str = "") -> bool:
        """Отклонение заявки преподавателя"""
        try:
            request = self.db.query(TeacherRequest).filter(TeacherRequest.id == request_id).first()
            if not request or request.status != 'pending':
                return False

            request.status = 'rejected'
            request.rejected_by = admin_id
            request.rejected_at = datetime.utcnow()
            request.rejection_reason = reason

            self.db.commit()
            return True
        except Exception:
            self.db.rollback()
            return False

    # ========== STATISTICS ==========

    def get_statistics(self) -> Dict[str, Any]:
        """Получение статистики"""
        stats = {
            'total_users': 0,
            'total_teachers': 0,
            'total_students': 0,
            'active_students': 0,
            'inactive_students': 0,
            'students_by_status': {},
            'students_by_department': {},
            'teachers_by_student_count': []
        }

        try:
            # Пользователи
            stats['total_users'] = self.db.query(User).count()
            stats['total_teachers'] = self.db.query(User).filter(User.role == 'teacher').count()

            # Студенты
            students = self.db.query(Student).all()
            stats['total_students'] = len(students)

            for student in students:
                status = student.status or 'unknown'
                stats['students_by_status'][status] = stats['students_by_status'].get(status, 0) + 1

                if status == 'active':
                    stats['active_students'] += 1
                else:
                    stats['inactive_students'] += 1

                # Направления
                if student.department_id:
                    stats['students_by_department'][student.department_id] = \
                        stats['students_by_department'].get(student.department_id, 0) + 1

            # Преподаватели по количеству студентов
            teachers = self.db.query(User).filter(User.role == 'teacher').all()
            for teacher in teachers:
                student_count = self.count_students_by_teacher(teacher.id)
                stats['teachers_by_student_count'].append({
                    'teacher_id': teacher.id,
                    'teacher_name': teacher.full_name,
                    'student_count': student_count
                })

            # Сортируем преподаватели по количеству студентов
            stats['teachers_by_student_count'].sort(key=lambda x: x['student_count'], reverse=True)

            return stats

        except Exception as e:
            print(f"Ошибка получения статистики: {e}")
            return stats

    # ========== PRIVATE METHODS ==========

    def _increment_teacher_student_count(self, teacher_id: str):
        """Увеличивает счетчик студентов у преподавателя"""
        try:
            teacher = self.db.query(User).filter(User.id == teacher_id).first()
            if teacher:
                teacher.current_students_count = (teacher.current_students_count or 0) + 1
                teacher.updated_at = datetime.utcnow()
                self.db.commit()
        except Exception as e:
            self.db.rollback()
            print(f"Ошибка увеличения счетчика студентов: {e}")

    def _decrement_teacher_student_count(self, teacher_id: str):
        """Уменьшает счетчик студентов у преподавателя"""
        try:
            teacher = self.db.query(User).filter(User.id == teacher_id).first()
            if teacher and (teacher.current_students_count or 0) > 0:
                teacher.current_students_count = (teacher.current_students_count or 0) - 1
                teacher.updated_at = datetime.utcnow()
                self.db.commit()
        except Exception as e:
            self.db.rollback()
            print(f"Ошибка уменьшения счетчика студентов: {e}")

    def _user_to_dict(self, user: User) -> Dict[str, Any]:
        """Конвертация пользователя в словарь"""
        if not user:
            return {}

        return {
            'id': user.id,
            'email': user.email,
            'full_name': user.full_name,
            'phone': user.phone,
            'role': user.role,
            'date_of_birth': user.date_of_birth,
            'max_students': user.max_students,
            'current_students_count': user.current_students_count,
            'assigned_departments': user.assigned_departments or [],
            'assigned_specialities': user.assigned_specialities or [],
            'experience': user.experience,
            'education': user.education,
            'is_active': user.is_active,
            'approved_by': user.approved_by,
            'approved_at': user.approved_at,
            'created_at': user.created_at,
            'updated_at': user.updated_at,
            'last_login': user.last_login
        }

    def _student_to_dict(self, student: Student) -> Dict[str, Any]:
        """Конвертация студента в словарь"""
        if not student:
            return {}

        result = {
            'id': student.id,
            'russian_student_id': student.russian_student_id,
            'full_name': student.full_name,
            'phone': student.phone,
            'email': student.email,
            'date_of_birth': student.date_of_birth,
            'status': student.status,
            'application_status': student.application_status,
            'department_id': student.department_id,
            'speciality_id': student.speciality_id,
            'priority_place': student.priority_place,
            'exam_scores': student.exam_scores or {},
            'additional_contacts': student.additional_contacts or [],
            'notes': student.notes,
            'assigned_teacher_id': student.assigned_teacher_id,
            'last_communication_date': student.last_communication_date,
            'created_at': student.created_at,
            'updated_at': student.updated_at
        }

        # Добавляем информацию о направлении и специальности если есть
        if student.department:
            result['department_name'] = student.department.name
        if student.speciality:
            result['speciality_name'] = student.speciality.name

        return result

    def _department_to_dict(self, department: Department) -> Dict[str, Any]:
        """Конвертация направления в словарь"""
        if not department:
            return {}

        return {
            'id': department.id,
            'code': department.code,
            'name': department.name,
            'faculty': department.faculty,
            'description': department.description,
            'is_active': department.is_active,
            'dean': department.dean,
            'contact_email': department.contact_email,
            'contact_phone': department.contact_phone,
            'created_at': department.created_at,
            'updated_at': department.updated_at
        }

    def _speciality_to_dict(self, speciality: Speciality) -> Dict[str, Any]:
        """Конвертация специальности в словарь"""
        if not speciality:
            return {}

        return {
            'id': speciality.id,
            'code': speciality.code,
            'name': speciality.name,
            'department_id': speciality.department_id,
            'study_duration': speciality.study_duration,
            'description': speciality.description,
            'is_active': speciality.is_active,
            'tuition_fee': float(speciality.tuition_fee) if speciality.tuition_fee else None,
            'required_exams': speciality.required_exams or [],
            'created_at': speciality.created_at,
            'updated_at': speciality.updated_at
        }

    def _communication_to_dict(self, communication: Communication) -> Dict[str, Any]:
        """Конвертация коммуникации в словарь"""
        if not communication:
            return {}

        return {
            'id': communication.id,
            'student_id': communication.student_id,
            'communication_type': communication.communication_type,
            'status': communication.status,
            'date_time': communication.date_time,
            'duration_minutes': communication.duration_minutes,
            'topic': communication.topic,
            'notes': communication.notes,
            'next_action': communication.next_action,
            'next_action_date': communication.next_action_date,
            'attachment_urls': communication.attachment_urls or [],
            'is_important': communication.is_important,
            'created_by': communication.created_by,
            'created_at': communication.created_at,
            'updated_at': communication.updated_at
        }

    def _teacher_request_to_dict(self, request: TeacherRequest) -> Dict[str, Any]:
        """Конвертация заявки преподавателя в словарь"""
        if not request:
            return {}

        return {
            'id': request.id,
            'full_name': request.full_name,
            'email': request.email,
            'phone': request.phone,
            'max_students': request.max_students,
            'status': request.status,
            'requested_at': request.requested_at,
            'message': request.message,
            'assigned_departments': request.assigned_departments or [],
            'experience': request.experience,
            'education': request.education,
            'approved_by': request.approved_by,
            'approved_at': request.approved_at,
            'rejected_by': request.rejected_by,
            'rejected_at': request.rejected_at,
            'rejection_reason': request.rejection_reason,
            'user_id': request.user_id
        }
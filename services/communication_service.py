from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session

from database.schema import Communication, Student, User


class CommunicationService:
    """Сервис для управления коммуникациями с абитуриентами"""

    # Допустимые значения для contact_status (ENUM в БД)
    VALID_CONTACT_STATUSES = [
        'NEW', 'MET', 'INTERESTED', 'ORIGINAL_SUBMITTED',
        'WAITING_ORIGINAL', 'NOT_INTERESTED', 'ENROLLED', 'WITHDRAWN'
    ]

    # Допустимые значения для communication_type (ENUM в БД - в UPPERCASE)
    VALID_COMMUNICATION_TYPES = ['CALL', 'MEETING', 'EMAIL', 'MESSAGE']

    # Допустимые значения для status коммуникации (ENUM в БД - в UPPERCASE)
    VALID_STATUSES = ['PLANNED', 'COMPLETED', 'CANCELLED', 'MISSED']

    # Маппинг для преобразования строковых значений в ENUM для contact_status
    STATUS_MAPPING = {
        # Русские варианты
        'новый': 'NEW',
        'новый контакт': 'NEW',
        'встретились': 'MET',
        'встреча': 'MET',
        'заинтересован': 'INTERESTED',
        'заинтересован в поступлении': 'INTERESTED',
        'подал оригиналы': 'ORIGINAL_SUBMITTED',
        'оригиналы поданы': 'ORIGINAL_SUBMITTED',
        'ждем оригиналы': 'WAITING_ORIGINAL',
        'ожидание оригиналов': 'WAITING_ORIGINAL',
        'не заинтересован': 'NOT_INTERESTED',
        'отказ': 'NOT_INTERESTED',
        'зачислен': 'ENROLLED',
        'отчислен': 'WITHDRAWN',

        # Английские варианты
        'new': 'NEW',
        'met': 'MET',
        'interested': 'INTERESTED',
        'original_submitted': 'ORIGINAL_SUBMITTED',
        'waiting_original': 'WAITING_ORIGINAL',
        'not_interested': 'NOT_INTERESTED',
        'enrolled': 'ENROLLED',
        'withdrawn': 'WITHDRAWN',

        # Ошибочные значения (для обратной совместимости)
        'string': 'NEW',
        '': 'NEW',
        None: None
    }

    # Маппинг для communication_type (приводим к UPPERCASE)
    COMMUNICATION_TYPE_MAPPING = {
        'call': 'CALL',
        'meeting': 'MEETING',
        'email': 'EMAIL',
        'message': 'MESSAGE',
        'phone': 'CALL',
        'phone_call': 'CALL',
        'sms': 'MESSAGE',
    }

    # Маппинг для status (приводим к UPPERCASE)
    STATUS_MAPPING_FOR_COMM = {
        'planned': 'PLANNED',
        'completed': 'COMPLETED',
        'cancelled': 'CANCELLED',
        'missed': 'MISSED',
        'plan': 'PLANNED',
        'complete': 'COMPLETED',
        'cancel': 'CANCELLED',
        'miss': 'MISSED',
    }

    def __init__(self):
        pass

    def _validate_contact_status(self, status: Optional[str]) -> Optional[str]:
        """Валидация и нормализация contact_status (UPPERCASE для БД)"""
        if not status:
            return None

        # Приводим к нижнему регистру для поиска в маппинге
        status_lower = str(status).strip().lower()

        # Проверяем, есть ли в маппинге
        if status_lower in self.STATUS_MAPPING:
            normalized = self.STATUS_MAPPING[status_lower]
            if normalized in self.VALID_CONTACT_STATUSES:
                return normalized

        # Проверяем, может быть уже правильное значение (в верхнем регистре)
        if status.upper() in self.VALID_CONTACT_STATUSES:
            return status.upper()

        # Если ничего не подошло, возвращаем NEW по умолчанию
        print(f"⚠️ Недопустимое значение contact_status: '{status}', используется 'NEW'")
        return 'NEW'

    def _validate_communication_type(self, comm_type: str) -> str:
        """Валидация и нормализация communication_type (в UPPERCASE для БД)"""
        if not comm_type:
            raise ValueError("Тип коммуникации обязателен")

        # Приводим к нижнему регистру для поиска в маппинге
        comm_type_lower = str(comm_type).strip().lower()

        # Проверяем в маппинге
        if comm_type_lower in self.COMMUNICATION_TYPE_MAPPING:
            normalized = self.COMMUNICATION_TYPE_MAPPING[comm_type_lower]
            if normalized in self.VALID_COMMUNICATION_TYPES:
                return normalized

        # Проверяем, может быть уже правильное значение (в верхнем регистре)
        if comm_type.upper() in self.VALID_COMMUNICATION_TYPES:
            return comm_type.upper()

        # Если ничего не подошло, ошибка
        raise ValueError(f"Недопустимый тип коммуникации: {comm_type}. "
                         f"Допустимые: {', '.join(self.VALID_COMMUNICATION_TYPES)}")

    def _validate_status(self, status: str) -> str:
        """Валидация статуса коммуникации (UPPERCASE для БД)"""
        if not status:
            return 'COMPLETED'

        # Приводим к нижнему регистру для поиска в маппинге
        status_lower = str(status).strip().lower()

        # Проверяем в маппинге
        if status_lower in self.STATUS_MAPPING_FOR_COMM:
            normalized = self.STATUS_MAPPING_FOR_COMM[status_lower]
            if normalized in self.VALID_STATUSES:
                return normalized

        # Проверяем, может быть уже правильное значение (в верхнем регистре)
        if status.upper() in self.VALID_STATUSES:
            return status.upper()

        # Если ничего не подошло, возвращаем COMPLETED по умолчанию
        print(f"⚠️ Недопустимое значение status: '{status}', используется 'COMPLETED'")
        return 'COMPLETED'

    def get_student_communications(
            self,
            student_id: int,
            user_id: int,
            db: Session,
            limit: int = 50,
            offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Получение всех коммуникаций с абитуриентом"""
        student = db.query(Student).filter(Student.id == student_id).first()
        if not student:
            return []

        if not self._can_access_student(student, user_id, db):
            return []

        communications = db.query(Communication).filter(
            Communication.student_id == student_id
        ).order_by(Communication.date_time.desc()).offset(offset).limit(limit).all()

        return [self._communication_to_dict(c, db) for c in communications]

    def create_communication(
            self,
            communication_data: Dict[str, Any],
            user_id: int,
            db: Session
    ) -> Dict[str, Any]:
        """Создание записи о коммуникации"""
        student_id = communication_data.get('student_id')

        # Проверяем доступ к абитуриенту
        student = db.query(Student).filter(Student.id == student_id).first()
        if not student:
            raise ValueError("Абитуриент не найден")

        if not self._can_access_student(student, user_id, db):
            raise PermissionError("Нет доступа к этому абитуриенту")

        # Валидация communication_type (теперь возвращает UPPERCASE)
        communication_type = communication_data.get('communication_type')
        communication_type = self._validate_communication_type(communication_type)

        # Валидация contact_status
        contact_status = self._validate_contact_status(communication_data.get('contact_status'))

        # Валидация status коммуникации (теперь возвращает UPPERCASE)
        comm_status = self._validate_status(communication_data.get('status', 'completed'))

        # Создаем коммуникацию
        communication = Communication(
            student_id=student_id,
            communication_type=communication_type,
            status=comm_status,
            date_time=communication_data.get('date_time', datetime.utcnow()),
            duration_minutes=communication_data.get('duration_minutes'),
            notes=communication_data.get('notes'),
            created_by=user_id,
            created_at=datetime.utcnow()
        )

        db.add(communication)

        # Обновляем статус контакта абитуриента
        if contact_status:
            old_status = student.contact_status
            student.contact_status = contact_status
            print(f"📝 Обновлен статус контакта студента {student_id}: {old_status} -> {contact_status}")

        student.last_communication_date = datetime.utcnow()
        student.updated_at = datetime.utcnow()

        try:
            db.commit()
            db.refresh(communication)
        except Exception as e:
            db.rollback()
            print(f"❌ Ошибка при сохранении коммуникации: {e}")
            raise ValueError(f"Ошибка базы данных: {str(e)}")

        return self._communication_to_dict(communication, db)

    def update_communication(
            self,
            communication_id: int,
            update_data: Dict[str, Any],
            user_id: int,
            db: Session
    ) -> Optional[Dict[str, Any]]:
        """Обновление записи о коммуникации"""
        communication = db.query(Communication).filter(
            Communication.id == communication_id
        ).first()

        if not communication:
            return None

        # Проверяем доступ
        if communication.created_by != user_id:
            user = db.query(User).filter(User.id == user_id).first()
            if user.role != 'admin':
                raise PermissionError("Можно редактировать только свои записи")

        # Обновляем поля с валидацией
        for field, value in update_data.items():
            if value is not None and hasattr(communication, field):
                # Валидация для contact_status
                if field == 'contact_status' and value:
                    value = self._validate_contact_status(value)
                    if communication.student:
                        communication.student.contact_status = value
                        communication.student.last_communication_date = datetime.utcnow()
                        communication.student.updated_at = datetime.utcnow()
                    continue

                # Валидация для communication_type
                if field == 'communication_type' and value:
                    value = self._validate_communication_type(value)

                # Валидация для status
                if field == 'status' and value:
                    value = self._validate_status(value)

                setattr(communication, field, value)

        communication.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(communication)

        return self._communication_to_dict(communication, db)

    def delete_communication(self, communication_id: int, user_id: int, db: Session) -> bool:
        """Удаление записи о коммуникации"""
        communication = db.query(Communication).filter(
            Communication.id == communication_id
        ).first()

        if not communication:
            return False

        # Проверяем доступ
        if communication.created_by != user_id:
            user = db.query(User).filter(User.id == user_id).first()
            if user.role != 'admin':
                raise PermissionError("Можно удалять только свои записи")

        db.delete(communication)
        db.commit()
        return True

    def get_communication_stats(
            self,
            user_id: int,
            db: Session,
            days_back: int = 30
    ) -> Dict[str, Any]:
        """Получение статистики по коммуникациям"""
        from datetime import datetime, timedelta

        since_date = datetime.utcnow() - timedelta(days=days_back)

        # Получаем доступных абитуриентов
        available_students = self._get_available_student_ids(user_id, db)

        # Базовый запрос
        query = db.query(Communication).filter(
            Communication.student_id.in_(available_students),
            Communication.created_at >= since_date
        )

        total = query.count()

        # Статистика по типам (используем UPPERCASE для БД)
        by_type = {}
        for comm_type in self.VALID_COMMUNICATION_TYPES:
            count = query.filter(Communication.communication_type == comm_type).count()
            if count > 0:
                by_type[comm_type.lower()] = count  # для ответа в нижнем регистре

        # Статистика по статусам контактов
        contact_status_stats = {}
        students_with_comms = db.query(Student).filter(
            Student.id.in_(available_students),
            Student.last_communication_date >= since_date
        ).all()

        for student in students_with_comms:
            if student.contact_status:
                status = student.contact_status
                contact_status_stats[status] = contact_status_stats.get(status, 0) + 1

        # Последние коммуникации
        recent = query.order_by(Communication.created_at.desc()).limit(10).all()

        return {
            'total_communications': total,
            'by_type': by_type,
            'contact_status_distribution': contact_status_stats,
            'recent_communications': [self._communication_to_dict(c, db) for c in recent],
            'period_days': days_back
        }

    def _can_access_student(self, student: Student, user_id: int, db: Session) -> bool:
        """Проверка доступа к абитуриенту"""
        user = db.query(User).filter(User.id == user_id).first()

        if user.role == 'admin':
            return True

        if student.kurator_id == user_id:
            return True

        if user.assigned_departments and student.department_id in user.assigned_departments:
            return True

        return False

    def _get_available_student_ids(self, user_id: int, db: Session) -> List[int]:
        """Получение списка ID доступных абитуриентов"""
        user = db.query(User).filter(User.id == user_id).first()

        query = db.query(Student.id)

        if user.role == 'admin':
            return [id for (id,) in query.all()]

        if user.assigned_departments:
            query = query.filter(Student.department_id.in_(user.assigned_departments))
        else:
            query = query.filter(Student.kurator_id == user_id)

        return [id for (id,) in query.all()]

    def _communication_to_dict(self, comm: Communication, db: Session) -> Dict[str, Any]:
        """Конвертация коммуникации в словарь"""
        if not comm:
            return None

        creator = db.query(User).filter(User.id == comm.created_by).first()

        # Получаем актуальный статус контакта студента
        contact_status = None
        student_name = None
        if comm.student:
            contact_status = comm.student.contact_status
            student_name = comm.student.full_name

        # Преобразуем communication_type в нижний регистр для ответа API
        comm_type = comm.communication_type.value if comm.communication_type else None
        if comm_type:
            comm_type = comm_type.lower()

        # Преобразуем status в нижний регистр для ответа API
        comm_status = comm.status.value if comm.status else None
        if comm_status:
            comm_status = comm_status.lower()

        return {
            'id': comm.id,
            'student_id': comm.student_id,
            'student_name': student_name,
            'communication_type': comm_type,
            'status': comm_status,
            'date_time': comm.date_time.isoformat() if comm.date_time else None,
            'duration_minutes': comm.duration_minutes,
            'notes': comm.notes,
            'contact_status': contact_status,
            'created_by': comm.created_by,
            'created_by_name': creator.full_name if creator else None,
            'created_at': comm.created_at.isoformat() if comm.created_at else None
        }
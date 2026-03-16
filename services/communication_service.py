# services/communication_service.py
from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session

from database.schema import Communication, Student, User


class CommunicationService:
    """Сервис для управления коммуникациями с абитуриентами"""

    def __init__(self):
        pass

    def get_student_communications(
            self,
            student_id: int,
            user_id: int,
            db: Session,
            limit: int = 50,
            offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Получение всех коммуникаций с абитуриентом"""
        # Проверяем доступ к абитуриенту
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

        # Создаем коммуникацию
        communication = Communication(
            student_id=student_id,
            communication_type=communication_data['communication_type'],
            status=communication_data.get('status', 'completed'),
            date_time=communication_data.get('date_time', datetime.utcnow()),
            duration_minutes=communication_data.get('duration_minutes'),
            notes=communication_data.get('notes'),
            created_by=user_id,
            created_at=datetime.utcnow()
        )

        db.add(communication)

        # Обновляем статус контакта абитуриента
        if communication_data.get('contact_status'):
            student.contact_status = communication_data['contact_status']
        student.last_communication_date = datetime.utcnow()

        db.commit()
        db.refresh(communication)

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

        # Обновляем поля
        for field, value in update_data.items():
            if hasattr(communication, field) and value is not None:
                setattr(communication, field, value)

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

        # Статистика по типам
        by_type = {}
        for comm_type in ['call', 'meeting', 'email', 'message']:
            count = query.filter(Communication.communication_type == comm_type).count()
            if count > 0:
                by_type[comm_type] = count

        # Последние коммуникации
        recent = query.order_by(Communication.created_at.desc()).limit(10).all()

        return {
            'total_communications': total,
            'by_type': by_type,
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

        return {
            'id': comm.id,
            'student_id': comm.student_id,
            'communication_type': comm.communication_type.value if comm.communication_type else None,
            'status': comm.status.value if comm.status else None,
            'date_time': comm.date_time,
            'duration_minutes': comm.duration_minutes,
            'notes': comm.notes,
            'created_by': comm.created_by,
            'created_by_name': creator.full_name if creator else None,
            'created_at': comm.created_at
        }
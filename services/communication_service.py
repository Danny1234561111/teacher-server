# services/communication_service.py
import os
import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc, asc, func, text

from services.database_service import DatabaseService
from database.schema import Communication, Student, User
from database.database import get_db


class CommunicationService:
    """Сервис для управления историей коммуникаций со студентами"""

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(CommunicationService, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self.database_service = DatabaseService()
            self._initialized = True

    def create_communication(
            self,
            communication_data: Dict[str, Any],
            user_id: str
    ) -> str:
        """Создание записи о коммуникации"""
        try:
            return self.database_service.create_communication(communication_data, user_id)
        except Exception as e:
            raise ValueError(f"Ошибка создания коммуникации: {str(e)}")

    def get_communications_by_student(
            self,
            student_id: str,
            user_id: str,
            limit: int = 50,
            offset: int = 0,
            communication_type: Optional[str] = None,
            status: Optional[str] = None,
            date_from: Optional[datetime] = None,
            date_to: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """Получение истории коммуникаций со студентом"""
        try:
            return self.database_service.get_communications_by_student(
                student_id=student_id,
                user_id=user_id,
                limit=limit,
                offset=offset
            )
        except Exception as e:
            return []

    def get_communications_by_teacher(
            self,
            teacher_id: str,
            limit: int = 100,
            offset: int = 0,
            important_only: bool = False
    ) -> List[Dict[str, Any]]:
        """Получение всех коммуникаций преподавателя"""
        try:
            return self.database_service.get_communications_by_teacher(
                teacher_id=teacher_id,
                limit=limit,
                offset=offset
            )
        except Exception as e:
            return []

    def update_communication(
            self,
            communication_id: str,
            update_data: Dict[str, Any],
            user_id: str
    ) -> bool:
        """Обновление записи о коммуникации"""
        try:
            return self.database_service.update_communication(
                communication_id=communication_id,
                update_data=update_data,
                user_id=user_id
            )
        except Exception as e:
            return False

    def delete_communication(self, communication_id: str, user_id: str) -> bool:
        """Удаление записи о коммуникации"""
        try:
            return self.database_service.delete_communication(communication_id, user_id)
        except Exception as e:
            return False

    def get_communication_stats(
            self,
            teacher_id: str,
            days_back: int = 30
    ) -> Dict[str, Any]:
        """Получение статистики по коммуникациям"""
        try:
            return self.database_service.get_communication_stats(teacher_id, days_back)
        except Exception as e:
            return {
                'total_communications': 0,
                'by_type': {},
                'by_status': {},
                'recent_communications': [],
                'upcoming_actions': []
            }
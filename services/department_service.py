# services/department_service.py
import os
from typing import List, Dict, Any, Optional
from datetime import datetime
from firebase_admin import firestore


class DepartmentService:
    """Сервис для работы с направлениями и специальностями"""

    def __init__(self, firestore_service):
        self.firestore = firestore_service
        self._db = firestore_service._db

    def create_department(self, department_data: Dict[str, Any]) -> str:
        """Создание направления (факультета)"""
        try:
            department_id = f"dept_{department_data['code']}"

            department_doc = {
                'id': department_id,
                'code': department_data['code'],
                'name': department_data['name'],
                'faculty': department_data['faculty'],
                'description': department_data.get('description'),
                'is_active': True,
                'created_at': firestore.SERVER_TIMESTAMP,
                'updated_at': firestore.SERVER_TIMESTAMP
            }

            doc_ref = self._db.collection('departments').document(department_id)
            doc_ref.set(department_doc)

            return department_id
        except Exception as e:
            raise ValueError(f"Ошибка создания направления: {str(e)}")

    def create_speciality(self, speciality_data: Dict[str, Any]) -> str:
        """Создание специальности"""
        try:
            # Проверяем существование направления
            dept_ref = self._db.collection('departments').document(speciality_data['department_id'])
            if not dept_ref.get().exists:
                raise ValueError(f"Направление {speciality_data['department_id']} не найдено")

            speciality_id = f"spec_{speciality_data['code']}"

            speciality_doc = {
                'id': speciality_id,
                'code': speciality_data['code'],
                'name': speciality_data['name'],
                'department_id': speciality_data['department_id'],
                'study_duration': speciality_data.get('study_duration', 4),
                'description': speciality_data.get('description'),
                'is_active': True,
                'created_at': firestore.SERVER_TIMESTAMP,
                'updated_at': firestore.SERVER_TIMESTAMP
            }

            doc_ref = self._db.collection('specialities').document(speciality_id)
            doc_ref.set(speciality_doc)

            return speciality_id
        except Exception as e:
            raise ValueError(f"Ошибка создания специальности: {str(e)}")
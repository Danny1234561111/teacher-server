import pandas as pd
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from io import BytesIO
from sqlalchemy.orm import Session
from datetime import datetime

from database.database import get_db
from database.schema import (
    Student, StudentApplication, Profile, Speciality, Department,
    StudentStatus, ContactStatus, MeetingStatus, CallStatus,
    DecisionStatus, DocumentsStatus, StudyForm, StudyBasis,
    ApplicationStatus, User, UserRole
)
from services.excel_import_service import ExcelImportService
from services.auth_service import AuthService

router = APIRouter(prefix="/excel-import", tags=["Excel Import"])
security = HTTPBearer()
auth_service = AuthService()


# ===== МОДЕЛИ =====

class ExcelImportResponse(BaseModel):
    """Ответ на загрузку Excel файла"""
    success: bool
    total_rows: int
    created_students: int
    updated_students: int
    created_applications: int
    errors: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []
    message: str


# ===== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====

async def get_current_user(
        credentials: HTTPAuthorizationCredentials = Depends(security),
        db: Session = Depends(get_db)
) -> User:
    """Получение текущего пользователя"""
    token = credentials.credentials
    user_data = auth_service.get_user_by_token(token, db)

    user = db.query(User).filter(User.id == user_data['id']).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    return user


# ===== ЭНДПОИНТЫ =====

@router.post("/upload", response_model=ExcelImportResponse)
async def import_students_from_excel(
        file: UploadFile = File(..., description="Excel файл с данными абитуриентов"),
        create_missing_profiles: bool = False,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    Импорт абитуриентов из Excel файла.

    Поддерживаемые колонки в Excel:
    - ФИО / full_name (обязательно)
    - Телефон / phone
    - Профиль / profile_name (название образовательной программы)
    - Баллы / score (сумма баллов ЕГЭ)
    - Приоритет / priority (от 1 до 10)
    - Форма обучения / study_form (Очная/Заочная/Очно-заочная)
    - Основа обучения / study_basis (Бюджетная/Платная/Целевая)
    - ID поступающего / russian_student_id (уникальный идентификатор)

    Пример структуры Excel:
    | ФИО | Телефон | Профиль | Баллы | Приоритет | Форма обучения | Основа обучения |
    """
    try:
        # Проверяем расширение файла
        if not file.filename.endswith(('.xlsx', '.xls')):
            raise HTTPException(
                status_code=400,
                detail=f"Неподдерживаемый формат файла '{file.filename}'. Загрузите файл Excel (.xlsx или .xls)"
            )

        # Читаем Excel файл
        contents = await file.read()

        try:
            df = pd.read_excel(BytesIO(contents))
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Ошибка при чтении Excel файла: {str(e)}")

        if df.empty:
            raise HTTPException(status_code=400, detail="Excel файл пуст")

        # Создаем сервис и импортируем данные
        import_service = ExcelImportService(db, current_user.id)

        result = await import_service.import_from_dataframe(
            df=df,
            create_missing_profiles=create_missing_profiles
        )

        return ExcelImportResponse(
            success=result['success'],
            total_rows=result['total_rows'],
            created_students=result['created_students'],
            updated_students=result['updated_students'],
            created_applications=result['created_applications'],
            errors=result['errors'],
            warnings=result['warnings'],
            message=result['message']
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Внутренняя ошибка сервера: {str(e)}")


@router.post("/upload-with-mapping")
async def get_column_mapping_example():
    """
    Возвращает пример соответствия колонок в Excel
    """
    return {
        "required_columns": ["ФИО"],
        "optional_columns": {
            "Телефон": "phone",
            "Профиль": "profile_name",
            "Баллы": "score",
            "Приоритет": "priority",
            "Форма обучения": "study_form",
            "Основа обучения": "study_basis",
            "ID поступающего": "russian_student_id",
            "Почта": "email"
        },
        "study_form_options": ["Очная", "Заочная", "Очно-заочная"],
        "study_basis_options": ["Бюджетная", "Платная", "Целевая"],
        "example_data": [
            {
                "ФИО": "Иванов Иван Иванович",
                "Телефон": "+79123456789",
                "Профиль": "Отечественная филология",
                "Баллы": 275,
                "Приоритет": 1,
                "Форма обучения": "Очная",
                "Основа обучения": "Бюджетная"
            }
        ]
    }
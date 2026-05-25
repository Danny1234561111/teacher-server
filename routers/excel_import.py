import pandas as pd
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Set
from io import BytesIO
from sqlalchemy.orm import Session
from database.database import get_db
from database.schema import User, Student
from routers.auth import get_current_user
from services.auth_service import AuthService
from services.excel_import_service import ExcelImportService

router = APIRouter()
security = HTTPBearer()
auth_service = AuthService()


class ExcelImportResponse(BaseModel):
    success: bool
    total_rows: int
    created_students: int
    updated_students: int
    created_applications: int
    errors: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []
    message: str
    duplicates_found: Optional[List[Dict[str, Any]]] = None


@router.post("/upload", response_model=ExcelImportResponse)
async def import_students_from_excel(
        file: UploadFile = File(..., description="Excel файл с данными абитуриентов"),
        create_missing_profiles: bool = Form(False, description="Создавать ли отсутствующие профили"),
        duplicate_strategy: str = Form("skip",
                                       description="Стратегия обработки дубликатов: 'skip', 'replace_all', 'replace_selected'"),
        replace_ids: Optional[str] = Form(None, description="JSON строка со списком ID для замены"),
        credentials: HTTPAuthorizationCredentials = Depends(security),
        db: Session = Depends(get_db)
):
    try:
        # Получаем текущего пользователя по токену
        token = credentials.credentials
        user_data = auth_service.get_user_by_token(token, db)
        current_user = db.query(User).filter(User.id == user_data['id']).first()

        if not current_user:
            raise HTTPException(status_code=401, detail="Пользователь не найден")

        # Проверка формата файла
        if not file.filename.endswith(('.xlsx', '.xls')):
            raise HTTPException(
                status_code=400,
                detail=f"Неподдерживаемый формат файла '{file.filename}'. Загрузите файл Excel (.xlsx или .xls)"
            )

        # Чтение файла в DataFrame
        contents = await file.read()
        try:
            df = pd.read_excel(BytesIO(contents))
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Ошибка при чтении Excel файла: {str(e)}")

        if df.empty:
            raise HTTPException(status_code=400, detail="Excel файл пуст")

        # Для проверки дубликатов создаем временный сервис и нормализуем колонки
        temp_service = ExcelImportService(db, current_user.id)
        df_normalized = temp_service._normalize_columns(df.copy())

        # Получаем ID из нормализованного DataFrame для проверки дубликатов
        if 'russian_student_id' in df_normalized.columns:
            try:
                # Пробуем получить ID как строки (для универсальности)
                ids_from_file = []
                for val in df_normalized['russian_student_id'].dropna():
                    try:
                        # Очищаем строку от нецифровых символов
                        if isinstance(val, str):
                            cleaned = ''.join(filter(str.isdigit, val))
                            if cleaned:
                                ids_from_file.append(int(cleaned))
                        else:
                            ids_from_file.append(int(float(val)))
                    except (ValueError, TypeError):
                        continue

                ids_from_file = list(set(ids_from_file))  # Уникальные значения

                # Проверяем существующих студентов
                existing_students = db.query(Student).filter(Student.russian_student_id.in_(ids_from_file)).all()

                duplicates_found = [
                    {"id": s.russian_student_id, "full_name": s.full_name}
                    for s in existing_students
                ]
            except Exception as e:
                # Если не удалось получить ID, продолжаем без проверки дубликатов
                duplicates_found = []
        else:
            duplicates_found = []

        # Парсим replace_ids из JSON строки
        replace_ids_set = set()
        if replace_ids:
            import json
            try:
                replace_ids_list = json.loads(replace_ids)
                replace_ids_set = set(replace_ids_list)
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Неверный формат replace_ids. Ожидается JSON массив.")

        # Стратегия SKIP: возвращаем ошибку со списком дублей
        if duplicate_strategy == "skip" and duplicates_found:
            return ExcelImportResponse(
                success=False,
                total_rows=len(df),
                created_students=0,
                updated_students=0,
                created_applications=0,
                errors=[
                    {"row": 0, "error": "Найдены дубликаты. Используйте стратегию замены или выберите игнорирование."}
                ],
                warnings=[],
                message="Импорт прерван: найдены дубликаты.",
                duplicates_found=duplicates_found
            )

        # Стратегия REPLACE_SELECTED: проверяем список ID на замену
        if duplicate_strategy == "replace_selected":
            if not replace_ids_set:
                raise HTTPException(
                    status_code=400,
                    detail="Для стратегии 'replace_selected' необходимо указать список replace_ids"
                )

            ids_of_duplicates_in_file = [s.russian_student_id for s in existing_students]
            not_allowed_to_replace = set(ids_of_duplicates_in_file) - replace_ids_set

            if not_allowed_to_replace:
                details = [f"ID {id_}" for id_ in not_allowed_to_replace]
                return ExcelImportResponse(
                    success=False,
                    total_rows=len(df),
                    created_students=0,
                    updated_students=0,
                    created_applications=0,
                    errors=[{
                        "row": 0,
                        "error": f"Найдены дубликаты. Не все из них выбраны для замены. {', '.join(details)}"
                    }],
                    warnings=[],
                    message="Импорт прерван: не все дубликаты выбраны для замены.",
                    duplicates_found=duplicates_found
                )

        # Запускаем импорт (вся логика нормализации и проверки внутри)
        import_service = ExcelImportService(db, current_user.id)

        result = await import_service.import_from_dataframe(
            df=df,
            create_missing_profiles=create_missing_profiles,
            duplicate_strategy=duplicate_strategy,
            replace_ids=replace_ids_set
        )

        return ExcelImportResponse(
            success=result['success'],
            total_rows=result['total_rows'],
            created_students=result['created_students'],
            updated_students=result['updated_students'],
            created_applications=result['created_applications'],
            errors=result['errors'],
            warnings=result['warnings'],
            message=result['message'],
            duplicates_found=duplicates_found if duplicates_found else None
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Внутренняя ошибка сервера при импорте: {str(e)}")
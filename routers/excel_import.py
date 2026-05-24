import pandas as pd
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
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

class ExcelImportRequest(BaseModel):
    file: UploadFile = Field(..., description="Excel файл с данными абитуриентов")
    create_missing_profiles: bool = Field(False, description="Создавать ли отсутствующие профили")
    duplicate_strategy: str = Field(
        default="skip",
        description="Стратегия обработки дубликатов: 'skip', 'replace_all', 'replace_selected'"
    )
    replace_ids: Optional[List[int]] = Field(
        None,
        description="Список ID поступающих для замены (требуется при duplicate_strategy='replace_selected')"
    )


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



@router.post("/excel-import/upload", response_model=ExcelImportResponse)
async def import_students_from_excel(
        request: ExcelImportRequest,
        current_user: User = Depends(get_current_user),  # Используем вашу функцию авторизации
        db: Session = Depends(get_db)
):
    try:
        file = request.file

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
        df.columns = df.columns.str.strip().str.lower()
        if 'russian_student_id' not in df.columns and not any('id' in col and 'student' in col for col in df.columns):
            return ExcelImportResponse(
                success=False,
                total_rows=len(df),
                created_students=0,
                updated_students=0,
                created_applications=0,
                errors=[{"row": 0, "error": "Отсутствует колонка с ID поступающего (russian_student_id)"}],
                warnings=[],
                message="Ошибка: в файле нет обязательных колонок"
            )
        try:
            ids_from_file = df['russian_student_id'].dropna().astype(str).unique().tolist()
        except KeyError:
            # Если колонка называется иначе, пробуем найти ее и извлечь значения
            id_col = next((col for col in df.columns if 'id' in col and 'student' in col), None)
            if id_col:
                ids_from_file = df[id_col].dropna().astype(str).unique().tolist()
            else:
                return ExcelImportResponse(
                    success=False,
                    total_rows=len(df),
                    created_students=0,
                    updated_students=0,
                    created_applications=0,
                    errors=[{"row": 0, "error": "Не удалось определить колонку с ID поступающего"}],
                    warnings=[],
                    message="Ошибка: не удалось определить колонку с ID"
                )
        existing_students = db.query(Student).filter(Student.russian_student_id.in_(ids_from_file)).all()

        duplicates_found = [
            {"id": s.russian_student_id, "full_name": s.full_name}
            for s in existing_students
        ]

        # Стратегия SKIP: возвращаем ошибку со списком дублей
        if request.duplicate_strategy == "skip" and duplicates_found:
            return ExcelImportResponse(
                success=False,
                total_rows=len(df),
                created_students=0,
                updated_students=0,
                created_applications=0,
                errors=[
                    {"row": 0, "error": "Найдены дубликаты. Используйте стратегию замены или выберите игнорирование."}],
                message="Импорт прерван: найдены дубликаты.",
                duplicates_found=duplicates_found
            )

        # Стратегия REPLACE_SELECTED: проверяем список ID на замену
        if request.duplicate_strategy == "replace_selected":
            if not request.replace_ids:
                raise HTTPException(status_code=400,
                                    detail="Для стратегии 'replace_selected' необходимо указать список replace_ids")

            ids_of_duplicates_in_file = [s.russian_student_id for s in existing_students]
            not_allowed_to_replace = set(ids_of_duplicates_in_file) - set(request.replace_ids)

            if not_allowed_to_replace:
                details = [f"ID {id_}" for id_ in not_allowed_to_replace]
                return ExcelImportResponse(
                    success=False,
                    total_rows=len(df),
                    created_students=0,
                    updated_students=0,
                    created_applications=0,
                    errors=[{"row": 0,
                             "error": f"Найдены дубликаты. Не все из них выбраны для замены. {', '.join(details)}"}],
                    message="Импорт прерван: не все дубликаты выбраны для замены.",
                    duplicates_found=duplicates_found
                )
        import_service = ExcelImportService(db, current_user.id)

        result = await import_service.import_from_dataframe(
            df=df,
            create_missing_profiles=request.create_missing_profiles,
            duplicate_strategy=request.duplicate_strategy,
            replace_ids=set(request.replace_ids) if request.replace_ids else set()
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
        raise  # Пробрасываем HTTP-ошибки дальше
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Внутренняя ошибка сервера при импорте: {str(e)}")
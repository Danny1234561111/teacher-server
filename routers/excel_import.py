# api/routes/excel_import.py
import pandas as pd
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import List, Optional, Dict, Any, Set
from io import BytesIO
from sqlalchemy.orm import Session
import json

from database.database import get_db
from database.schema import User
from services.excel_import_service import ExcelImportService
from services.auth_service import AuthService

router = APIRouter(tags=["Excel Import"])
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


async def get_current_user_mobile(
        credentials: HTTPAuthorizationCredentials = Depends(security),
        db: Session = Depends(get_db)
) -> User:
    token = credentials.credentials
    user_data = auth_service.get_user_by_token(token, db)
    user = db.query(User).filter(User.id == user_data['id']).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return user


async def get_current_user_web(
        request: Request,
        db: Session = Depends(get_db)
) -> User:
    user_data = auth_service.get_current_user_web(request, db)
    user = db.query(User).filter(User.id == user_data['id']).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return user


@router.post("/mobile/upload", response_model=ExcelImportResponse)
async def mobile_import_students_from_excel(
        file: UploadFile = File(..., description="Excel файл с данными абитуриентов"),
        create_missing_profiles: bool = Form(False),
        duplicate_strategy: str = Form("skip", description="skip, replace_all, replace_selected"),
        replace_ids: Optional[str] = Form(None, description='JSON строка со списком ID, например "[123, 456]"'),
        current_user: User = Depends(get_current_user_mobile),
        db: Session = Depends(get_db)
):
    try:
        if not file.filename.endswith(('.xlsx', '.xls')):
            raise HTTPException(status_code=400, detail=f"Неподдерживаемый формат файла")

        contents = await file.read()
        try:
            df = pd.read_excel(BytesIO(contents))
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Ошибка при чтении Excel файла: {str(e)}")

        if df.empty:
            raise HTTPException(status_code=400, detail="Excel файл пуст")

        replace_ids_set = set()
        if replace_ids:
            try:
                replace_ids_list = json.loads(replace_ids)
                replace_ids_set = set(replace_ids_list)
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Неверный формат replace_ids")

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
            duplicates_found=result.get('duplicates_found')
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка: {str(e)}")


@router.post("/web/upload", response_model=ExcelImportResponse)
async def web_import_students_from_excel(
        request: Request,
        file: UploadFile = File(..., description="Excel файл с данными абитуриентов"),
        create_missing_profiles: bool = Form(False),
        duplicate_strategy: str = Form("skip", description="skip, replace_all, replace_selected"),
        replace_ids: Optional[str] = Form(None, description='JSON строка со списком ID, например "[123, 456]"'),
        db: Session = Depends(get_db)
):
    try:
        current_user = await get_current_user_web(request, db)

        if not file.filename.endswith(('.xlsx', '.xls')):
            raise HTTPException(status_code=400, detail=f"Неподдерживаемый формат файла")

        contents = await file.read()
        try:
            df = pd.read_excel(BytesIO(contents))
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Ошибка при чтении Excel файла: {str(e)}")

        if df.empty:
            raise HTTPException(status_code=400, detail="Excel файл пуст")

        replace_ids_set = set()
        if replace_ids:
            try:
                replace_ids_list = json.loads(replace_ids)
                replace_ids_set = set(replace_ids_list)
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Неверный формат replace_ids")

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
            duplicates_found=result.get('duplicates_found')
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка: {str(e)}")
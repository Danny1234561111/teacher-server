# api/routes/students.py
from fastapi import APIRouter, HTTPException, Depends, status, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from sqlalchemy.orm import Session

from services.student_service import StudentService
from services.communication_service import CommunicationService
from services.auth_service import AuthService
from database.database import get_db
from database.schema import User

router = APIRouter(prefix="/api/students", tags=["Students"])
security = HTTPBearer()
auth_service = AuthService()
student_service = StudentService()
communication_service = CommunicationService()


# ===== МОДЕЛИ ДЛЯ АБИТУРИЕНТОВ =====

class StudentCreate(BaseModel):
    """Создание абитуриента - только самое необходимое"""
    full_name: str = Field(..., min_length=2, description="ФИО абитуриента")
    russian_student_id: Optional[int] = Field(None, description="Российский ID студента (7 цифр)")
    phone: Optional[str] = Field(None, description="Номер телефона")


class StudentUpdate(BaseModel):
    """Обновление абитуриента - можно обновлять любые поля"""
    full_name: Optional[str] = None
    russian_student_id: Optional[int] = None
    phone: Optional[str] = None
    additional_contacts: Optional[dict] = None
    prior_contact: Optional[str] = None
    department_id: Optional[int] = None
    speciality_id: Optional[int] = None
    profile_id: Optional[int] = None
    study_level: Optional[str] = None
    study_form: Optional[str] = None
    study_basis: Optional[str] = None
    status: Optional[str] = None
    application_status: Optional[str] = None
    contact_status: Optional[str] = None
    total_score: Optional[int] = None


class StudentResponse(BaseModel):
    """Ответ с данными абитуриента"""
    id: int
    russian_student_id: Optional[int]
    full_name: str
    phone: Optional[str]
    department_name: Optional[str]
    speciality_name: Optional[str]
    profile_name: Optional[str]
    status: Optional[str]
    application_status: Optional[str]
    contact_status: Optional[str]
    total_score: Optional[int]
    last_communication: Optional[datetime]
    kurator_id: Optional[int]


class StudentListResponse(BaseModel):
    total: int
    students: List[StudentResponse]


# ===== МОДЕЛИ ДЛЯ КОММУНИКАЦИЙ =====

class CommunicationCreate(BaseModel):
    """Создание записи о коммуникации"""
    communication_type: str = Field(..., pattern="^(call|meeting|email|message)$")
    status: Optional[str] = "completed"
    date_time: Optional[datetime] = None
    duration_minutes: Optional[int] = None
    notes: Optional[str] = None
    contact_status: Optional[str] = None  # Новый статус контакта для студента


class CommunicationUpdate(BaseModel):
    """Обновление записи о коммуникации"""
    communication_type: Optional[str] = Field(None, pattern="^(call|meeting|email|message)$")
    status: Optional[str] = None
    date_time: Optional[datetime] = None
    duration_minutes: Optional[int] = None
    notes: Optional[str] = None


class CommunicationResponse(BaseModel):
    """Ответ с данными о коммуникации"""
    id: int
    student_id: int
    student_name: Optional[str]
    communication_type: str
    status: str
    date_time: datetime
    duration_minutes: Optional[int]
    notes: Optional[str]
    created_by_name: Optional[str]
    created_at: datetime


class CommunicationStatsResponse(BaseModel):
    """Статистика по коммуникациям"""
    total_communications: int
    by_type: dict
    recent_communications: List[CommunicationResponse]
    period_days: int


# ===== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====

async def get_current_user(
        credentials: HTTPAuthorizationCredentials = Depends(security),
        db: Session = Depends(get_db)
) -> User:
    token = credentials.credentials
    user_data = auth_service.get_user_by_token(token, db)

    user = db.query(User).filter(User.id == user_data['id']).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    return user


# ===== ЭНДПОИНТЫ ДЛЯ АБИТУРИЕНТОВ =====

@router.get("", response_model=StudentListResponse)
async def get_students(
        skip: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=500),
        status: Optional[str] = None,
        department_id: Optional[int] = None,
        speciality_id: Optional[int] = None,
        search: Optional[str] = None,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """Получение списка доступных абитуриентов"""
    students = student_service.get_available_students(
        user_id=current_user.id,
        db=db,
        skip=skip,
        limit=limit,
        status=status,
        department_id=department_id,
        speciality_id=speciality_id,
        search=search
    )

    return {
        "total": len(students),
        "students": students
    }


@router.get("/{student_id}", response_model=StudentResponse)
async def get_student(
        student_id: int,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """Получение абитуриента по ID"""
    student = student_service.get_student_by_id(
        student_id=student_id,
        user_id=current_user.id,
        db=db
    )

    if not student:
        raise HTTPException(status_code=404, detail="Абитуриент не найден или доступ запрещен")

    return student


@router.post("", response_model=StudentResponse, status_code=201)
async def create_student(
        student_data: StudentCreate,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """Создание нового абитуриента (только ФИО, ID и телефон)"""
    try:
        return student_service.create_student(
            student_data.dict(exclude_unset=True),
            user_id=current_user.id,
            db=db
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{student_id}", response_model=StudentResponse)
async def update_student(
        student_id: int,
        student_data: StudentUpdate,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """Обновление данных абитуриента"""
    try:
        student = student_service.update_student(
            student_id=student_id,
            update_data=student_data.dict(exclude_unset=True),
            user_id=current_user.id,
            db=db
        )

        if not student:
            raise HTTPException(status_code=404, detail="Абитуриент не найден")

        return student
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.delete("/{student_id}")
async def delete_student(
        student_id: int,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """Удаление абитуриента (только для админа)"""
    try:
        deleted = student_service.delete_student(
            student_id=student_id,
            user_id=current_user.id,
            db=db
        )

        if not deleted:
            raise HTTPException(status_code=404, detail="Абитуриент не найден")

        return {"message": "Абитуриент успешно удален"}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


# ===== ЭНДПОИНТЫ ДЛЯ КОММУНИКАЦИЙ (ВНУТРИ СТУДЕНТОВ) =====

@router.get("/{student_id}/communications", response_model=List[CommunicationResponse])
async def get_student_communications(
        student_id: int,
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """Получение истории коммуникаций с абитуриентом"""
    # Проверяем доступ к абитуриенту
    student = student_service.get_student_by_id(
        student_id=student_id,
        user_id=current_user.id,
        db=db
    )

    if not student:
        raise HTTPException(status_code=404, detail="Абитуриент не найден или доступ запрещен")

    communications = communication_service.get_student_communications(
        student_id=student_id,
        user_id=current_user.id,
        db=db,
        limit=limit,
        offset=offset
    )

    return communications


@router.post("/{student_id}/communications", response_model=CommunicationResponse, status_code=201)
async def create_student_communication(
        student_id: int,
        comm_data: CommunicationCreate,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """Создание записи о коммуникации с абитуриентом"""
    # Проверяем доступ к абитуриенту
    student = student_service.get_student_by_id(
        student_id=student_id,
        user_id=current_user.id,
        db=db
    )

    if not student:
        raise HTTPException(status_code=404, detail="Абитуриент не найден или доступ запрещен")

    try:
        # Добавляем student_id в данные
        full_data = comm_data.dict(exclude_unset=True)
        full_data['student_id'] = student_id

        return communication_service.create_communication(
            communication_data=full_data,
            user_id=current_user.id,
            db=db
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.put("/communications/{comm_id}", response_model=CommunicationResponse)
async def update_communication(
        comm_id: int,
        comm_data: CommunicationUpdate,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """Обновление записи о коммуникации"""
    try:
        communication = communication_service.update_communication(
            communication_id=comm_id,
            update_data=comm_data.dict(exclude_unset=True),
            user_id=current_user.id,
            db=db
        )

        if not communication:
            raise HTTPException(status_code=404, detail="Коммуникация не найдена")

        return communication
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.delete("/communications/{comm_id}")
async def delete_communication(
        comm_id: int,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """Удаление записи о коммуникации"""
    try:
        deleted = communication_service.delete_communication(
            communication_id=comm_id,
            user_id=current_user.id,
            db=db
        )

        if not deleted:
            raise HTTPException(status_code=404, detail="Коммуникация не найдена")

        return {"message": "Коммуникация успешно удалена"}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.get("/communications/stats", response_model=CommunicationStatsResponse)
async def get_communication_stats(
        days_back: int = Query(30, ge=1, le=365),
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """Получение статистики по коммуникациям"""
    return communication_service.get_communication_stats(
        user_id=current_user.id,
        db=db,
        days_back=days_back
    )
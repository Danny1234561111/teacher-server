from fastapi import APIRouter, HTTPException, Depends, status, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime
from sqlalchemy.orm import Session

from services.student_service import StudentService
from services.communication_service import CommunicationService
from services.auth_service import AuthService
from database.database import get_db
from database.schema import User, Department, Speciality, Profile, StudentApplication, ApplicationStatus

router = APIRouter(prefix="/api/students", tags=["Students"])
security = HTTPBearer()
auth_service = AuthService()
student_service = StudentService()
communication_service = CommunicationService()


# ===== ENUM для валидации =====

class ContactStatus(str):
    """Допустимые статусы контакта"""
    NEW = "NEW"
    MET = "MET"
    INTERESTED = "INTERESTED"
    ORIGINAL_SUBMITTED = "ORIGINAL_SUBMITTED"
    WAITING_ORIGINAL = "WAITING_ORIGINAL"
    NOT_INTERESTED = "NOT_INTERESTED"
    ENROLLED = "ENROLLED"
    WITHDRAWN = "WITHDRAWN"

    @classmethod
    def get_valid_values(cls):
        return [cls.NEW, cls.MET, cls.INTERESTED, cls.ORIGINAL_SUBMITTED,
                cls.WAITING_ORIGINAL, cls.NOT_INTERESTED, cls.ENROLLED, cls.WITHDRAWN]

    @classmethod
    def normalize(cls, value: str) -> str:
        if not value:
            return value
        value_upper = value.upper()
        if value_upper in cls.get_valid_values():
            return value_upper
        mapping = {
            'STRING': cls.NEW,
            'NEW': cls.NEW,
            'MET': cls.MET,
            'INTERESTED': cls.INTERESTED,
            'ORIGINAL_SUBMITTED': cls.ORIGINAL_SUBMITTED,
            'WAITING_ORIGINAL': cls.WAITING_ORIGINAL,
            'NOT_INTERESTED': cls.NOT_INTERESTED,
        }
        return mapping.get(value_upper, value_upper)


class CommunicationType(str):
    CALL = "CALL"
    MEETING = "MEETING"
    EMAIL = "EMAIL"
    MESSAGE = "MESSAGE"

    @classmethod
    def get_valid_values(cls):
        return [cls.CALL, cls.MEETING, cls.EMAIL, cls.MESSAGE]

    @classmethod
    def normalize(cls, value: str) -> str:
        if not value:
            return value
        value_upper = value.upper()
        if value_upper in cls.get_valid_values():
            return value_upper
        mapping = {
            'CALL': cls.CALL,
            'MEETING': cls.MEETING,
            'EMAIL': cls.EMAIL,
            'MESSAGE': cls.MESSAGE,
            'PHONE': cls.CALL,
            'PHONE_CALL': cls.CALL,
            'SMS': cls.MESSAGE,
        }
        return mapping.get(value_upper, value_upper)


class CommunicationStatus(str):
    PLANNED = "planned"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    MISSED = "missed"

    @classmethod
    def get_valid_values(cls):
        return [cls.PLANNED, cls.COMPLETED, cls.CANCELLED, cls.MISSED]

    @classmethod
    def normalize(cls, value: str) -> str:
        if not value:
            return value
        value_lower = value.lower()
        if value_lower in cls.get_valid_values():
            return value_lower
        mapping = {
            'planned': cls.PLANNED,
            'completed': cls.COMPLETED,
            'cancelled': cls.CANCELLED,
            'missed': cls.MISSED,
            'COMPLETED': cls.COMPLETED,
            'PLANNED': cls.PLANNED,
            'CANCELLED': cls.CANCELLED,
            'MISSED': cls.MISSED,
        }
        return mapping.get(value_lower, value_lower)


# ===== МОДЕЛИ ДЛЯ АБИТУРИЕНТОВ =====

class StudentCreate(BaseModel):
    full_name: str = Field(..., min_length=2, description="ФИО абитуриента")
    russian_student_id: Optional[int] = Field(None, description="Российский ID студента (7 цифр)")
    phone: Optional[str] = Field(None, description="Номер телефона")

    @field_validator('full_name')
    @classmethod
    def validate_full_name(cls, v):
        if not v or len(v.strip()) < 2:
            raise ValueError('ФИО должно содержать минимум 2 символа')
        return v.strip()


class StudentUpdate(BaseModel):
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
    contact_type: Optional[str] = None
    consent_status: Optional[bool] = None
    total_score: Optional[int] = None

    @field_validator('contact_status')
    @classmethod
    def validate_contact_status(cls, v):
        if v:
            normalized = ContactStatus.normalize(v)
            if normalized not in ContactStatus.get_valid_values():
                raise ValueError(
                    f"Недопустимый статус контакта. Допустимые: {', '.join(ContactStatus.get_valid_values())}")
            return normalized
        return v


class StudentResponse(BaseModel):
    id: int
    russian_student_id: Optional[int]
    full_name: str
    phone: Optional[str]
    additional_contacts: Optional[dict]
    prior_contact: Optional[str]
    department_id: Optional[int]
    department_name: Optional[str]
    speciality_id: Optional[int]
    speciality_name: Optional[str]
    profile_id: Optional[int]
    profile_name: Optional[str]
    study_level: Optional[str]
    study_form: Optional[str]
    study_basis: Optional[str]
    status: Optional[str]
    application_status: Optional[str]
    contact_status: Optional[str]
    contact_type: Optional[str]
    consent_status: Optional[bool]
    total_score: Optional[int]
    position: Optional[int]
    last_communication: Optional[datetime]
    last_communication_note: Optional[str]
    kurator_id: Optional[int]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class StudentListResponse(BaseModel):
    total: int
    students: List[StudentResponse]


# ===== МОДЕЛИ ДЛЯ ЗАЯВЛЕНИЙ И КОНКУРСНОЙ ИНФОРМАЦИИ =====

class StudentApplicationResponse(BaseModel):
    """Ответ с данными о заявлении студента"""
    id: int
    student_id: int
    department_id: int
    department_name: Optional[str] = None
    speciality_id: int
    speciality_name: Optional[str] = None
    profile_id: Optional[int] = None
    profile_name: Optional[str] = None
    position: Optional[int] = None
    priority: Optional[int] = None
    total_score: Optional[int] = None
    application_status: Optional[str] = None
    consent_status: Optional[bool] = None
    participation: Optional[bool] = None
    is_main_contest: Optional[bool] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CompetitiveInfoResponse(BaseModel):
    """Ответ с конкурсной информацией по студенту"""
    position: Optional[int]
    total_students: int
    total_enrolled: int
    total_submitted: int
    average_score: float
    min_score: int
    max_score: int
    passing_score: Optional[int]
    student_score: Optional[int]
    department_name: Optional[str]
    speciality_name: Optional[str]
    profile_name: Optional[str]


# ===== МОДЕЛИ ДЛЯ КОММУНИКАЦИЙ =====

class CommunicationCreate(BaseModel):
    communication_type: str = Field(..., description="Тип коммуникации")
    status: Optional[str] = Field("completed", description="Статус коммуникации")
    date_time: Optional[datetime] = Field(None, description="Дата и время")
    duration_minutes: Optional[int] = Field(None, ge=1, le=480, description="Длительность в минутах")
    notes: Optional[str] = Field(None, max_length=2000, description="Заметки")
    contact_status: Optional[str] = Field(None, description="Новый статус контакта для студента")

    @field_validator('communication_type')
    @classmethod
    def validate_communication_type(cls, v):
        if v:
            normalized = CommunicationType.normalize(v)
            if normalized not in CommunicationType.get_valid_values():
                raise ValueError(
                    f"Недопустимый тип коммуникации. Допустимые: {', '.join([t.lower() for t in CommunicationType.get_valid_values()])}")
            return normalized
        return v

    @field_validator('status')
    @classmethod
    def validate_status(cls, v):
        if v:
            normalized = CommunicationStatus.normalize(v)
            if normalized not in CommunicationStatus.get_valid_values():
                raise ValueError(
                    f"Недопустимый статус. Допустимые: {', '.join(CommunicationStatus.get_valid_values())}")
            return normalized
        return 'completed'

    @field_validator('contact_status')
    @classmethod
    def validate_contact_status(cls, v):
        if v:
            normalized = ContactStatus.normalize(v)
            if normalized not in ContactStatus.get_valid_values():
                raise ValueError(f"Недопустимый статус контакта: {v}")
            return normalized
        return v


class CommunicationUpdate(BaseModel):
    communication_type: Optional[str] = None
    status: Optional[str] = None
    date_time: Optional[datetime] = None
    duration_minutes: Optional[int] = Field(None, ge=1, le=480)
    notes: Optional[str] = Field(None, max_length=2000)

    @field_validator('communication_type')
    @classmethod
    def validate_communication_type(cls, v):
        if v:
            normalized = CommunicationType.normalize(v)
            if normalized not in CommunicationType.get_valid_values():
                raise ValueError(f"Недопустимый тип коммуникации")
            return normalized
        return v

    @field_validator('status')
    @classmethod
    def validate_status(cls, v):
        if v:
            normalized = CommunicationStatus.normalize(v)
            if normalized not in CommunicationStatus.get_valid_values():
                raise ValueError(f"Недопустимый статус")
            return normalized
        return v


class CommunicationResponse(BaseModel):
    id: int
    student_id: int
    student_name: Optional[str]
    communication_type: str
    status: str
    date_time: datetime
    duration_minutes: Optional[int]
    notes: Optional[str]
    contact_status: Optional[str]
    created_by_name: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class CommunicationStatsResponse(BaseModel):
    total_communications: int
    by_type: dict
    contact_status_distribution: Optional[dict] = {}
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
        application_status: Optional[str] = None,
        contact_status: Optional[str] = None,
        consent_status: Optional[bool] = None,
        department_id: Optional[int] = None,
        speciality_id: Optional[int] = None,
        search: Optional[str] = None,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """Получение списка доступных абитуриентов с фильтрацией"""
    students = student_service.get_available_students(
        user_id=current_user.id,
        db=db,
        skip=skip,
        limit=limit,
        status=status,
        application_status=application_status,
        contact_status=contact_status,
        consent_status=consent_status,
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


# ===== ЭНДПОИНТЫ ДЛЯ ЗАЯВЛЕНИЙ И КОНКУРСНОЙ ИНФОРМАЦИИ =====
# ВАЖНО: пути без дублирования /api/students, так как router уже имеет prefix="/api/students"

@router.get("/{student_id}/applications", response_model=List[StudentApplicationResponse])
async def get_student_applications(
        student_id: int,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """Получение всех заявлений студента на специальности"""
    # Проверяем доступ к студенту
    student = student_service.get_student_by_id(
        student_id=student_id,
        user_id=current_user.id,
        db=db
    )
    if not student:
        raise HTTPException(status_code=404, detail="Абитуриент не найден или доступ запрещен")

    applications = db.query(StudentApplication).filter(
        StudentApplication.student_id == student_id
    ).all()

    result = []
    for app in applications:
        department = db.query(Department).filter(Department.id == app.department_id).first()
        speciality = db.query(Speciality).filter(Speciality.id == app.speciality_id).first()
        profile = db.query(Profile).filter(Profile.id == app.profile_id).first() if app.profile_id else None

        result.append({
            "id": app.id,
            "student_id": app.student_id,
            "department_id": app.department_id,
            "department_name": department.name if department else None,
            "speciality_id": app.speciality_id,
            "speciality_name": speciality.name if speciality else None,
            "profile_id": app.profile_id,
            "profile_name": profile.name if profile else None,
            "position": app.position,
            "priority": app.priority,
            "total_score": app.total_score,
            "application_status": app.application_status.value if app.application_status else None,
            "consent_status": app.consent_status if app.consent_status is not None else False,
            "participation": app.participation if app.participation is not None else True,
            "is_main_contest": app.is_main_contest if app.is_main_contest is not None else False,
            "created_at": app.created_at,
            "updated_at": app.updated_at
        })

    return result


@router.get("/{student_id}/competitive-info", response_model=CompetitiveInfoResponse)
async def get_student_competitive_info(
        student_id: int,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """Получение конкурсной информации по студенту (место, проходной балл, статистика)"""
    # Проверяем доступ к студенту
    student = student_service.get_student_by_id(
        student_id=student_id,
        user_id=current_user.id,
        db=db
    )
    if not student:
        raise HTTPException(status_code=404, detail="Абитуриент не найден или доступ запрещен")

    # Получаем основное заявление (с наивысшим приоритетом или первое)
    main_application = db.query(StudentApplication).filter(
        StudentApplication.student_id == student_id
    ).order_by(StudentApplication.priority.asc(), StudentApplication.id.asc()).first()

    if not main_application:
        return CompetitiveInfoResponse(
            position=None,
            total_students=0,
            total_enrolled=0,
            total_submitted=0,
            average_score=0,
            min_score=0,
            max_score=0,
            passing_score=None,
            student_score=student.get('total_score'),
            department_name=None,
            speciality_name=None,
            profile_name=None
        )

    # Получаем всех студентов на той же специальности
    query = db.query(StudentApplication).filter(
        StudentApplication.department_id == main_application.department_id,
        StudentApplication.speciality_id == main_application.speciality_id
    )

    if main_application.profile_id:
        query = query.filter(StudentApplication.profile_id == main_application.profile_id)

    all_applications = query.all()

    # Сортируем по баллам (по убыванию)
    sorted_apps = sorted(all_applications, key=lambda x: x.total_score or 0, reverse=True)

    # Находим место текущего студента
    position = 1
    for i, app in enumerate(sorted_apps, 1):
        if app.student_id == student_id:
            position = i
            break

    # Подсчет статистики
    total_students = len(all_applications)
    enrolled_count = len([a for a in all_applications if a.application_status == ApplicationStatus.ACCEPTED])
    submitted_count = len([a for a in all_applications if a.application_status != ApplicationStatus.PENDING])

    scores = [a.total_score for a in all_applications if a.total_score and a.total_score > 0]
    avg_score = sum(scores) / len(scores) if scores else 0
    min_score = min(scores) if scores else 0
    max_score = max(scores) if scores else 0

    # Проходной балл (балл последнего зачисленного)
    passing_score = None
    if enrolled_count > 0:
        enrolled_apps = [a for a in all_applications if a.application_status == ApplicationStatus.ACCEPTED]
        enrolled_sorted = sorted(enrolled_apps, key=lambda x: x.total_score or 0, reverse=True)
        if enrolled_sorted:
            passing_score = enrolled_sorted[-1].total_score

    department = db.query(Department).filter(Department.id == main_application.department_id).first()
    speciality = db.query(Speciality).filter(Speciality.id == main_application.speciality_id).first()
    profile = db.query(Profile).filter(Profile.id == main_application.profile_id).first() if main_application.profile_id else None

    return CompetitiveInfoResponse(
        position=position,
        total_students=total_students,
        total_enrolled=enrolled_count,
        total_submitted=submitted_count,
        average_score=round(avg_score, 2),
        min_score=min_score,
        max_score=max_score,
        passing_score=passing_score,
        student_score=main_application.total_score,
        department_name=department.name if department else None,
        speciality_name=speciality.name if speciality else None,
        profile_name=profile.name if profile else None
    )


# ===== ЭНДПОИНТЫ ДЛЯ СОЗДАНИЯ/ОБНОВЛЕНИЯ/УДАЛЕНИЯ =====

@router.post("", response_model=StudentResponse, status_code=201)
async def create_student(
        student_data: StudentCreate,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """Создание нового абитуриента"""
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
    """Удаление абитуриента"""
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


# ===== ЭНДПОИНТЫ ДЛЯ КОММУНИКАЦИЙ =====

@router.get("/{student_id}/communications", response_model=List[CommunicationResponse])
async def get_student_communications(
        student_id: int,
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """Получение истории коммуникаций с абитуриентом"""
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
    student = student_service.get_student_by_id(
        student_id=student_id,
        user_id=current_user.id,
        db=db
    )

    if not student:
        raise HTTPException(status_code=404, detail="Абитуриент не найден или доступ запрещен")

    try:
        full_data = comm_data.dict(exclude_unset=True)
        full_data['student_id'] = student_id

        result = communication_service.create_communication(
            communication_data=full_data,
            user_id=current_user.id,
            db=db
        )
        return result
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
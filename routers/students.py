# api/routes/students.py
from fastapi import APIRouter, HTTPException, Depends, status, Query, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime
from sqlalchemy.orm import Session

from services.student_service import StudentService
from services.communication_service import CommunicationService
from services.auth_service import AuthService
from database.database import get_db
from database.schema import User, Department, Speciality, Profile, StudentApplication, ApplicationStatus, Student, \
    StudyForm, UserRole, StudyBasis, StudyLevel, MeetingStatus, CallStatus, DecisionStatus, DocumentsStatus

router = APIRouter(prefix="", tags=["Students"])
security = HTTPBearer()
auth_service = AuthService()
student_service = StudentService()
communication_service = CommunicationService()


class ContactStatus(str):
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


class MeetingStatusEnum(str):
    NOT_MET = "NOT_MET"
    MET = "MET"
    UNKNOWN = "UNKNOWN"

    @classmethod
    def get_valid_values(cls):
        return [cls.NOT_MET, cls.MET, cls.UNKNOWN]

    @classmethod
    def normalize(cls, value: str) -> str:
        if not value:
            return cls.UNKNOWN
        value_upper = value.upper()
        if value_upper in cls.get_valid_values():
            return value_upper
        return cls.UNKNOWN


class CallStatusEnum(str):
    NOT_REACHED = "NOT_REACHED"
    REACHED = "REACHED"
    UNKNOWN = "UNKNOWN"

    @classmethod
    def get_valid_values(cls):
        return [cls.NOT_REACHED, cls.REACHED, cls.UNKNOWN]

    @classmethod
    def normalize(cls, value: str) -> str:
        if not value:
            return cls.UNKNOWN
        value_upper = value.upper()
        if value_upper in cls.get_valid_values():
            return value_upper
        return cls.UNKNOWN


class DecisionStatusEnum(str):
    THINKING = "THINKING"
    DECIDED = "DECIDED"
    DENIED = "DENIED"
    UNKNOWN = "UNKNOWN"

    @classmethod
    def get_valid_values(cls):
        return [cls.THINKING, cls.DECIDED, cls.DENIED, cls.UNKNOWN]

    @classmethod
    def normalize(cls, value: str) -> str:
        if not value:
            return cls.UNKNOWN
        value_upper = value.upper()
        if value_upper in cls.get_valid_values():
            return value_upper
        return cls.UNKNOWN


class DocumentsStatusEnum(str):
    NOT_SUBMITTED = "NOT_SUBMITTED"
    ORIGINAL_SUBMITTED = "ORIGINAL_SUBMITTED"
    WAITING_ORIGINAL = "WAITING_ORIGINAL"
    ENROLLED = "ENROLLED"

    @classmethod
    def get_valid_values(cls):
        return [cls.NOT_SUBMITTED, cls.ORIGINAL_SUBMITTED, cls.WAITING_ORIGINAL, cls.ENROLLED]

    @classmethod
    def normalize(cls, value: str) -> str:
        if not value:
            return cls.NOT_SUBMITTED
        value_upper = value.upper()
        if value_upper in cls.get_valid_values():
            return value_upper
        return cls.NOT_SUBMITTED


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


class StudentCreate(BaseModel):
    full_name: str = Field(..., min_length=2)
    russian_student_id: Optional[int] = None
    phone: Optional[str] = None
    study_level: Optional[str] = None
    study_form: Optional[str] = None
    study_basis: Optional[str] = None

    @field_validator('full_name')
    @classmethod
    def validate_full_name(cls, v):
        if not v or len(v.strip()) < 2:
            raise ValueError('ФИО должно содержать минимум 2 символа')
        return v.strip()

    @field_validator('study_level')
    @classmethod
    def validate_study_level(cls, v):
        if v:
            valid_values = [level.value for level in StudyLevel]
            if v not in valid_values:
                raise ValueError(f"Недопустимый уровень. Допустимые: {', '.join(valid_values)}")
        return v

    @field_validator('study_form')
    @classmethod
    def validate_study_form(cls, v):
        if v:
            valid_values = [form.value for form in StudyForm]
            if v not in valid_values:
                raise ValueError(f"Недопустимая форма. Допустимые: {', '.join(valid_values)}")
        return v

    @field_validator('study_basis')
    @classmethod
    def validate_study_basis(cls, v):
        if v:
            valid_values = [basis.value for basis in StudyBasis]
            if v not in valid_values:
                raise ValueError(f"Недопустимая основа. Допустимые: {', '.join(valid_values)}")
        return v


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
    meeting_status: Optional[str] = None
    call_status: Optional[str] = None
    decision_status: Optional[str] = None
    documents_status: Optional[str] = None

    @field_validator('contact_status')
    @classmethod
    def validate_contact_status(cls, v):
        if v:
            normalized = ContactStatus.normalize(v)
            if normalized not in ContactStatus.get_valid_values():
                raise ValueError(f"Недопустимый статус контакта")
            return normalized
        return v

    @field_validator('meeting_status')
    @classmethod
    def validate_meeting_status(cls, v):
        if v:
            normalized = MeetingStatusEnum.normalize(v)
            if normalized not in MeetingStatusEnum.get_valid_values():
                raise ValueError(f"Недопустимый статус встречи")
            return normalized
        return v

    @field_validator('call_status')
    @classmethod
    def validate_call_status(cls, v):
        if v:
            normalized = CallStatusEnum.normalize(v)
            if normalized not in CallStatusEnum.get_valid_values():
                raise ValueError(f"Недопустимый статус дозвона")
            return normalized
        return v

    @field_validator('decision_status')
    @classmethod
    def validate_decision_status(cls, v):
        if v:
            normalized = DecisionStatusEnum.normalize(v)
            if normalized not in DecisionStatusEnum.get_valid_values():
                raise ValueError(f"Недопустимый статус решения")
            return normalized
        return v

    @field_validator('documents_status')
    @classmethod
    def validate_documents_status(cls, v):
        if v:
            normalized = DocumentsStatusEnum.normalize(v)
            if normalized not in DocumentsStatusEnum.get_valid_values():
                raise ValueError(f"Недопустимый статус документов")
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
    meeting_status: Optional[str] = "UNKNOWN"
    call_status: Optional[str] = "UNKNOWN"
    decision_status: Optional[str] = "UNKNOWN"
    documents_status: Optional[str] = "NOT_SUBMITTED"

    class Config:
        from_attributes = True


class StudentListResponse(BaseModel):
    total: int
    students: List[StudentResponse]


class StudentApplicationResponse(BaseModel):
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
    study_form: Optional[str] = None
    study_basis: Optional[str] = None
    study_level: Optional[str] = None
    budget_places_total: Optional[int] = None
    budget_places_filled: Optional[int] = None
    paid_places_total: Optional[int] = None
    paid_places_filled: Optional[int] = None
    target_places_total: Optional[int] = None
    target_places_filled: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CompetitiveInfoResponse(BaseModel):
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
    study_form: Optional[str] = None
    study_basis: Optional[str] = None
    budget_places_total: Optional[int] = None
    budget_places_filled: Optional[int] = None
    budget_places_free: Optional[int] = None
    competition: Optional[float] = None


class GroupStatisticsResponse(BaseModel):
    group_name: str
    profile_id: Optional[int] = None
    study_form: Optional[str]
    study_basis: Optional[str]
    total_applications: int
    applications_submitted: int
    enrolled: int
    average_score: float
    min_score: int
    max_score: int
    budget: dict
    paid: dict
    target: dict
    competition: float
    passing_score_current: int
    passing_score_last_year: int


class CommunicationCreate(BaseModel):
    communication_type: str
    status: Optional[str] = "completed"
    date_time: Optional[datetime] = None
    duration_minutes: Optional[int] = None
    notes: Optional[str] = None
    contact_status: Optional[str] = None

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
        return 'completed'


class CommunicationUpdate(BaseModel):
    communication_type: Optional[str] = None
    status: Optional[str] = None
    date_time: Optional[datetime] = None
    duration_minutes: Optional[int] = None
    notes: Optional[str] = None


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


@router.get("", response_model=StudentListResponse)
async def get_students_mobile(
        skip: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=500),
        status: Optional[str] = None,
        application_status: Optional[str] = None,
        contact_status: Optional[str] = None,
        consent_status: Optional[bool] = None,
        department_id: Optional[int] = None,
        speciality_id: Optional[int] = None,
        study_form: Optional[str] = None,
        study_basis: Optional[str] = None,
        search: Optional[str] = None,
        meeting_status: Optional[str] = None,
        call_status: Optional[str] = None,
        decision_status: Optional[str] = None,
        documents_status: Optional[str] = None,
        current_user: User = Depends(get_current_user_mobile),
        db: Session = Depends(get_db)
):
    students = student_service.get_available_students(
        user_id=current_user.id, db=db, skip=skip, limit=limit,
        status=status, application_status=application_status, contact_status=contact_status,
        consent_status=consent_status, department_id=department_id, speciality_id=speciality_id,
        study_form=study_form, study_basis=study_basis, search=search,
        meeting_status=meeting_status, call_status=call_status,
        decision_status=decision_status, documents_status=documents_status
    )
    return {"total": len(students), "students": students}


@router.get("/{student_id}", response_model=StudentResponse)
async def get_student_mobile(
        student_id: int,
        current_user: User = Depends(get_current_user_mobile),
        db: Session = Depends(get_db)
):
    student = student_service.get_student_by_id(student_id=student_id, user_id=current_user.id, db=db)
    if not student:
        raise HTTPException(status_code=404, detail="Абитуриент не найден")
    return student


@router.get("/{student_id}/applications", response_model=List[StudentApplicationResponse])
async def get_student_applications_mobile(
        student_id: int,
        current_user: User = Depends(get_current_user_mobile),
        db: Session = Depends(get_db)
):
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Абитуриент не найден")

    user = db.query(User).filter(User.id == current_user.id).first()
    if user.role != UserRole.ADMIN and student.kurator_id != current_user.id:
        raise HTTPException(status_code=403, detail="Доступ запрещен")

    applications = db.query(StudentApplication).filter(StudentApplication.student_id == student_id).all()
    result = []
    for app in applications:
        department = db.query(Department).filter(Department.id == app.department_id).first()
        speciality = db.query(Speciality).filter(Speciality.id == app.speciality_id).first()
        profile = db.query(Profile).filter(Profile.id == app.profile_id).first() if app.profile_id else None
        result.append(StudentApplicationResponse(
            id=app.id, student_id=app.student_id, department_id=app.department_id,
            department_name=department.name if department else None,
            speciality_id=app.speciality_id, speciality_name=speciality.name if speciality else None,
            profile_id=app.profile_id, profile_name=profile.name if profile else None,
            position=app.position, priority=app.priority, total_score=app.total_score,
            application_status=app.application_status.value if app.application_status else None,
            consent_status=app.consent_status if app.consent_status is not None else False,
            participation=app.participation if app.participation is not None else True,
            is_main_contest=app.is_main_contest if app.is_main_contest is not None else False,
            study_form=app.study_form.value if app.study_form else None,
            study_basis=app.study_basis.value if app.study_basis else None,
            study_level=app.study_level.value if app.study_level else None,
            budget_places_total=app.budget_places_total, budget_places_filled=app.budget_places_filled,
            paid_places_total=app.paid_places_total, paid_places_filled=app.paid_places_filled,
            target_places_total=app.target_places_total, target_places_filled=app.target_places_filled,
            created_at=app.created_at, updated_at=app.updated_at
        ))
    return result


@router.get("/{student_id}/competitive-info", response_model=CompetitiveInfoResponse)
async def get_student_competitive_info_mobile(
        student_id: int,
        current_user: User = Depends(get_current_user_mobile),
        db: Session = Depends(get_db)
):
    student = student_service.get_student_by_id(student_id=student_id, user_id=current_user.id, db=db)
    if not student:
        raise HTTPException(status_code=404, detail="Абитуриент не найден")

    main_application = db.query(StudentApplication).filter(
        StudentApplication.student_id == student_id
    ).order_by(StudentApplication.priority.asc(), StudentApplication.id.asc()).first()

    if not main_application:
        return CompetitiveInfoResponse(
            position=None, total_students=0, total_enrolled=0, total_submitted=0,
            average_score=0, min_score=0, max_score=0, passing_score=None,
            student_score=student.get('total_score'), department_name=None,
            speciality_name=None, profile_name=None, study_form=None,
            study_basis=None, budget_places_total=None, budget_places_filled=None,
            budget_places_free=None, competition=None
        )

    query = db.query(StudentApplication).filter(
        StudentApplication.department_id == main_application.department_id,
        StudentApplication.speciality_id == main_application.speciality_id
    )
    if main_application.profile_id:
        query = query.filter(StudentApplication.profile_id == main_application.profile_id)
    if main_application.study_form:
        query = query.filter(StudentApplication.study_form == main_application.study_form)
    if main_application.study_basis:
        query = query.filter(StudentApplication.study_basis == main_application.study_basis)

    all_applications = query.all()
    sorted_apps = sorted(all_applications, key=lambda x: x.total_score or 0, reverse=True)

    position = 1
    for i, app in enumerate(sorted_apps, 1):
        if app.student_id == student_id:
            position = i
            break

    total_students = len(all_applications)
    enrolled_count = len([a for a in all_applications if a.application_status == ApplicationStatus.ACCEPTED])
    submitted_count = len([a for a in all_applications if a.application_status != ApplicationStatus.PENDING])

    scores = [a.total_score for a in all_applications if a.total_score and a.total_score > 0]
    avg_score = sum(scores) / len(scores) if scores else 0
    min_score = min(scores) if scores else 0
    max_score = max(scores) if scores else 0

    passing_score = None
    if enrolled_count > 0:
        enrolled_apps = [a for a in all_applications if a.application_status == ApplicationStatus.ACCEPTED]
        enrolled_sorted = sorted(enrolled_apps, key=lambda x: x.total_score or 0, reverse=True)
        if enrolled_sorted:
            passing_score = enrolled_sorted[-1].total_score

    department = db.query(Department).filter(Department.id == main_application.department_id).first()
    speciality = db.query(Speciality).filter(Speciality.id == main_application.speciality_id).first()
    profile = db.query(Profile).filter(Profile.id == main_application.profile_id).first() if main_application.profile_id else None

    budget_places_free = None
    if main_application.budget_places_total and main_application.budget_places_filled:
        budget_places_free = main_application.budget_places_total - main_application.budget_places_filled
    elif main_application.budget_places_total:
        budget_places_free = main_application.budget_places_total

    competition = None
    if main_application.budget_places_total and main_application.budget_places_total > 0:
        competition = round(total_students / main_application.budget_places_total, 2)

    return CompetitiveInfoResponse(
        position=position, total_students=total_students, total_enrolled=enrolled_count,
        total_submitted=submitted_count, average_score=round(avg_score, 2),
        min_score=min_score, max_score=max_score, passing_score=passing_score,
        student_score=main_application.total_score,
        department_name=department.name if department else None,
        speciality_name=speciality.name if speciality else None,
        profile_name=profile.name if profile else None,
        study_form=main_application.study_form.value if main_application.study_form else None,
        study_basis=main_application.study_basis.value if main_application.study_basis else None,
        budget_places_total=main_application.budget_places_total,
        budget_places_filled=main_application.budget_places_filled,
        budget_places_free=budget_places_free, competition=competition
    )


@router.get("/{student_id}/competitive-info/{speciality_id}", response_model=CompetitiveInfoResponse)
async def get_student_competitive_info_for_speciality_mobile(
        student_id: int,
        speciality_id: int,
        current_user: User = Depends(get_current_user_mobile),
        db: Session = Depends(get_db)
):
    student = student_service.get_student_by_id(student_id=student_id, user_id=current_user.id, db=db)
    if not student:
        raise HTTPException(status_code=404, detail="Абитуриент не найден")

    application = db.query(StudentApplication).filter(
        StudentApplication.student_id == student_id,
        StudentApplication.speciality_id == speciality_id
    ).first()

    if not application:
        return CompetitiveInfoResponse(
            position=None, total_students=0, total_enrolled=0, total_submitted=0,
            average_score=0, min_score=0, max_score=0, passing_score=None,
            student_score=None, department_name=None, speciality_name=None,
            profile_name=None, study_form=None, study_basis=None,
            budget_places_total=None, budget_places_filled=None, budget_places_free=None, competition=None
        )

    query = db.query(StudentApplication).filter(StudentApplication.speciality_id == speciality_id)
    if application.profile_id:
        query = query.filter(StudentApplication.profile_id == application.profile_id)
    if application.study_form:
        query = query.filter(StudentApplication.study_form == application.study_form)
    if application.study_basis:
        query = query.filter(StudentApplication.study_basis == application.study_basis)

    all_applications = query.all()
    sorted_apps = sorted(all_applications, key=lambda x: x.total_score or 0, reverse=True)

    position = 1
    for i, app in enumerate(sorted_apps, 1):
        if app.student_id == student_id:
            position = i
            break

    total_students = len(all_applications)
    enrolled_count = len([a for a in all_applications if a.application_status == ApplicationStatus.ACCEPTED])
    submitted_count = len([a for a in all_applications if a.application_status != ApplicationStatus.PENDING])

    scores = [a.total_score for a in all_applications if a.total_score and a.total_score > 0]
    avg_score = sum(scores) / len(scores) if scores else 0
    min_score = min(scores) if scores else 0
    max_score = max(scores) if scores else 0

    passing_score = None
    if enrolled_count > 0:
        enrolled_apps = [a for a in all_applications if a.application_status == ApplicationStatus.ACCEPTED]
        enrolled_sorted = sorted(enrolled_apps, key=lambda x: x.total_score or 0, reverse=True)
        if enrolled_sorted:
            passing_score = enrolled_sorted[-1].total_score

    department = db.query(Department).filter(Department.id == application.department_id).first()
    speciality = db.query(Speciality).filter(Speciality.id == speciality_id).first()
    profile = db.query(Profile).filter(Profile.id == application.profile_id).first() if application.profile_id else None

    budget_places_free = None
    if application.budget_places_total and application.budget_places_filled:
        budget_places_free = application.budget_places_total - application.budget_places_filled
    elif application.budget_places_total:
        budget_places_free = application.budget_places_total

    competition = None
    if application.budget_places_total and application.budget_places_total > 0:
        competition = round(total_students / application.budget_places_total, 2)

    return CompetitiveInfoResponse(
        position=position, total_students=total_students, total_enrolled=enrolled_count,
        total_submitted=submitted_count, average_score=round(avg_score, 2),
        min_score=min_score, max_score=max_score, passing_score=passing_score,
        student_score=application.total_score,
        department_name=department.name if department else None,
        speciality_name=speciality.name if speciality else None,
        profile_name=profile.name if profile else None,
        study_form=application.study_form.value if application.study_form else None,
        study_basis=application.study_basis.value if application.study_basis else None,
        budget_places_total=application.budget_places_total,
        budget_places_filled=application.budget_places_filled,
        budget_places_free=budget_places_free, competition=competition
    )


@router.get("/{student_id}/communications", response_model=List[CommunicationResponse])
async def get_student_communications_mobile(
        student_id: int,
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
        current_user: User = Depends(get_current_user_mobile),
        db: Session = Depends(get_db)
):
    student = student_service.get_student_by_id(student_id=student_id, user_id=current_user.id, db=db)
    if not student:
        raise HTTPException(status_code=404, detail="Абитуриент не найден")

    communications = communication_service.get_student_communications(
        student_id=student_id, user_id=current_user.id, db=db, limit=limit, offset=offset
    )
    return communications


@router.post("/{student_id}/communications", response_model=CommunicationResponse, status_code=201)
async def create_student_communication_mobile(
        student_id: int,
        comm_data: CommunicationCreate,
        current_user: User = Depends(get_current_user_mobile),
        db: Session = Depends(get_db)
):
    student = student_service.get_student_by_id(student_id=student_id, user_id=current_user.id, db=db)
    if not student:
        raise HTTPException(status_code=404, detail="Абитуриент не найден")

    full_data = comm_data.dict(exclude_unset=True)
    full_data['student_id'] = student_id
    result = communication_service.create_communication(
        communication_data=full_data, user_id=current_user.id, db=db
    )
    return result


@router.post("", response_model=StudentResponse, status_code=201)
async def create_student_mobile(
        student_data: StudentCreate,
        current_user: User = Depends(get_current_user_mobile),
        db: Session = Depends(get_db)
):
    return student_service.create_student(student_data.dict(exclude_unset=True), user_id=current_user.id, db=db)


@router.put("/{student_id}", response_model=StudentResponse)
async def update_student_mobile(
        student_id: int,
        student_data: StudentUpdate,
        current_user: User = Depends(get_current_user_mobile),
        db: Session = Depends(get_db)
):
    student = student_service.update_student(
        student_id=student_id, update_data=student_data.dict(exclude_unset=True),
        user_id=current_user.id, db=db
    )
    if not student:
        raise HTTPException(status_code=404, detail="Абитуриент не найден")
    return student


@router.delete("/{student_id}")
async def delete_student_mobile(
        student_id: int,
        current_user: User = Depends(get_current_user_mobile),
        db: Session = Depends(get_db)
):
    deleted = student_service.delete_student(student_id=student_id, user_id=current_user.id, db=db)
    if not deleted:
        raise HTTPException(status_code=404, detail="Абитуриент не найден")
    return {"message": "Абитуриент успешно удален"}


@router.get("/statistics/groups", response_model=List[GroupStatisticsResponse])
async def get_group_statistics_mobile(
        current_user: User = Depends(get_current_user_mobile),
        db: Session = Depends(get_db)
):
    from services.parser_service import GROUPS_CONFIG
    results = []
    for group_config in GROUPS_CONFIG:
        department = db.query(Department).filter(Department.name == group_config['department_name']).first()
        if not department:
            continue
        speciality = db.query(Speciality).filter(
            Speciality.name == group_config['speciality_name'],
            Speciality.department_id == department.id
        ).first()
        if not speciality:
            continue
        profile = db.query(Profile).filter(
            Profile.name == group_config['profile_name'],
            Profile.speciality_id == speciality.id
        ).first()
        if not profile:
            from services.parser_service import ParserService
            parser = ParserService(db)
            data = parser.fetch_group_data(group_config['uid'])
            api_data = data.get('data', []) if data and data.get('state') == 'ok' else []
            stats = parser.calculate_statistics_from_api_data(group_config, api_data)
            profile_id = None
        else:
            stats = {
                "total_applications": profile.total_applications or 0,
                "applications_submitted": profile.applications_submitted or 0,
                "enrolled": profile.enrolled or 0,
                "average_score": profile.average_score or 0,
                "min_score": profile.min_score or 0,
                "max_score": profile.max_score or 0,
                "budget": {"total": profile.budget_places or 0, "filled": profile.budget_filled or 0,
                           "free": profile.budget_free or 0, "applicants_in_range": profile.budget_applicants_in_range or 0,
                           "applicants_with_consent": profile.budget_applicants_with_consent or 0,
                           "passing_score": profile.budget_passing_score or 0},
                "paid": {"total": profile.paid_places or 0, "filled": profile.paid_filled or 0,
                         "free": profile.paid_free or 0, "applicants_with_consent": profile.paid_applicants_with_consent or 0},
                "target": {"total": profile.target_places or 0, "filled": profile.target_filled or 0,
                           "free": profile.target_free or 0, "applicants_with_consent": profile.target_applicants_with_consent or 0},
                "competition": profile.competition or 0,
                "passing_score_current": profile.passing_score_current or 0,
                "passing_score_last_year": profile.passing_score_last_year or 0
            }
            profile_id = profile.id
        results.append(GroupStatisticsResponse(
            group_name=group_config['name'], profile_id=profile_id,
            study_form=group_config.get('study_form').value if group_config.get('study_form') else None,
            study_basis=group_config.get('study_basis').value if group_config.get('study_basis') else None,
            total_applications=stats['total_applications'], applications_submitted=stats['applications_submitted'],
            enrolled=stats['enrolled'], average_score=stats['average_score'], min_score=stats['min_score'],
            max_score=stats['max_score'], budget=stats['budget'], paid=stats['paid'], target=stats['target'],
            competition=stats['competition'], passing_score_current=stats['passing_score_current'],
            passing_score_last_year=stats['passing_score_last_year']
        ))
    return results


@router.get("/communications/stats", response_model=CommunicationStatsResponse)
async def get_communication_stats_mobile(
        days_back: int = Query(30, ge=1, le=365),
        current_user: User = Depends(get_current_user_mobile),
        db: Session = Depends(get_db)
):
    return communication_service.get_communication_stats(
        user_id=current_user.id, db=db, days_back=days_back
    )


@router.put("/communications/{comm_id}", response_model=CommunicationResponse)
async def update_communication_mobile(
        comm_id: int,
        comm_data: CommunicationUpdate,
        current_user: User = Depends(get_current_user_mobile),
        db: Session = Depends(get_db)
):
    communication = communication_service.update_communication(
        communication_id=comm_id, update_data=comm_data.dict(exclude_unset=True),
        user_id=current_user.id, db=db
    )
    if not communication:
        raise HTTPException(status_code=404, detail="Коммуникация не найдена")
    return communication


@router.delete("/communications/{comm_id}")
async def delete_communication_mobile(
        comm_id: int,
        current_user: User = Depends(get_current_user_mobile),
        db: Session = Depends(get_db)
):
    deleted = communication_service.delete_communication(
        communication_id=comm_id, user_id=current_user.id, db=db
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Коммуникация не найдена")
    return {"message": "Коммуникация успешно удалена"}


@router.get("/web", response_model=StudentListResponse)
async def web_get_students(
        request: Request,
        skip: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=500),
        status: Optional[str] = None,
        application_status: Optional[str] = None,
        contact_status: Optional[str] = None,
        consent_status: Optional[bool] = None,
        department_id: Optional[int] = None,
        speciality_id: Optional[int] = None,
        study_form: Optional[str] = None,
        study_basis: Optional[str] = None,
        search: Optional[str] = None,
        meeting_status: Optional[str] = None,
        call_status: Optional[str] = None,
        decision_status: Optional[str] = None,
        documents_status: Optional[str] = None,
        db: Session = Depends(get_db)
):
    current_user = await get_current_user_web(request, db)
    students = student_service.get_available_students(
        user_id=current_user.id, db=db, skip=skip, limit=limit,
        status=status, application_status=application_status, contact_status=contact_status,
        consent_status=consent_status, department_id=department_id, speciality_id=speciality_id,
        study_form=study_form, study_basis=study_basis, search=search,
        meeting_status=meeting_status, call_status=call_status,
        decision_status=decision_status, documents_status=documents_status
    )
    return {"total": len(students), "students": students}


@router.get("/web/{student_id}", response_model=StudentResponse)
async def web_get_student(
        request: Request,
        student_id: int,
        db: Session = Depends(get_db)
):
    current_user = await get_current_user_web(request, db)
    student = student_service.get_student_by_id(student_id=student_id, user_id=current_user.id, db=db)
    if not student:
        raise HTTPException(status_code=404, detail="Абитуриент не найден")
    return student


@router.get("/web/{student_id}/applications", response_model=List[StudentApplicationResponse])
async def web_get_student_applications(
        request: Request,
        student_id: int,
        db: Session = Depends(get_db)
):
    current_user = await get_current_user_web(request, db)
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Абитуриент не найден")

    user = db.query(User).filter(User.id == current_user.id).first()
    if user.role != UserRole.ADMIN and student.kurator_id != current_user.id:
        raise HTTPException(status_code=403, detail="Доступ запрещен")

    applications = db.query(StudentApplication).filter(StudentApplication.student_id == student_id).all()
    result = []
    for app in applications:
        department = db.query(Department).filter(Department.id == app.department_id).first()
        speciality = db.query(Speciality).filter(Speciality.id == app.speciality_id).first()
        profile = db.query(Profile).filter(Profile.id == app.profile_id).first() if app.profile_id else None
        result.append(StudentApplicationResponse(
            id=app.id, student_id=app.student_id, department_id=app.department_id,
            department_name=department.name if department else None,
            speciality_id=app.speciality_id, speciality_name=speciality.name if speciality else None,
            profile_id=app.profile_id, profile_name=profile.name if profile else None,
            position=app.position, priority=app.priority, total_score=app.total_score,
            application_status=app.application_status.value if app.application_status else None,
            consent_status=app.consent_status if app.consent_status is not None else False,
            participation=app.participation if app.participation is not None else True,
            is_main_contest=app.is_main_contest if app.is_main_contest is not None else False,
            study_form=app.study_form.value if app.study_form else None,
            study_basis=app.study_basis.value if app.study_basis else None,
            study_level=app.study_level.value if app.study_level else None,
            budget_places_total=app.budget_places_total, budget_places_filled=app.budget_places_filled,
            paid_places_total=app.paid_places_total, paid_places_filled=app.paid_places_filled,
            target_places_total=app.target_places_total, target_places_filled=app.target_places_filled,
            created_at=app.created_at, updated_at=app.updated_at
        ))
    return result


@router.get("/web/{student_id}/competitive-info", response_model=CompetitiveInfoResponse)
async def web_get_student_competitive_info(
        request: Request,
        student_id: int,
        db: Session = Depends(get_db)
):
    current_user = await get_current_user_web(request, db)

    student = student_service.get_student_by_id(student_id=student_id, user_id=current_user.id, db=db)
    if not student:
        raise HTTPException(status_code=404, detail="Абитуриент не найден")

    main_application = db.query(StudentApplication).filter(
        StudentApplication.student_id == student_id
    ).order_by(StudentApplication.priority.asc(), StudentApplication.id.asc()).first()

    if not main_application:
        return CompetitiveInfoResponse(
            position=None, total_students=0, total_enrolled=0, total_submitted=0,
            average_score=0, min_score=0, max_score=0, passing_score=None,
            student_score=student.get('total_score'), department_name=None,
            speciality_name=None, profile_name=None, study_form=None,
            study_basis=None, budget_places_total=None, budget_places_filled=None,
            budget_places_free=None, competition=None
        )

    query = db.query(StudentApplication).filter(
        StudentApplication.department_id == main_application.department_id,
        StudentApplication.speciality_id == main_application.speciality_id
    )
    if main_application.profile_id:
        query = query.filter(StudentApplication.profile_id == main_application.profile_id)
    if main_application.study_form:
        query = query.filter(StudentApplication.study_form == main_application.study_form)
    if main_application.study_basis:
        query = query.filter(StudentApplication.study_basis == main_application.study_basis)

    all_applications = query.all()
    sorted_apps = sorted(all_applications, key=lambda x: x.total_score or 0, reverse=True)

    position = 1
    for i, app in enumerate(sorted_apps, 1):
        if app.student_id == student_id:
            position = i
            break

    total_students = len(all_applications)
    enrolled_count = len([a for a in all_applications if a.application_status == ApplicationStatus.ACCEPTED])
    submitted_count = len([a for a in all_applications if a.application_status != ApplicationStatus.PENDING])

    scores = [a.total_score for a in all_applications if a.total_score and a.total_score > 0]
    avg_score = sum(scores) / len(scores) if scores else 0
    min_score = min(scores) if scores else 0
    max_score = max(scores) if scores else 0

    passing_score = None
    if enrolled_count > 0:
        enrolled_apps = [a for a in all_applications if a.application_status == ApplicationStatus.ACCEPTED]
        enrolled_sorted = sorted(enrolled_apps, key=lambda x: x.total_score or 0, reverse=True)
        if enrolled_sorted:
            passing_score = enrolled_sorted[-1].total_score

    department = db.query(Department).filter(Department.id == main_application.department_id).first()
    speciality = db.query(Speciality).filter(Speciality.id == main_application.speciality_id).first()
    profile = db.query(Profile).filter(Profile.id == main_application.profile_id).first() if main_application.profile_id else None

    budget_places_free = None
    if main_application.budget_places_total and main_application.budget_places_filled:
        budget_places_free = main_application.budget_places_total - main_application.budget_places_filled
    elif main_application.budget_places_total:
        budget_places_free = main_application.budget_places_total

    competition = None
    if main_application.budget_places_total and main_application.budget_places_total > 0:
        competition = round(total_students / main_application.budget_places_total, 2)

    return CompetitiveInfoResponse(
        position=position, total_students=total_students, total_enrolled=enrolled_count,
        total_submitted=submitted_count, average_score=round(avg_score, 2),
        min_score=min_score, max_score=max_score, passing_score=passing_score,
        student_score=main_application.total_score,
        department_name=department.name if department else None,
        speciality_name=speciality.name if speciality else None,
        profile_name=profile.name if profile else None,
        study_form=main_application.study_form.value if main_application.study_form else None,
        study_basis=main_application.study_basis.value if main_application.study_basis else None,
        budget_places_total=main_application.budget_places_total,
        budget_places_filled=main_application.budget_places_filled,
        budget_places_free=budget_places_free, competition=competition
    )


@router.get("/web/{student_id}/competitive-info/{speciality_id}", response_model=CompetitiveInfoResponse)
async def web_get_student_competitive_info_for_speciality(
        request: Request,
        student_id: int,
        speciality_id: int,
        db: Session = Depends(get_db)
):
    current_user = await get_current_user_web(request, db)

    student = student_service.get_student_by_id(student_id=student_id, user_id=current_user.id, db=db)
    if not student:
        raise HTTPException(status_code=404, detail="Абитуриент не найден")

    application = db.query(StudentApplication).filter(
        StudentApplication.student_id == student_id,
        StudentApplication.speciality_id == speciality_id
    ).first()

    if not application:
        return CompetitiveInfoResponse(
            position=None, total_students=0, total_enrolled=0, total_submitted=0,
            average_score=0, min_score=0, max_score=0, passing_score=None,
            student_score=None, department_name=None, speciality_name=None,
            profile_name=None, study_form=None, study_basis=None,
            budget_places_total=None, budget_places_filled=None, budget_places_free=None, competition=None
        )

    query = db.query(StudentApplication).filter(StudentApplication.speciality_id == speciality_id)
    if application.profile_id:
        query = query.filter(StudentApplication.profile_id == application.profile_id)
    if application.study_form:
        query = query.filter(StudentApplication.study_form == application.study_form)
    if application.study_basis:
        query = query.filter(StudentApplication.study_basis == application.study_basis)

    all_applications = query.all()
    sorted_apps = sorted(all_applications, key=lambda x: x.total_score or 0, reverse=True)

    position = 1
    for i, app in enumerate(sorted_apps, 1):
        if app.student_id == student_id:
            position = i
            break

    total_students = len(all_applications)
    enrolled_count = len([a for a in all_applications if a.application_status == ApplicationStatus.ACCEPTED])
    submitted_count = len([a for a in all_applications if a.application_status != ApplicationStatus.PENDING])

    scores = [a.total_score for a in all_applications if a.total_score and a.total_score > 0]
    avg_score = sum(scores) / len(scores) if scores else 0
    min_score = min(scores) if scores else 0
    max_score = max(scores) if scores else 0

    passing_score = None
    if enrolled_count > 0:
        enrolled_apps = [a for a in all_applications if a.application_status == ApplicationStatus.ACCEPTED]
        enrolled_sorted = sorted(enrolled_apps, key=lambda x: x.total_score or 0, reverse=True)
        if enrolled_sorted:
            passing_score = enrolled_sorted[-1].total_score

    department = db.query(Department).filter(Department.id == application.department_id).first()
    speciality = db.query(Speciality).filter(Speciality.id == speciality_id).first()
    profile = db.query(Profile).filter(Profile.id == application.profile_id).first() if application.profile_id else None

    budget_places_free = None
    if application.budget_places_total and application.budget_places_filled:
        budget_places_free = application.budget_places_total - application.budget_places_filled
    elif application.budget_places_total:
        budget_places_free = application.budget_places_total

    competition = None
    if application.budget_places_total and application.budget_places_total > 0:
        competition = round(total_students / application.budget_places_total, 2)

    return CompetitiveInfoResponse(
        position=position, total_students=total_students, total_enrolled=enrolled_count,
        total_submitted=submitted_count, average_score=round(avg_score, 2),
        min_score=min_score, max_score=max_score, passing_score=passing_score,
        student_score=application.total_score,
        department_name=department.name if department else None,
        speciality_name=speciality.name if speciality else None,
        profile_name=profile.name if profile else None,
        study_form=application.study_form.value if application.study_form else None,
        study_basis=application.study_basis.value if application.study_basis else None,
        budget_places_total=application.budget_places_total,
        budget_places_filled=application.budget_places_filled,
        budget_places_free=budget_places_free, competition=competition
    )


@router.get("/web/{student_id}/communications", response_model=List[CommunicationResponse])
async def web_get_student_communications(
        request: Request,
        student_id: int,
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
        db: Session = Depends(get_db)
):
    current_user = await get_current_user_web(request, db)
    student = student_service.get_student_by_id(student_id=student_id, user_id=current_user.id, db=db)
    if not student:
        return []

    communications = communication_service.get_student_communications(
        student_id=student_id, user_id=current_user.id, db=db, limit=limit, offset=offset
    )
    return communications


@router.post("/web/{student_id}/communications", response_model=CommunicationResponse, status_code=201)
async def web_create_student_communication(
        request: Request,
        student_id: int,
        comm_data: CommunicationCreate,
        db: Session = Depends(get_db)
):
    current_user = await get_current_user_web(request, db)
    student = student_service.get_student_by_id(student_id=student_id, user_id=current_user.id, db=db)
    if not student:
        raise HTTPException(status_code=404, detail="Абитуриент не найден")

    full_data = comm_data.dict(exclude_unset=True)
    full_data['student_id'] = student_id
    result = communication_service.create_communication(
        communication_data=full_data, user_id=current_user.id, db=db
    )
    return result


@router.post("/web", response_model=StudentResponse, status_code=201)
async def web_create_student(
        request: Request,
        student_data: StudentCreate,
        db: Session = Depends(get_db)
):
    current_user = await get_current_user_web(request, db)
    return student_service.create_student(student_data.dict(exclude_unset=True), user_id=current_user.id, db=db)


@router.put("/web/{student_id}", response_model=StudentResponse)
async def web_update_student(
        request: Request,
        student_id: int,
        student_data: StudentUpdate,
        db: Session = Depends(get_db)
):
    current_user = await get_current_user_web(request, db)
    student = student_service.update_student(
        student_id=student_id, update_data=student_data.dict(exclude_unset=True),
        user_id=current_user.id, db=db
    )
    if not student:
        raise HTTPException(status_code=404, detail="Абитуриент не найден")
    return student


@router.delete("/web/{student_id}")
async def web_delete_student(
        request: Request,
        student_id: int,
        db: Session = Depends(get_db)
):
    current_user = await get_current_user_web(request, db)
    deleted = student_service.delete_student(student_id=student_id, user_id=current_user.id, db=db)
    if not deleted:
        raise HTTPException(status_code=404, detail="Абитуриент не найден")
    return {"message": "Абитуриент успешно удален"}


@router.get("/web/statistics/groups", response_model=List[GroupStatisticsResponse])
async def web_get_group_statistics(
        request: Request,
        db: Session = Depends(get_db)
):
    current_user = await get_current_user_web(request, db)
    from services.parser_service import GROUPS_CONFIG
    results = []
    for group_config in GROUPS_CONFIG:
        department = db.query(Department).filter(Department.name == group_config['department_name']).first()
        if not department:
            continue
        speciality = db.query(Speciality).filter(
            Speciality.name == group_config['speciality_name'],
            Speciality.department_id == department.id
        ).first()
        if not speciality:
            continue
        profile = db.query(Profile).filter(
            Profile.name == group_config['profile_name'],
            Profile.speciality_id == speciality.id
        ).first()
        if not profile:
            from services.parser_service import ParserService
            parser = ParserService(db)
            data = parser.fetch_group_data(group_config['uid'])
            api_data = data.get('data', []) if data and data.get('state') == 'ok' else []
            stats = parser.calculate_statistics_from_api_data(group_config, api_data)
            profile_id = None
        else:
            stats = {
                "total_applications": profile.total_applications or 0,
                "applications_submitted": profile.applications_submitted or 0,
                "enrolled": profile.enrolled or 0,
                "average_score": profile.average_score or 0,
                "min_score": profile.min_score or 0,
                "max_score": profile.max_score or 0,
                "budget": {"total": profile.budget_places or 0, "filled": profile.budget_filled or 0,
                           "free": profile.budget_free or 0, "applicants_in_range": profile.budget_applicants_in_range or 0,
                           "applicants_with_consent": profile.budget_applicants_with_consent or 0,
                           "passing_score": profile.budget_passing_score or 0},
                "paid": {"total": profile.paid_places or 0, "filled": profile.paid_filled or 0,
                         "free": profile.paid_free or 0, "applicants_with_consent": profile.paid_applicants_with_consent or 0},
                "target": {"total": profile.target_places or 0, "filled": profile.target_filled or 0,
                           "free": profile.target_free or 0, "applicants_with_consent": profile.target_applicants_with_consent or 0},
                "competition": profile.competition or 0,
                "passing_score_current": profile.passing_score_current or 0,
                "passing_score_last_year": profile.passing_score_last_year or 0
            }
            profile_id = profile.id
        results.append(GroupStatisticsResponse(
            group_name=group_config['name'], profile_id=profile_id,
            study_form=group_config.get('study_form').value if group_config.get('study_form') else None,
            study_basis=group_config.get('study_basis').value if group_config.get('study_basis') else None,
            total_applications=stats['total_applications'], applications_submitted=stats['applications_submitted'],
            enrolled=stats['enrolled'], average_score=stats['average_score'], min_score=stats['min_score'],
            max_score=stats['max_score'], budget=stats['budget'], paid=stats['paid'], target=stats['target'],
            competition=stats['competition'], passing_score_current=stats['passing_score_current'],
            passing_score_last_year=stats['passing_score_last_year']
        ))
    return results


@router.get("/web/communications/stats", response_model=CommunicationStatsResponse)
async def web_get_communication_stats(
        request: Request,
        days_back: int = Query(30, ge=1, le=365),
        db: Session = Depends(get_db)
):
    current_user = await get_current_user_web(request, db)
    return communication_service.get_communication_stats(
        user_id=current_user.id, db=db, days_back=days_back
    )


@router.put("/web/communications/{comm_id}", response_model=CommunicationResponse)
async def web_update_communication(
        request: Request,
        comm_id: int,
        comm_data: CommunicationUpdate,
        db: Session = Depends(get_db)
):
    current_user = await get_current_user_web(request, db)
    communication = communication_service.update_communication(
        communication_id=comm_id, update_data=comm_data.dict(exclude_unset=True),
        user_id=current_user.id, db=db
    )
    if not communication:
        raise HTTPException(status_code=404, detail="Коммуникация не найдена")
    return communication


@router.delete("/web/communications/{comm_id}")
async def web_delete_communication(
        request: Request,
        comm_id: int,
        db: Session = Depends(get_db)
):
    current_user = await get_current_user_web(request, db)
    deleted = communication_service.delete_communication(
        communication_id=comm_id, user_id=current_user.id, db=db
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Коммуникация не найдена")
    return {"message": "Коммуникация успешно удалена"}
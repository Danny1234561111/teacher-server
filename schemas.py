from pydantic import BaseModel, EmailStr, Field, validator, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime, date
from enum import Enum
import re


# ========== Enums ==========
class UserRole(str, Enum):
    ADMIN = "admin"
    TEACHER = "teacher"
    STUDENT = "student"

class CommunicationType(str, Enum):
    CALL = "call"
    MEETING = "meeting"
    EMAIL = "email"
    MESSAGE = "message"
    OTHER = "other"

class CommunicationStatus(str, Enum):
    PLANNED = "planned"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    RESCHEDULED = "rescheduled"

class StudentStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    GRADUATED = "graduated"
    DROPPED = "dropped"

class TeacherRequestStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"

class StudentRequestType(str, Enum):
    DEPARTMENT_CHANGE = "department_change"
    TEACHER_CHANGE = "teacher_change"
    INFORMATION = "information"
    OTHER = "other"

class StudentRequestStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    REJECTED = "rejected"
    CLOSED = "closed"

class NotificationPriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"

class ReportType(str, Enum):
    TEACHERS = "teachers"
    STUDENTS = "students"
    DEPARTMENTS = "departments"
    REQUESTS = "requests"
    SYSTEM = "system"


# ========== Аутентификация ==========
class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class RegisterRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=6)
    phone: Optional[str] = None
    date_of_birth: Optional[date] = None
    role: UserRole = UserRole.TEACHER
    max_students: int = Field(20, ge=1, le=1000)

    @validator('phone')
    def validate_phone(cls, v):
        if v:
            phone_pattern = re.compile(r'^\+?[1-9]\d{1,14}$')
            if not phone_pattern.match(v):
                raise ValueError('Phone must contain only digits and optional + sign')
        return v

class AuthResponse(BaseModel):
    token: str
    user_id: str
    user: Dict[str, Any]
    message: Optional[str] = None

class TokenRefreshRequest(BaseModel):
    refresh_token: str

class TokenRefreshResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: Dict[str, Any]

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=6)

class ResetPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordConfirmRequest(BaseModel):
    reset_token: str
    new_password: str = Field(..., min_length=6)

class LogoutRequest(BaseModel):
    access_token: str
    refresh_token: str


# ========== Пользователи ==========
class UserBase(BaseModel):
    email: EmailStr
    full_name: str = Field(..., min_length=2, max_length=100)
    phone: Optional[str] = None
    date_of_birth: Optional[date] = None
    role: UserRole = UserRole.TEACHER
    max_students: int = 20

class UserCreate(UserBase):
    password: str = Field(..., min_length=6)

class UserUpdate(BaseModel):
    full_name: Optional[str] = Field(None, min_length=2, max_length=100)
    phone: Optional[str] = None
    date_of_birth: Optional[date] = None
    new_password: Optional[str] = Field(None, min_length=6)
    max_students: Optional[int] = Field(None, ge=1, le=1000)
    is_active: Optional[bool] = None

class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str
    phone: Optional[str]
    date_of_birth: Optional[date]
    role: str
    max_students: int
    current_students_count: int
    is_active: bool
    created_at: Optional[datetime]
    last_login: Optional[datetime]
    updated_at: Optional[datetime]
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    assigned_departments: List[str] = []
    assigned_specialities: List[str] = []
    experience: Optional[str] = None
    education: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# ========== Направления и специальности ==========
class DepartmentBase(BaseModel):
    code: str = Field(..., min_length=1, max_length=20)
    name: str = Field(..., min_length=2, max_length=200)
    faculty: str = Field(..., max_length=200)
    description: Optional[str] = None
    is_active: bool = True
    dean: Optional[str] = None
    contact_email: Optional[EmailStr] = None
    contact_phone: Optional[str] = None

class DepartmentCreate(DepartmentBase):
    pass

class DepartmentUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=200)
    faculty: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = None
    is_active: Optional[bool] = None
    dean: Optional[str] = None
    contact_email: Optional[EmailStr] = None
    contact_phone: Optional[str] = None

class DepartmentResponse(DepartmentBase):
    id: str
    created_at: datetime
    updated_at: datetime
    total_students: int = 0
    total_teachers: int = 0

    model_config = ConfigDict(from_attributes=True)


class SpecialityBase(BaseModel):
    code: str = Field(..., min_length=1, max_length=20)
    name: str = Field(..., min_length=2, max_length=200)
    department_id: str
    study_duration: int = Field(4, ge=1, le=6)
    description: Optional[str] = None
    is_active: bool = True
    tuition_fee: Optional[float] = None
    required_exams: List[str] = []

class SpecialityCreate(SpecialityBase):
    pass

class SpecialityUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=200)
    study_duration: Optional[int] = Field(None, ge=1, le=6)
    description: Optional[str] = None
    is_active: Optional[bool] = None
    tuition_fee: Optional[float] = None
    required_exams: Optional[List[str]] = None

class SpecialityResponse(SpecialityBase):
    id: str
    created_at: datetime
    updated_at: datetime
    department_name: Optional[str] = None
    total_students: int = 0

    model_config = ConfigDict(from_attributes=True)


# ========== Студенты ==========
class StudentBase(BaseModel):
    russian_student_id: str = Field(..., min_length=1, max_length=50)
    full_name: str = Field(..., min_length=2, max_length=200)
    phone: str
    email: Optional[EmailStr] = None
    date_of_birth: Optional[date] = None
    department_id: Optional[str] = None
    speciality_id: Optional[str] = None
    priority_place: Optional[int] = Field(None, ge=1, le=10)
    status: StudentStatus = StudentStatus.ACTIVE
    additional_contacts: List[str] = []

    @validator('phone')
    def validate_phone(cls, v):
        phone_pattern = re.compile(r'^\+?[1-9]\d{1,14}$')
        if not phone_pattern.match(v):
            raise ValueError('Invalid phone number format')
        return v

    @validator('additional_contacts')
    def validate_additional_contacts(cls, v):
        for contact in v:
            if not isinstance(contact, str) or len(contact) > 100:
                raise ValueError('Invalid contact format')
        return v

class StudentCreate(StudentBase):
    pass

class StudentUpdateRequest(BaseModel):
    """Модель для обновления студента"""
    full_name: Optional[str] = Field(None, min_length=2, max_length=200)
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    date_of_birth: Optional[date] = None
    department_id: Optional[str] = None
    speciality_id: Optional[str] = None
    priority_place: Optional[int] = Field(None, ge=1, le=10)
    status: Optional[StudentStatus] = None
    additional_contacts: Optional[List[str]] = None

    @validator('phone')
    def validate_phone(cls, v):
        if v:
            phone_pattern = re.compile(r'^\+?[1-9]\d{1,14}$')
            if not phone_pattern.match(v):
                raise ValueError('Invalid phone number format')
        return v

class StudentUpdate(BaseModel):
    """Альтернативная модель для обновления студента (старая версия)"""
    full_name: Optional[str] = Field(None, min_length=2, max_length=200)
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    date_of_birth: Optional[date] = None
    department_id: Optional[str] = None
    speciality_id: Optional[str] = None
    priority_place: Optional[int] = Field(None, ge=1, le=10)
    assigned_teacher_id: Optional[str] = None
    status: Optional[StudentStatus] = None
    additional_contacts: Optional[List[str]] = None

    @validator('phone')
    def validate_phone(cls, v):
        if v:
            phone_pattern = re.compile(r'^\+?[1-9]\d{1,14}$')
            if not phone_pattern.match(v):
                raise ValueError('Invalid phone number format')
        return v

class StudentResponse(BaseModel):
    id: str
    russian_student_id: str
    full_name: str
    phone: str
    email: Optional[str]
    date_of_birth: Optional[date]
    department_id: Optional[str]
    speciality_id: Optional[str]
    department_name: Optional[str] = None
    speciality_name: Optional[str] = None
    priority_place: Optional[int] = 1
    status: str
    additional_contacts: List[str]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    last_communication_date: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ========== Поиск и фильтры ==========
class StudentFilter(BaseModel):
    teacher_id: Optional[str] = None
    status: Optional[StudentStatus] = None
    department_id: Optional[str] = None
    speciality_id: Optional[str] = None
    search: Optional[str] = None
    skip: int = Field(0, ge=0)
    limit: int = Field(20, ge=1, le=100)

class CommunicationFilter(BaseModel):
    student_id: Optional[str] = None
    communication_type: Optional[CommunicationType] = None
    status: Optional[CommunicationStatus] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    important_only: bool = False
    skip: int = Field(0, ge=0)
    limit: int = Field(50, ge=1, le=100)


# ========== История коммуникаций ==========
class CommunicationBase(BaseModel):
    student_id: str
    communication_type: CommunicationType = CommunicationType.CALL
    status: CommunicationStatus = CommunicationStatus.COMPLETED
    date_time: datetime
    duration_minutes: Optional[int] = Field(None, ge=1, le=1440)
    topic: str = Field(..., min_length=1, max_length=200)
    notes: str = Field(..., min_length=1, max_length=5000)
    next_action: Optional[str] = Field(None, max_length=200)
    next_action_date: Optional[datetime] = None
    attachment_urls: List[str] = []
    is_important: bool = False

    @validator('attachment_urls')
    def validate_attachment_urls(cls, v):
        for url in v:
            if not isinstance(url, str) or len(url) > 500:
                raise ValueError('Invalid URL format')
        return v

class CommunicationCreate(CommunicationBase):
    pass

class CommunicationUpdate(BaseModel):
    communication_type: Optional[CommunicationType] = None
    status: Optional[CommunicationStatus] = None
    date_time: Optional[datetime] = None
    duration_minutes: Optional[int] = Field(None, ge=1, le=1440)
    topic: Optional[str] = Field(None, min_length=1, max_length=200)
    notes: Optional[str] = Field(None, min_length=1, max_length=5000)
    next_action: Optional[str] = Field(None, max_length=200)
    next_action_date: Optional[datetime] = None
    attachment_urls: Optional[List[str]] = None
    is_important: Optional[bool] = None

class CommunicationResponse(BaseModel):
    id: str
    student_id: str
    communication_type: CommunicationType
    status: CommunicationStatus
    date_time: datetime
    duration_minutes: Optional[int]
    topic: str
    notes: str
    next_action: Optional[str]
    next_action_date: Optional[datetime]
    attachment_urls: List[str]
    is_important: bool
    created_by: str
    created_at: datetime
    updated_at: datetime
    student_name: Optional[str] = None
    student_phone: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# ========== Заявки на регистрацию преподавателей ==========
class TeacherRegistrationRequest(BaseModel):
    """Запрос на регистрацию преподавателя"""
    full_name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    phone: Optional[str] = None
    max_students: int = Field(20, ge=1, le=1000)
    departments: List[str] = []
    specialities: List[str] = []
    experience: Optional[str] = Field(None, max_length=500)
    education: Optional[str] = Field(None, max_length=500)
    message: Optional[str] = Field(None, max_length=1000)

    @validator('phone')
    def validate_phone(cls, v):
        if v:
            phone_pattern = re.compile(r'^\+?[1-9]\d{1,14}$')
            if not phone_pattern.match(v):
                raise ValueError('Phone must contain only digits and optional + sign')
        return v

class TeacherRequestResponse(BaseModel):
    """Ответ с информацией о заявке преподавателя"""
    id: str
    full_name: str
    email: str
    phone: Optional[str]
    max_students: int
    departments: List[str]
    specialities: List[str]
    experience: Optional[str]
    education: Optional[str]
    status: TeacherRequestStatus
    requested_at: datetime
    approved_at: Optional[datetime]
    rejected_at: Optional[datetime]
    approved_by: Optional[str]
    rejected_by: Optional[str]
    rejection_reason: Optional[str]
    user_id: Optional[str]

    model_config = ConfigDict(from_attributes=True)

class TeacherRequestUpdate(BaseModel):
    """Обновление заявки преподавателя (для администратора)"""
    status: TeacherRequestStatus
    departments: Optional[List[str]] = None
    rejection_reason: Optional[str] = Field(None, max_length=500)

class TeacherRequestStatusResponse(BaseModel):
    """Статус заявки преподавателя"""
    request_id: str
    status: TeacherRequestStatus
    message: Optional[str] = None
    user_id: Optional[str] = None
    email: Optional[str] = None


# ========== Запросы по студентам ==========
class StudentRequestBase(BaseModel):
    """Базовая модель запроса по студенту"""
    student_id: Optional[str] = None
    teacher_id: Optional[str] = None
    request_type: StudentRequestType
    title: str = Field(..., max_length=200)
    message: str = Field(..., max_length=2000)
    priority: NotificationPriority = NotificationPriority.NORMAL
    related_data: Optional[Dict[str, Any]] = None

class StudentRequestCreate(StudentRequestBase):
    """Создание запроса по студенту"""
    pass

class StudentRequestResponse(StudentRequestBase):
    """Ответ с информацией о запросе по студенту"""
    id: str
    status: StudentRequestStatus
    created_by: str
    created_at: datetime
    updated_at: datetime
    resolved_at: Optional[datetime]
    resolved_by: Optional[str]
    resolution_notes: Optional[str] = Field(None, max_length=1000)
    assigned_to: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

class StudentRequestUpdate(BaseModel):
    """Обновление запроса по студенту"""
    status: Optional[StudentRequestStatus] = None
    assigned_to: Optional[str] = None
    resolution_notes: Optional[str] = Field(None, max_length=1000)
    priority: Optional[NotificationPriority] = None


# ========== Статистика ==========
class CommunicationStats(BaseModel):
    total_communications: int
    by_type: Dict[str, int]
    by_status: Dict[str, int]
    recent_communications: List[Dict[str, Any]]
    upcoming_actions: List[Dict[str, Any]]

class StudentStats(BaseModel):
    total_students: int
    active_students: int
    inactive_students: int
    by_status: Dict[str, int]
    by_department: Dict[str, int]

class TeacherDashboard(BaseModel):
    teacher_info: UserResponse
    student_stats: StudentStats
    communication_stats: CommunicationStats
    recent_students: List[StudentResponse]
    upcoming_communications: List[CommunicationResponse]

class AdminStats(BaseModel):
    """Статистика для администратора"""
    total_teachers: int
    total_students: int
    active_teachers: int
    active_students: int
    pending_teacher_requests: int
    pending_student_requests: int
    pending_department_requests: int
    recent_registrations: List[Dict[str, Any]] = []
    students_by_department: Dict[str, int] = {}
    students_by_speciality: Dict[str, int] = {}
    teachers_by_student_count: List[Dict[str, Any]] = []
    system_status: Dict[str, Any] = {}


# ========== Комбинированные ответы ==========
class StudentWithCommunications(BaseModel):
    student: StudentResponse
    communications: List[CommunicationResponse]
    total_communications: int
    last_communication: Optional[datetime]
    next_planned_communication: Optional[datetime]

class BatchStudentCreate(BaseModel):
    students: List[StudentCreate]

class BatchStudentResponse(BaseModel):
    created: int
    failed: int
    student_ids: List[str]
    errors: List[Dict[str, Any]] = []


# ========== Ответы с пагинацией ==========
class PaginatedResponse(BaseModel):
    items: List[Any]
    total: int
    page: int
    page_size: int
    total_pages: int

class StudentsPaginated(PaginatedResponse):
    items: List[StudentResponse]

class CommunicationsPaginated(PaginatedResponse):
    items: List[CommunicationResponse]


# ========== Административные действия ==========
class TeacherActivationRequest(BaseModel):
    """Запрос на активацию/деактивацию преподавателя"""
    teacher_id: str
    action: str = Field(..., pattern="^(activate|deactivate)$")
    reason: Optional[str] = Field(None, max_length=500)

class DepartmentAssignment(BaseModel):
    """Назначение направлений/специальностей преподавателю"""
    teacher_id: str
    department_ids: List[str] = []
    speciality_ids: List[str] = []
    replace_existing: bool = True

class BulkTeacherRegistration(BaseModel):
    """Массовая регистрация преподавателей"""
    teachers: List[TeacherRegistrationRequest]
    default_departments: Optional[List[str]] = []
    default_specialities: Optional[List[str]] = []
    send_welcome_email: bool = True

class BulkRegistrationResult(BaseModel):
    """Результат массовой регистрации"""
    total: int
    successful: int
    failed: int
    details: List[Dict[str, Any]] = []
    errors: List[str] = []


# ========== Отчеты администратора ==========
class AdminReportRequest(BaseModel):
    """Запрос на генерацию отчета"""
    report_type: ReportType
    format: str = Field("json", pattern="^(json|csv|xlsx|pdf)$")
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    department_id: Optional[str] = None
    speciality_id: Optional[str] = None
    include_details: bool = False

class AdminReportResponse(BaseModel):
    """Ответ с отчетом"""
    report_id: str
    report_type: str
    format: str
    download_url: Optional[str]
    generated_at: datetime
    size_bytes: Optional[int]
    expires_at: Optional[datetime]


# ========== Системные настройки ==========
class SystemSettings(BaseModel):
    """Системные настройки"""
    registration_enabled: bool = True
    teacher_registration_requires_approval: bool = True
    student_registration_requires_approval: bool = False
    max_students_per_teacher: int = 100
    default_teacher_max_students: int = 20
    notification_email: Optional[str] = None
    system_email: Optional[str] = None
    maintenance_mode: bool = False
    maintenance_message: Optional[str] = None

class SettingsUpdateResponse(BaseModel):
    """Ответ с настройками"""
    system_settings: SystemSettings
    updated_at: datetime
    updated_by: Optional[str]


# ========== Системные сообщения ==========
class ErrorResponse(BaseModel):
    detail: str
    code: Optional[str] = None

class SuccessResponse(BaseModel):
    message: str
    data: Optional[Dict[str, Any]] = None

class HealthResponse(BaseModel):
    status: str
    database: str
    auth: str
    version: str
    uptime: Optional[float] = None


# ========== Экспорт данных ==========
class ExportRequest(BaseModel):
    format: str = Field("json", pattern="^(json|csv|xlsx)$")
    include_communications: bool = False
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None

class ExportResponse(BaseModel):
    export_id: str
    status: str
    download_url: Optional[str] = None
    created_at: datetime


# ========== Настройки пользователя ==========
class UserSettings(BaseModel):
    email_notifications: bool = True
    sms_notifications: bool = False
    daily_summary: bool = True
    weekly_report: bool = True
    language: str = "ru"
    timezone: str = "Europe/Moscow"
    theme: str = "light"

class UserSettingsResponse(BaseModel):
    user_id: str
    settings: UserSettings
    updated_at: datetime


# ========== Валидация токенов ==========
class TokenData(BaseModel):
    sub: str
    email: str
    role: str
    exp: int
    iat: int

class TokenValidation(BaseModel):
    valid: bool
    user_id: Optional[str] = None
    role: Optional[str] = None
    expires_in: Optional[int] = None


# ========== Вспомогательные модели ==========
class ContactInfo(BaseModel):
    type: str
    value: str
    is_primary: bool = False

    @validator('type')
    def validate_type(cls, v):
        allowed_types = ['phone', 'email', 'telegram', 'whatsapp', 'other']
        if v not in allowed_types:
            raise ValueError(f'Contact type must be one of: {allowed_types}')
        return v

class Address(BaseModel):
    country: str
    city: str
    street: str
    postal_code: Optional[str]
    apartment: Optional[str]

class EducationInfo(BaseModel):
    institution: str
    faculty: str
    specialization: str
    year_start: int
    year_end: Optional[int]
    degree: Optional[str]


# ========== Расширенная модель студента ==========
class ExtendedStudentCreate(StudentBase):
    contacts: List[ContactInfo] = []
    address: Optional[Address] = None
    education_info: Optional[EducationInfo] = None
    guardian_name: Optional[str] = None
    guardian_phone: Optional[str] = None
    guardian_relation: Optional[str] = None

class ExtendedStudentResponse(StudentResponse):
    contacts: List[ContactInfo] = []
    address: Optional[Address] = None
    education_info: Optional[EducationInfo] = None
    guardian_name: Optional[str] = None
    guardian_phone: Optional[str] = None
    guardian_relation: Optional[str] = None
    communication_stats: Optional[Dict[str, Any]] = None


# ========== Аналитика ==========
class AnalyticsRequest(BaseModel):
    period: str = Field("month", pattern="^(day|week|month|quarter|year)$")
    metrics: List[str] = ["communications", "students", "engagement"]

class AnalyticsResponse(BaseModel):
    period: str
    metrics: Dict[str, Any]
    trends: Dict[str, List[float]]
    comparisons: Dict[str, Any]
    generated_at: datetime


# ========== Экспорт/Импорт ==========
class ImportRequest(BaseModel):
    file_url: str
    file_type: str
    mapping: Optional[Dict[str, str]] = None
    skip_first_row: bool = True

    @validator('file_type')
    def validate_file_type(cls, v):
        allowed_types = ['csv', 'xlsx', 'json']
        if v not in allowed_types:
            raise ValueError(f'File type must be one of: {allowed_types}')
        return v

class ImportResponse(BaseModel):
    import_id: str
    status: str
    processed: int
    successful: int
    failed: int
    errors: List[str] = []
    created_at: datetime
class AdminNotificationBase(BaseModel):
    """Базовая модель уведомления администратора"""
    title: str = Field(..., min_length=1, max_length=200)
    message: str = Field(..., min_length=1)
    notification_type: str = Field(..., description="teacher_request, student_request, department_access, system, alert")
    priority: str = Field(default="normal", description="low, normal, high, urgent")
    related_id: Optional[str] = None
    action_url: Optional[str] = None
    is_read: bool = False

    class Config:
        from_attributes = True
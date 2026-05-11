from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, JSON, Enum, Float
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime
import enum

Base = declarative_base()

# Enums для статусов
class StudentStatus(enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    UNKNOWN = "unknown"
    ENROLLED = "enrolled"
    WITHDRAWN = "withdrawn"


class ApplicationStatus(enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    PAID = "paid"


class ContactStatus(enum.Enum):
    NEW = "new"
    MET = "был на встрече"
    INTERESTED = "заинтересован в поступлении"
    ORIGINAL_SUBMITTED = "подан оригинал"
    WAITING_ORIGINAL = "ждем оригинал"
    NOT_INTERESTED = "не заинтересован/не интересно"


class ContactType(enum.Enum):
    CALL = "звонок"
    MESSAGE = "сообщение"
    MEETING = "личная встреча"


class CommunicationType(enum.Enum):
    CALL = "call"
    MEETING = "meeting"
    EMAIL = "email"
    MESSAGE = "message"


class CommunicationStatus(enum.Enum):
    COMPLETED = "completed"
    PLANNED = "planned"


class UserRole(enum.Enum):
    TEACHER = "teacher"
    ADMIN = "admin"


class StudyLevel(enum.Enum):
    BACHELOR = "Бакалавриат"
    MASTER = "Магистратура"
    SPECIALIST = "Специалитет"
    PHD = "Аспирантура"


class StudyForm(enum.Enum):
    FULL_TIME = "Очная"
    PART_TIME = "Очно-заочная"
    CORRESPONDENCE = "Заочная"


class StudyBasis(enum.Enum):
    BUDGET = "Бюджетная"
    PAID = "Платная"
    TARGET = "Целевая"


class PriorContact(enum.Enum):
    TELEGRAM = "телеграмм"
    VK = "вк"
    MESSAGES = "просто сообщения"
    PHONE = "звонок"
    URL = "ссылка"


# ИСПРАВЛЕНО: значения в ВЕРХНЕМ РЕГИСТРЕ
class MeetingStatus(enum.Enum):
    """Статус посещения встречи/сбора"""
    NOT_MET = "NOT_MET"
    MET = "MET"


class CallStatus(enum.Enum):
    """Статус дозвона"""
    NOT_REACHED = "NOT_REACHED"
    REACHED = "REACHED"


class DecisionStatus(enum.Enum):
    """Статус решения о поступлении"""
    THINKING = "THINKING"
    DECIDED = "DECIDED"


class DocumentsStatus(enum.Enum):
    """Статус подачи документов"""
    NOT_SUBMITTED = "NOT_SUBMITTED"
    ORIGINAL_SUBMITTED = "ORIGINAL_SUBMITTED"
    WAITING_ORIGINAL = "WAITING_ORIGINAL"
    ENROLLED = "ENROLLED"


# Модель Department (Направления)
class Department(Base):
    __tablename__ = "departments"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    faculty = Column(String, nullable=False)

    specialities = relationship("Speciality", back_populates="department", cascade="all, delete-orphan")
    applications = relationship("StudentApplication", back_populates="department")


# Модель Speciality (Специальности)
class Speciality(Base):
    __tablename__ = "specialities"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=False)

    department = relationship("Department", back_populates="specialities")
    profiles = relationship("Profile", back_populates="speciality", cascade="all, delete-orphan")
    applications = relationship("StudentApplication", back_populates="speciality")


# Модель Profile (Профили/Программы внутри специальности)
class Profile(Base):
    __tablename__ = "profiles"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, nullable=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    speciality_id = Column(Integer, ForeignKey("specialities.id"), nullable=False)

    study_level = Column(Enum(StudyLevel), nullable=True)
    study_form = Column(Enum(StudyForm), nullable=True)
    study_basis = Column(Enum(StudyBasis), nullable=True)
    budget_places = Column(Integer, nullable=True)
    paid_places = Column(Integer, nullable=True)
    target_places = Column(Integer, nullable=True)
    passing_score = Column(Integer, nullable=True)
    entrance_tests = Column(JSON, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # ===== НОВЫЕ ПОЛЯ ДЛЯ СТАТИСТИКИ ГРУППЫ =====
    # Общая статистика
    total_applications = Column(Integer, default=0, comment="Всего заявлений в группе")
    applications_submitted = Column(Integer, default=0, comment="Подало документы")
    enrolled = Column(Integer, default=0, comment="Зачислено")
    average_score = Column(Float, default=0, comment="Средний балл")
    min_score = Column(Integer, default=0, comment="Минимальный балл")
    max_score = Column(Integer, default=0, comment="Максимальный балл")
    competition = Column(Float, default=0, comment="Конкурс чел/место")

    # Бюджетная статистика
    budget_filled = Column(Integer, default=0, comment="Бюджетных мест заполнено")
    budget_free = Column(Integer, default=0, comment="Бюджетных мест свободно")
    budget_applicants_in_range = Column(Integer, default=0, comment="Абитуриентов в пределах мест")
    budget_applicants_with_consent = Column(Integer, default=0, comment="Подало согласие на бюджет")
    budget_passing_score = Column(Integer, default=0, comment="Проходной балл на бюджет")

    # Платная статистика
    paid_filled = Column(Integer, default=0, comment="Платных мест заполнено")
    paid_free = Column(Integer, default=0, comment="Платных мест свободно")
    paid_applicants_with_consent = Column(Integer, default=0, comment="Подало согласие на платное")

    # Целевая статистика
    target_filled = Column(Integer, default=0, comment="Целевых мест заполнено")
    target_free = Column(Integer, default=0, comment="Целевых мест свободно")
    target_applicants_with_consent = Column(Integer, default=0, comment="Подало согласие на целевое")

    # Проходные баллы
    passing_score_current = Column(Integer, default=0, comment="Текущий проходной балл")
    passing_score_last_year = Column(Integer, default=0, comment="Проходной балл прошлого года")

    # Время последнего обновления статистики
    statistics_updated_at = Column(DateTime, nullable=True, comment="Время последнего обновления статистики")

    speciality = relationship("Speciality", back_populates="profiles")
    applications = relationship("StudentApplication", back_populates="profile")
# Модель StudentApplication (Заявление абитуриента на специальность)
class StudentApplication(Base):
    __tablename__ = "student_applications"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=False)
    speciality_id = Column(Integer, ForeignKey("specialities.id"), nullable=False)
    profile_id = Column(Integer, ForeignKey("profiles.id"), nullable=True)

    position = Column(Integer, nullable=True)
    priority = Column(Integer, nullable=True)
    is_main_contest = Column(Boolean, default=False)
    participation = Column(Boolean, default=True)
    consent_status = Column(Boolean, default=False)
    application_status = Column(Enum(ApplicationStatus), default=ApplicationStatus.PENDING)
    total_score = Column(Integer, nullable=True)

    main_contest_other = Column(String, nullable=True)
    higher_priority_other = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    study_form = Column(Enum(StudyForm), nullable=True)
    study_basis = Column(Enum(StudyBasis), nullable=True)
    study_level = Column(Enum(StudyLevel), nullable=True)

    budget_places_total = Column(Integer, nullable=True)
    budget_places_filled = Column(Integer, nullable=True)
    paid_places_total = Column(Integer, nullable=True)
    paid_places_filled = Column(Integer, nullable=True)
    target_places_total = Column(Integer, nullable=True)
    target_places_filled = Column(Integer, nullable=True)

    student = relationship("Student", back_populates="applications")
    department = relationship("Department", back_populates="applications")
    speciality = relationship("Speciality", back_populates="applications")
    profile = relationship("Profile", back_populates="applications")


# Модель Student (Абитуриент)
class Student(Base):
    __tablename__ = "students"

    id = Column(Integer, primary_key=True, index=True)
    russian_student_id = Column(Integer, nullable=True)
    full_name = Column(String, nullable=False)
    phone = Column(String, nullable=True)
    additional_contacts = Column(JSON, nullable=True)
    prior_contact = Column(Enum(PriorContact), nullable=True)

    study_level = Column(Enum(StudyLevel), nullable=True)
    study_form = Column(Enum(StudyForm), nullable=True)
    study_basis = Column(Enum(StudyBasis), nullable=True)

    status = Column(Enum(StudentStatus), default=StudentStatus.ACTIVE)
    contact_status = Column(Enum(ContactStatus), default=ContactStatus.NEW)
    contact_type = Column(Enum(ContactType), nullable=True)

    # НОВЫЕ СТАТУСЫ из Figma - значения в ВЕРХНЕМ РЕГИСТРЕ
    meeting_status = Column(Enum(MeetingStatus), default=MeetingStatus.NOT_MET)
    call_status = Column(Enum(CallStatus), default=CallStatus.NOT_REACHED)
    decision_status = Column(Enum(DecisionStatus), default=DecisionStatus.THINKING)
    documents_status = Column(Enum(DocumentsStatus), default=DocumentsStatus.NOT_SUBMITTED)

    last_communication_date = Column(DateTime, nullable=True)
    imported_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    kurator_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    applications = relationship("StudentApplication", back_populates="student", cascade="all, delete-orphan")
    communications = relationship("Communication", back_populates="student", cascade="all, delete-orphan")
    kurator = relationship("User", foreign_keys=[kurator_id], back_populates="kurator_students")


# Модель User (Пользователи)
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    full_name = Column(String, nullable=False)
    phone = Column(String, nullable=True)
    role = Column(Enum(UserRole), default=UserRole.TEACHER)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)

    assigned_departments = Column(JSON, default=list)
    assigned_specialities = Column(JSON, default=list)
    assigned_profiles = Column(JSON, default=list)

    active_contact = Column(String(500), nullable=True)
    active_contact_type = Column(String(50), nullable=True)
    active_contact_updated_at = Column(DateTime, nullable=True)

    created_communications = relationship("Communication", foreign_keys="Communication.created_by",
                                          back_populates="creator")
    kurator_students = relationship("Student", foreign_keys="Student.kurator_id", back_populates="kurator")
    notifications = relationship("Notification", back_populates="teacher")
    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")


# Модель Communication (Коммуникации)
class Communication(Base):
    __tablename__ = "communications"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    communication_type = Column(Enum(CommunicationType), nullable=False)
    status = Column(Enum(CommunicationStatus), default=CommunicationStatus.COMPLETED)
    date_time = Column(DateTime, nullable=False)
    duration_minutes = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    student = relationship("Student", back_populates="communications")
    creator = relationship("User", foreign_keys=[created_by], back_populates="created_communications")


# Модель Notification (Уведомления)
class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    teacher_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    message = Column(Text, nullable=False)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    type = Column(String, nullable=True)
    link = Column(String, nullable=True)

    teacher = relationship("User", back_populates="notifications")


# Модель для хранения refresh токенов
class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True, index=True)
    token = Column(String, unique=True, index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    revoked = Column(Boolean, default=False)

    user = relationship("User", back_populates="refresh_tokens")
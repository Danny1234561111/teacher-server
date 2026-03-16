# database/schema.py
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, JSON, Enum
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


# Модель Department (Направления)
class Department(Base):
    __tablename__ = "departments"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, nullable=False)  # Код направления
    name = Column(String, nullable=False)  # Название
    faculty = Column(String, nullable=False)  # Факультет

    # Связи
    specialities = relationship("Speciality", back_populates="department", cascade="all, delete-orphan")
    students = relationship("Student", back_populates="department")


# Модель Speciality (Специальности)
class Speciality(Base):
    __tablename__ = "specialities"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, nullable=False)  # Код специальности
    name = Column(String, nullable=False)  # Название
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=False)  # ID направления

    # Связи
    department = relationship("Department", back_populates="specialities")
    profiles = relationship("Profile", back_populates="speciality", cascade="all, delete-orphan")
    students = relationship("Student", back_populates="speciality")


# Модель Profile (Профили/Программы внутри специальности)
class Profile(Base):
    __tablename__ = "profiles"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, nullable=True)  # Код профиля (может отсутствовать)
    name = Column(String, nullable=False)  # Название профиля/программы
    description = Column(Text, nullable=True)  # Описание профиля
    speciality_id = Column(Integer, ForeignKey("specialities.id"), nullable=False)  # ID специальности

    # Дополнительные поля для профиля
    study_level = Column(Enum(StudyLevel), nullable=True)  # Уровень подготовки (может отличаться от специальности)
    study_form = Column(Enum(StudyForm), nullable=True)  # Форма обучения
    study_basis = Column(Enum(StudyBasis), nullable=True)  # Основание
    budget_places = Column(Integer, nullable=True)  # Количество бюджетных мест
    paid_places = Column(Integer, nullable=True)  # Количество платных мест
    target_places = Column(Integer, nullable=True)  # Количество целевых мест
    passing_score = Column(Integer, nullable=True)  # Проходной балл прошлого года
    entrance_tests = Column(JSON, nullable=True)  # Вступительные испытания (JSON массив)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Связи
    speciality = relationship("Speciality", back_populates="profiles")
    students = relationship("Student", back_populates="profile")


# Модель Student (Абитуриент)
class Student(Base):
    __tablename__ = "students"

    # ИДЕНТИФИКАЦИЯ
    id = Column(Integer, primary_key=True, index=True)
    russian_student_id = Column(Integer, nullable=True)  # Российский ID студента (7 цифр)

    # ЛИЧНЫЕ ДАННЫЕ
    full_name = Column(String, nullable=False)  # ФИО полностью
    phone = Column(String, nullable=True)  # Телефон
    additional_contacts = Column(JSON, nullable=True)  # Доп. контакты (JSON массив)
    prior_contact = Column(Enum(PriorContact), nullable=True)  # Приоритетная форма контакта

    # КОНКУРСНАЯ ГРУППА (контекст заявки)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)  # ID факультета/направления
    speciality_id = Column(Integer, ForeignKey("specialities.id"), nullable=True)  # ID специальности
    profile_id = Column(Integer, ForeignKey("profiles.id"), nullable=True)  # ID профиля/программы
    study_level = Column(Enum(StudyLevel), nullable=True)  # Уровень подготовки
    study_form = Column(Enum(StudyForm), nullable=True)  # Форма обучения
    study_basis = Column(Enum(StudyBasis), nullable=True)  # Основание

    # ПОЗИЦИИ В КОНКУРСЕ
    position = Column(Integer, nullable=True)  # № п/п в списке
    priority = Column(Integer, nullable=True)  # Приоритет (1…)
    is_main_contest = Column(Boolean, nullable=True)  # Основной конкурс (Да/Нет)
    participation = Column(Boolean, default=True)  # Участие в конкурсе (Да/Нет)
    main_contest_other = Column(String, nullable=True)  # Основной в другой КГ
    higher_priority_other = Column(String, nullable=True)  # Высший в другой КГ

    # СТАТУСЫ
    status = Column(Enum(StudentStatus), default=StudentStatus.ACTIVE)  # Общий статус
    application_status = Column(Enum(ApplicationStatus), default=ApplicationStatus.PENDING)  # Статус заявления
    contact_status = Column(Enum(ContactStatus), default=ContactStatus.NEW)  # Статус контакта
    contact_type = Column(Enum(ContactType), nullable=True)  # Тип контакта
    consent_status = Column(Boolean, nullable=True)  # Согласие на зачисление (Да/Нет)

    # БАЛЛЫ
    total_score = Column(Integer, nullable=True)  # Сумма баллов (ИТОГ)
    last_communication_date = Column(DateTime, nullable=True)  # Последняя коммуникация

    # СЛУЖЕБНЫЕ
    imported_at = Column(DateTime, nullable=True)  # Дата импорта из ИГУ
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    kurator_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # ID куратора

    # Связи
    communications = relationship("Communication", back_populates="student", cascade="all, delete-orphan")
    kurator = relationship("User", foreign_keys=[kurator_id], back_populates="kurator_students")
    department = relationship("Department", foreign_keys=[department_id], back_populates="students")
    speciality = relationship("Speciality", foreign_keys=[speciality_id], back_populates="students")
    profile = relationship("Profile", foreign_keys=[profile_id], back_populates="students")


# Модель User (Пользователи)
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)  # Email пользователя
    full_name = Column(String, nullable=False)  # Полное имя
    phone = Column(String, nullable=True)  # Телефон
    role = Column(Enum(UserRole), default=UserRole.TEACHER)  # Роль (teacher/admin)
    hashed_password = Column(String, nullable=False)  # Хешированный пароль
    is_active = Column(Boolean, default=True)  # Активен/неактивен

    # Назначенные направления и специальности
    assigned_departments = Column(JSON, default=list)  # ID направлений (JSON массив)
    assigned_specialities = Column(JSON, default=list)  # ID специальностей (JSON массив)
    assigned_profiles = Column(JSON, default=list)  # ID профилей (JSON массив)

    # Связи
    created_communications = relationship("Communication", foreign_keys="Communication.created_by",
                                          back_populates="creator")
    kurator_students = relationship("Student", foreign_keys="Student.kurator_id", back_populates="kurator")
    notifications = relationship("Notification", back_populates="teacher")
    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")


# Модель Communication (Коммуникации)
class Communication(Base):
    __tablename__ = "communications"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)  # ID студента
    communication_type = Column(Enum(CommunicationType), nullable=False)  # Тип
    status = Column(Enum(CommunicationStatus), default=CommunicationStatus.COMPLETED)  # Статус
    date_time = Column(DateTime, nullable=False)  # Дата и время
    duration_minutes = Column(Integer, nullable=True)  # Длительность в минутах
    notes = Column(Text, nullable=True)  # Заметки
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)  # ID создателя
    created_at = Column(DateTime, default=datetime.utcnow)

    # Связи
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
    type = Column(String, nullable=True)  # Тип уведомления
    link = Column(String, nullable=True)  # Ссылка для перехода

    # Связи
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

    # Связи
    user = relationship("User", back_populates="refresh_tokens")
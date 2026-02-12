from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, Numeric, JSON, Date
from sqlalchemy.orm import relationship, DeclarativeBase
from datetime import datetime


# Базовая модель для SQLAlchemy 2.0
class Base(DeclarativeBase):
    pass


# Таблица пользователей
class User(Base):
    __tablename__ = 'users'

    id = Column(String(50), primary_key=True)
    email = Column(String(100), unique=True, nullable=False, index=True)
    full_name = Column(String(200), nullable=False)
    phone = Column(String(20), nullable=True)
    role = Column(String(20), nullable=False, default='teacher')  # admin, teacher, student
    date_of_birth = Column(Date, nullable=True)
    max_students = Column(Integer, default=20)
    current_students_count = Column(Integer, default=0)
    assigned_departments = Column(JSON, default=list)
    assigned_specialities = Column(JSON, default=list)
    password_hash = Column(String(255), nullable=False)  # Хеш пароля
    experience = Column(Text, nullable=True)
    education = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    approved_by = Column(String(50), ForeignKey('users.id'), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    last_login = Column(DateTime, nullable=True)

    # Связи
    approver = relationship('User', remote_side=[id], backref='approved_users')
    communications_created = relationship('Communication', back_populates='creator')
    students_assigned = relationship('Student', back_populates='assigned_teacher')
    refresh_tokens = relationship('RefreshToken', back_populates='user', cascade="all, delete-orphan")

    # Индексы
    __table_args__ = (
        {'extend_existing': True}
    )


# Таблица refresh токенов
class RefreshToken(Base):
    __tablename__ = 'refresh_tokens'

    id = Column(String(50), primary_key=True)  # JTI токена
    user_id = Column(String(50), ForeignKey('users.id'), nullable=False)
    token_hash = Column(String(255), nullable=False)  # Хеш токена для безопасного хранения
    device_info = Column(JSON, default=dict)  # Информация об устройстве
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    revoked_at = Column(DateTime, nullable=True)
    is_revoked = Column(Boolean, default=False)

    # Связи
    user = relationship('User', back_populates='refresh_tokens')


# Таблица направлений (факультетов)
class Department(Base):
    __tablename__ = 'departments'

    id = Column(String(50), primary_key=True)
    code = Column(String(20), unique=True, nullable=False, index=True)
    name = Column(String(200), nullable=False)
    faculty = Column(String(100), nullable=True)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    dean = Column(String(100), nullable=True)
    contact_email = Column(String(100), nullable=True)
    contact_phone = Column(String(20), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Связи
    specialities = relationship('Speciality', back_populates='department', cascade="all, delete-orphan")
    students = relationship('Student', back_populates='department')


# Таблица специальностей
class Speciality(Base):
    __tablename__ = 'specialities'

    id = Column(String(50), primary_key=True)
    code = Column(String(20), unique=True, nullable=False, index=True)
    name = Column(String(200), nullable=False)
    department_id = Column(String(50), ForeignKey('departments.id'), nullable=False)
    study_duration = Column(Integer, default=4)  # годы
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    tuition_fee = Column(Numeric(10, 2), nullable=True)
    required_exams = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Связи
    department = relationship('Department', back_populates='specialities')
    students = relationship('Student', back_populates='speciality')


# Таблица студентов
class Student(Base):
    __tablename__ = 'students'

    id = Column(String(50), primary_key=True)
    russian_student_id = Column(String(50), unique=True, nullable=True, index=True)
    full_name = Column(String(200), nullable=False)
    phone = Column(String(20), nullable=False)
    email = Column(String(100), nullable=True)
    date_of_birth = Column(Date, nullable=True)
    status = Column(String(20), default='active')  # active, inactive, graduated, dropped
    application_status = Column(String(20), default='pending')  # pending, accepted, rejected
    department_id = Column(String(50), ForeignKey('departments.id'), nullable=True)
    speciality_id = Column(String(50), ForeignKey('specialities.id'), nullable=True)
    priority_place = Column(Integer, default=1)
    exam_scores = Column(JSON, default=dict)
    additional_contacts = Column(JSON, default=list)
    notes = Column(Text, nullable=True)
    assigned_teacher_id = Column(String(50), ForeignKey('users.id'), nullable=True)
    last_communication_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Связи
    department = relationship('Department', back_populates='students')
    speciality = relationship('Speciality', back_populates='students')
    assigned_teacher = relationship('User', back_populates='students_assigned')
    communications = relationship('Communication', back_populates='student', cascade="all, delete-orphan")

    # Индексы
    __table_args__ = (
        {'extend_existing': True}
    )


# Таблица заявок преподавателей
class TeacherRequest(Base):
    __tablename__ = 'teacher_requests'

    id = Column(String(50), primary_key=True)
    full_name = Column(String(200), nullable=False)
    email = Column(String(100), nullable=False, index=True)
    phone = Column(String(20), nullable=True)
    max_students = Column(Integer, default=20)
    status = Column(String(20), default='pending')  # pending, approved, rejected
    requested_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    message = Column(Text, nullable=True)
    assigned_departments = Column(JSON, default=list)
    experience = Column(Text, nullable=True)
    education = Column(Text, nullable=True)
    approved_by = Column(String(50), ForeignKey('users.id'), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    rejected_by = Column(String(50), ForeignKey('users.id'), nullable=True)
    rejected_at = Column(DateTime, nullable=True)
    rejection_reason = Column(Text, nullable=True)
    user_id = Column(String(50), ForeignKey('users.id'), nullable=True)

    # Связи
    approver = relationship('User', foreign_keys=[approved_by])
    rejecter = relationship('User', foreign_keys=[rejected_by])
    user = relationship('User', foreign_keys=[user_id])


# Таблица заявок студентов
class StudentRequest(Base):
    __tablename__ = 'student_requests'

    id = Column(String(50), primary_key=True)
    user_id = Column(String(50), ForeignKey('users.id'), nullable=True)
    email = Column(String(100), nullable=False)
    full_name = Column(String(200), nullable=False)
    phone = Column(String(20), nullable=True)
    status = Column(String(20), default='pending')  # pending, in_progress, resolved, rejected, closed
    requested_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    student_data = Column(JSON, default=dict)
    processed_by = Column(String(50), ForeignKey('users.id'), nullable=True)
    processed_at = Column(DateTime, nullable=True)
    request_type = Column(String(50), nullable=True)  # department_change, teacher_change, information, other
    title = Column(String(200), nullable=True)
    message = Column(Text, nullable=True)
    priority = Column(String(20), default='normal')  # low, normal, high, urgent
    related_data = Column(JSON, nullable=True)
    created_by = Column(String(50), ForeignKey('users.id'), nullable=True)
    assigned_to = Column(String(50), ForeignKey('users.id'), nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    resolution_notes = Column(Text, nullable=True)

    # Связи
    user = relationship('User', foreign_keys=[user_id])
    processor = relationship('User', foreign_keys=[processed_by])
    creator = relationship('User', foreign_keys=[created_by])
    assignee = relationship('User', foreign_keys=[assigned_to])


# Таблица коммуникаций
class Communication(Base):
    __tablename__ = 'communications'

    id = Column(String(50), primary_key=True)
    student_id = Column(String(50), ForeignKey('students.id'), nullable=False)
    communication_type = Column(String(20), nullable=False, default='call')  # call, meeting, email, message, other
    status = Column(String(20), nullable=False, default='completed')  # planned, completed, cancelled, rescheduled
    date_time = Column(DateTime, nullable=False, default=datetime.utcnow)
    duration_minutes = Column(Integer, nullable=True)
    topic = Column(String(200), nullable=False)
    notes = Column(Text, nullable=False)
    next_action = Column(String(200), nullable=True)
    next_action_date = Column(DateTime, nullable=True)
    attachment_urls = Column(JSON, default=list)
    is_important = Column(Boolean, default=False)
    created_by = Column(String(50), ForeignKey('users.id'), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Связи
    student = relationship('Student', back_populates='communications')
    creator = relationship('User', back_populates='communications_created')


# Таблица уведомлений администратора
class AdminNotification(Base):
    __tablename__ = 'admin_notifications'

    id = Column(String(50), primary_key=True)
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)
    notification_type = Column(String(50),
                               nullable=False)  # teacher_request, student_request, department_access, system, alert
    priority = Column(String(20), default='normal')  # low, normal, high, urgent
    related_id = Column(String(50), nullable=True)
    action_url = Column(String(500), nullable=True)
    is_read = Column(Boolean, default=False)
    created_by = Column(String(50), ForeignKey('users.id'), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    read_at = Column(DateTime, nullable=True)

    # Связи
    creator = relationship('User')


# Таблица системных настроек
class SystemSetting(Base):
    __tablename__ = 'system_settings'

    id = Column(String(50), primary_key=True, default='main')
    registration_enabled = Column(Boolean, default=True)
    teacher_registration_requires_approval = Column(Boolean, default=True)
    student_registration_requires_approval = Column(Boolean, default=False)
    max_students_per_teacher = Column(Integer, default=100)
    default_teacher_max_students = Column(Integer, default=20)
    notification_email = Column(String(100), nullable=True)
    system_email = Column(String(100), nullable=True)
    maintenance_mode = Column(Boolean, default=False)
    maintenance_message = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    updated_by = Column(String(50), ForeignKey('users.id'), nullable=True)

    # Связи
    updater = relationship('User')


# Таблица запросов доступа к направлениям
class DepartmentAccessRequest(Base):
    __tablename__ = 'department_access_requests'

    id = Column(String(50), primary_key=True)
    teacher_id = Column(String(50), ForeignKey('users.id'), nullable=False)
    department_ids = Column(JSON, nullable=False)
    speciality_ids = Column(JSON, default=list)
    reason = Column(Text, nullable=False)
    message = Column(Text, nullable=True)
    status = Column(String(20), default='pending')  # pending, approved, rejected
    requested_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    reviewed_at = Column(DateTime, nullable=True)
    reviewed_by = Column(String(50), ForeignKey('users.id'), nullable=True)
    review_notes = Column(Text, nullable=True)

    # Связи
    teacher = relationship('User', foreign_keys=[teacher_id])
    reviewer = relationship('User', foreign_keys=[reviewed_by])


# Таблица паролей для сброса (если нужно хранить токены сброса)
class PasswordResetToken(Base):
    __tablename__ = 'password_reset_tokens'

    id = Column(String(50), primary_key=True)
    user_id = Column(String(50), ForeignKey('users.id'), nullable=False)
    token_hash = Column(String(255), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    used_at = Column(DateTime, nullable=True)
    is_used = Column(Boolean, default=False)

    # Связи
    user = relationship('User')
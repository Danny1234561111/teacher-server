from fastapi import APIRouter, HTTPException, Depends, status, Query, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session

from services.admin_service import AdminService
from services.auth_service import AuthService
from database.database import get_db
from database.schema import User, Department, Speciality, Profile, StudentApplication, ApplicationStatus

router = APIRouter(tags=["Administration"])
security = HTTPBearer()
auth_service = AuthService()
admin_service = AdminService()


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6)
    full_name: str = Field(..., min_length=2)
    role: str = Field(..., pattern="^(ADMIN|TEACHER)$")  # Исправлено: только ADMIN или TEACHER
    phone: Optional[str] = None


class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    phone: Optional[str]
    role: str
    is_active: bool


class DepartmentCreate(BaseModel):
    code: str
    name: str
    faculty: str


class DepartmentResponse(BaseModel):
    id: int
    code: str
    name: str
    faculty: str


class SpecialityCreate(BaseModel):
    code: str
    name: str
    department_id: int


class SpecialityResponse(BaseModel):
    id: int
    code: str
    name: str
    department_id: int


class ProfileCreate(BaseModel):
    name: str
    speciality_id: int
    code: Optional[str] = None
    budget_places: Optional[int] = None
    paid_places: Optional[int] = None


class ProfileResponse(BaseModel):
    id: int
    name: str
    code: Optional[str]
    speciality_id: int
    budget_places: Optional[int]
    paid_places: Optional[int]


class DeleteResponse(BaseModel):
    message: str


# ===== УНИВЕРСАЛЬНАЯ АУТЕНТИФИКАЦИЯ =====

async def get_current_user_universal(
        request: Request,
        credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
        db: Session = Depends(get_db)
) -> User:
    """Универсальная аутентификация: Bearer (мобилка) или Cookie (веб)"""
    token = None

    # 1. Пробуем Bearer token (мобильное приложение)
    if credentials and credentials.credentials:
        token = credentials.credentials

    # 2. Если нет Bearer, пробуем Cookie (веб-приложение)
    if not token:
        token = request.cookies.get("access_token")

    if not token:
        raise HTTPException(status_code=401, detail="Токен не найден")

    try:
        user_data = auth_service.get_user_by_token(token, db)
        user = db.query(User).filter(User.id == user_data['id']).first()
        if not user:
            raise HTTPException(status_code=404, detail="Пользователь не найден")
        if not user.is_active:
            raise HTTPException(status_code=403, detail="Пользователь неактивен")
        return user
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


async def get_current_admin_universal(
        request: Request,
        credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
        db: Session = Depends(get_db)
) -> User:
    """Универсальная аутентификация с проверкой прав администратора"""
    user = await get_current_user_universal(request, credentials, db)

    role = user.role
    if hasattr(role, 'value'):
        is_admin = role.value == 'ADMIN'
    else:
        is_admin = role == 'ADMIN'

    if not is_admin:
        raise HTTPException(status_code=403, detail="Требуются права администратора")

    return user


# ===== ЭНДПОИНТЫ ДЛЯ ВСЕХ ПОЛЬЗОВАТЕЛЕЙ (TEACHER и ADMIN) =====

@router.get("/departments", response_model=List[DepartmentResponse])
async def get_all_departments(
        request: Request,
        current_user: User = Depends(get_current_user_universal),
        db: Session = Depends(get_db)
):
    """Получение списка всех факультетов (доступно всем авторизованным)"""
    return admin_service.get_all_departments(db)


@router.get("/specialities", response_model=List[SpecialityResponse])
async def get_all_specialities(
        request: Request,
        current_user: User = Depends(get_current_user_universal),
        db: Session = Depends(get_db)
):
    """Получение списка всех специальностей (доступно всем авторизованным)"""
    return admin_service.get_all_specialities(db)


@router.get("/profiles", response_model=List[ProfileResponse])
async def get_all_profiles(
        request: Request,
        current_user: User = Depends(get_current_user_universal),
        db: Session = Depends(get_db)
):
    """Получение списка всех профилей (доступно всем авторизованным)"""
    return admin_service.get_all_profiles(db)


# ===== АДМИН-ЭНДПОИНТЫ (только для ADMIN) =====

@router.get("/users", response_model=List[UserResponse])
async def get_all_users(
        request: Request,
        admin: User = Depends(get_current_admin_universal),
        db: Session = Depends(get_db)
):
    """Получение списка всех пользователей (только ADMIN)"""
    return admin_service.get_all_users(db)


@router.get("/stats")
async def get_system_stats(
        request: Request,
        admin: User = Depends(get_current_admin_universal),
        db: Session = Depends(get_db)
):
    """Получение статистики системы (только ADMIN)"""
    return admin_service.get_system_stats(db)


@router.get("/groups-statistics")
async def get_groups_statistics(
        request: Request,
        admin: User = Depends(get_current_admin_universal),
        db: Session = Depends(get_db)
):
    """Получение статистики по группам (только ADMIN)"""
    groups_config = [
        {
            "name": "Разработка",
            "department_name": "Информатика и вычислительная техника",
            "speciality_name": "Прикладная информатика",
            "profile_name": "Прикладная информатика в разработке"
        },
        {
            "name": "Дизайн",
            "department_name": "Факультет бизнес-коммуникаций и информатики",
            "speciality_name": "Прикладная информатика",
            "profile_name": "Прикладная информатика в дизайне"
        }
    ]

    result = {}

    for group_config in groups_config:
        department = db.query(Department).filter(
            Department.name == group_config["department_name"]
        ).first()

        if not department:
            result[group_config["name"]] = {
                "name": group_config["name"],
                "profile_name": group_config["profile_name"],
                "total_applications": 0,
                "applications_submitted": 0,
                "enrolled": 0,
                "average_score": 0,
                "min_score": 0,
                "max_score": 0,
                "error": f"Направление '{group_config['department_name']}' не найдено"
            }
            continue

        speciality = db.query(Speciality).filter(
            Speciality.name == group_config["speciality_name"],
            Speciality.department_id == department.id
        ).first()

        if not speciality:
            result[group_config["name"]] = {
                "name": group_config["name"],
                "profile_name": group_config["profile_name"],
                "total_applications": 0,
                "applications_submitted": 0,
                "enrolled": 0,
                "average_score": 0,
                "min_score": 0,
                "max_score": 0,
                "error": f"Специальность '{group_config['speciality_name']}' не найдена"
            }
            continue

        profile = db.query(Profile).filter(
            Profile.name == group_config["profile_name"],
            Profile.speciality_id == speciality.id
        ).first()

        query = db.query(StudentApplication).filter(
            StudentApplication.department_id == department.id,
            StudentApplication.speciality_id == speciality.id
        )

        if profile:
            query = query.filter(StudentApplication.profile_id == profile.id)

        applications = query.all()

        total_applications = len(applications)
        applications_submitted = len([
            a for a in applications
            if a.application_status != ApplicationStatus.PENDING or a.total_score
        ])
        enrolled = len([a for a in applications if a.application_status == ApplicationStatus.ACCEPTED])

        scores = [a.total_score for a in applications if a.total_score and a.total_score > 0]
        avg_score = sum(scores) / len(scores) if scores else 0
        min_score = min(scores) if scores else 0
        max_score = max(scores) if scores else 0

        result[group_config["name"]] = {
            "name": group_config["name"],
            "profile_name": group_config["profile_name"],
            "department_name": department.name,
            "speciality_name": speciality.name,
            "profile_id": profile.id if profile else None,
            "total_applications": total_applications,
            "applications_submitted": applications_submitted,
            "enrolled": enrolled,
            "average_score": round(avg_score, 2),
            "min_score": min_score,
            "max_score": max_score,
            "unique_students_count": len(set(a.student_id for a in applications))
        }

    return result


@router.post("/users", status_code=201, response_model=UserResponse)
async def create_user(
        request: Request,
        data: UserCreate,
        admin: User = Depends(get_current_admin_universal),
        db: Session = Depends(get_db)
):
    """Создание нового пользователя (только ADMIN)"""
    try:
        return admin_service.create_user(data.dict(), db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/departments", status_code=201, response_model=DepartmentResponse)
async def create_department(
        request: Request,
        data: DepartmentCreate,
        admin: User = Depends(get_current_admin_universal),
        db: Session = Depends(get_db)
):
    """Создание нового факультета (только ADMIN)"""
    return admin_service.create_department(data.dict(), db)


@router.post("/specialities", status_code=201, response_model=SpecialityResponse)
async def create_speciality(
        request: Request,
        data: SpecialityCreate,
        admin: User = Depends(get_current_admin_universal),
        db: Session = Depends(get_db)
):
    """Создание новой специальности (только ADMIN)"""
    return admin_service.create_speciality(data.dict(), db)


@router.post("/profiles", status_code=201, response_model=ProfileResponse)
async def create_profile(
        request: Request,
        data: ProfileCreate,
        admin: User = Depends(get_current_admin_universal),
        db: Session = Depends(get_db)
):
    """Создание нового профиля (только ADMIN)"""
    return admin_service.create_profile(data.dict(), db)


@router.delete("/users/{user_id}", response_model=DeleteResponse)
async def delete_user(
        request: Request,
        user_id: int,
        admin: User = Depends(get_current_admin_universal),
        db: Session = Depends(get_db)
):
    """Удаление пользователя (только ADMIN)"""
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="Нельзя удалить самого себя")

    deleted = admin_service.delete_user(user_id, db)
    if not deleted:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    return {"message": "Пользователь удален"}


@router.delete("/departments/{dept_id}", response_model=DeleteResponse)
async def delete_department(
        request: Request,
        dept_id: int,
        admin: User = Depends(get_current_admin_universal),
        db: Session = Depends(get_db)
):
    """Удаление факультета (только ADMIN)"""
    deleted = admin_service.delete_department(dept_id, db)
    if not deleted:
        raise HTTPException(status_code=404, detail="Факультет не найден")

    return {"message": "Факультет удален"}


@router.delete("/specialities/{spec_id}", response_model=DeleteResponse)
async def delete_speciality(
        request: Request,
        spec_id: int,
        admin: User = Depends(get_current_admin_universal),
        db: Session = Depends(get_db)
):
    """Удаление специальности (только ADMIN)"""
    deleted = admin_service.delete_speciality(spec_id, db)
    if not deleted:
        raise HTTPException(status_code=404, detail="Специальность не найдена")

    return {"message": "Специальность удалена"}


@router.delete("/profiles/{profile_id}", response_model=DeleteResponse)
async def delete_profile(
        request: Request,
        profile_id: int,
        admin: User = Depends(get_current_admin_universal),
        db: Session = Depends(get_db)
):
    """Удаление профиля (только ADMIN)"""
    deleted = admin_service.delete_profile(profile_id, db)
    if not deleted:
        raise HTTPException(status_code=404, detail="Профиль не найден")

    return {"message": "Профиль удален"}
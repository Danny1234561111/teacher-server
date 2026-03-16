# api/routes/admin.py
from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from sqlalchemy.orm import Session

from services.admin_service import AdminService
from services.auth_service import AuthService
from database.database import get_db
from database.schema import User

router = APIRouter(tags=["Administration"])
security = HTTPBearer()
auth_service = AuthService()
admin_service = AdminService()


# ===== МОДЕЛИ =====

class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6)
    full_name: str = Field(..., min_length=2)
    role: str = Field(..., pattern="^(admin|teacher|student)$")
    phone: Optional[str] = None
    # УБРАНО: max_students: Optional[int] = 20


class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    phone: Optional[str]
    role: str
    is_active: bool
    # УБРАНО: max_students: Optional[int]


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


# ===== ПРОВЕРКА АДМИНА =====

async def get_current_admin(
        credentials: HTTPAuthorizationCredentials = Depends(security),
        db: Session = Depends(get_db)
) -> User:
    token = credentials.credentials
    user_data = auth_service.get_user_by_token(token, db)

    # Безопасное получение роли
    role = user_data.get('role')

    # Проверяем разные случаи
    is_admin = False
    if hasattr(role, 'value'):  # если это Enum
        is_admin = role.value == 'admin'
    else:  # если это строка
        is_admin = role == 'admin'

    if not is_admin:
        print(f"Доступ запрещен. Роль пользователя: {role}")
        raise HTTPException(status_code=403, detail="Требуются права администратора")

    user = db.query(User).filter(User.id == user_data['id']).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    return user


# ===== ПОЛУЧЕНИЕ СПИСКОВ (ТОЛЬКО ВСЕ) =====

@router.get("/users", response_model=List[UserResponse])
async def get_all_users(
        admin: User = Depends(get_current_admin),
        db: Session = Depends(get_db)
):
    """Получение списка всех пользователей"""
    return admin_service.get_all_users(db)


@router.get("/departments", response_model=List[DepartmentResponse])
async def get_all_departments(
        admin: User = Depends(get_current_admin),
        db: Session = Depends(get_db)
):
    """Получение списка всех факультетов"""
    return admin_service.get_all_departments(db)


@router.get("/specialities", response_model=List[SpecialityResponse])
async def get_all_specialities(
        admin: User = Depends(get_current_admin),
        db: Session = Depends(get_db)
):
    """Получение списка всех специальностей"""
    return admin_service.get_all_specialities(db)


@router.get("/profiles", response_model=List[ProfileResponse])
async def get_all_profiles(
        admin: User = Depends(get_current_admin),
        db: Session = Depends(get_db)
):
    """Получение списка всех профилей"""
    return admin_service.get_all_profiles(db)


@router.get("/stats")
async def get_system_stats(
        admin: User = Depends(get_current_admin),
        db: Session = Depends(get_db)
):
    """Получение статистики системы"""
    return admin_service.get_system_stats(db)


# ===== ДОБАВЛЕНИЕ =====

@router.post("/users", status_code=201, response_model=UserResponse)
async def create_user(
        data: UserCreate,
        admin: User = Depends(get_current_admin),
        db: Session = Depends(get_db)
):
    """Добавление пользователя"""
    try:
        return admin_service.create_user(data.dict(), db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/departments", status_code=201, response_model=DepartmentResponse)
async def create_department(
        data: DepartmentCreate,
        admin: User = Depends(get_current_admin),
        db: Session = Depends(get_db)
):
    """Добавление факультета"""
    return admin_service.create_department(data.dict(), db)


@router.post("/specialities", status_code=201, response_model=SpecialityResponse)
async def create_speciality(
        data: SpecialityCreate,
        admin: User = Depends(get_current_admin),
        db: Session = Depends(get_db)
):
    """Добавление специальности"""
    return admin_service.create_speciality(data.dict(), db)


@router.post("/profiles", status_code=201, response_model=ProfileResponse)
async def create_profile(
        data: ProfileCreate,
        admin: User = Depends(get_current_admin),
        db: Session = Depends(get_db)
):
    """Добавление профиля"""
    return admin_service.create_profile(data.dict(), db)


# ===== УДАЛЕНИЕ =====

@router.delete("/users/{user_id}", response_model=DeleteResponse)
async def delete_user(
        user_id: int,
        admin: User = Depends(get_current_admin),
        db: Session = Depends(get_db)
):
    """Удаление пользователя"""
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="Нельзя удалить самого себя")

    deleted = admin_service.delete_user(user_id, db)
    if not deleted:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    return {"message": "Пользователь удален"}


@router.delete("/departments/{dept_id}", response_model=DeleteResponse)
async def delete_department(
        dept_id: int,
        admin: User = Depends(get_current_admin),
        db: Session = Depends(get_db)
):
    """Удаление факультета"""
    deleted = admin_service.delete_department(dept_id, db)
    if not deleted:
        raise HTTPException(status_code=404, detail="Факультет не найден")

    return {"message": "Факультет удален"}


@router.delete("/specialities/{spec_id}", response_model=DeleteResponse)
async def delete_speciality(
        spec_id: int,
        admin: User = Depends(get_current_admin),
        db: Session = Depends(get_db)
):
    """Удаление специальности"""
    deleted = admin_service.delete_speciality(spec_id, db)
    if not deleted:
        raise HTTPException(status_code=404, detail="Специальность не найдена")

    return {"message": "Специальность удалена"}


@router.delete("/profiles/{profile_id}", response_model=DeleteResponse)
async def delete_profile(
        profile_id: int,
        admin: User = Depends(get_current_admin),
        db: Session = Depends(get_db)
):
    """Удаление профиля"""
    deleted = admin_service.delete_profile(profile_id, db)
    if not deleted:
        raise HTTPException(status_code=404, detail="Профиль не найден")

    return {"message": "Профиль удален"}
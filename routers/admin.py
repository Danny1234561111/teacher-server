# api/routes/admin.py
from fastapi import APIRouter, HTTPException, Depends, status, Request
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
    role: str = Field(..., pattern="^(admin|teacher|student)$")
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


async def get_current_admin_mobile(
        credentials: HTTPAuthorizationCredentials = Depends(security),
        db: Session = Depends(get_db)
) -> User:
    token = credentials.credentials
    user_data = auth_service.get_user_by_token(token, db)

    role = user_data.get('role')
    is_admin = False
    if hasattr(role, 'value'):
        is_admin = role.value == 'admin'
    else:
        is_admin = role == 'admin'

    if not is_admin:
        print(f"Доступ запрещен. Роль пользователя: {role}")
        raise HTTPException(status_code=403, detail="Требуются права администратора")

    user = db.query(User).filter(User.id == user_data['id']).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    return user


async def get_current_admin_web(
        request: Request,
        db: Session = Depends(get_db)
) -> User:
    user_data = auth_service.get_current_user_web(request, db)

    role = user_data.get('role')
    is_admin = False
    if hasattr(role, 'value'):
        is_admin = role.value == 'admin'
    else:
        is_admin = role == 'admin'

    if not is_admin:
        print(f"Доступ запрещен. Роль пользователя: {role}")
        raise HTTPException(status_code=403, detail="Требуются права администратора")

    user = db.query(User).filter(User.id == user_data['id']).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    return user


async def get_current_teacher_mobile(
        credentials: HTTPAuthorizationCredentials = Depends(security),
        db: Session = Depends(get_db)
) -> User:
    token = credentials.credentials
    user_data = auth_service.get_user_by_token(token, db)
    user = db.query(User).filter(User.id == user_data['id']).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return user


async def get_current_teacher_web(
        request: Request,
        db: Session = Depends(get_db)
) -> User:
    user_data = auth_service.get_current_user_web(request, db)
    user = db.query(User).filter(User.id == user_data['id']).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return user


# ==================== МОБИЛЬНЫЕ ЭНДПОИНТЫ ====================

@router.get("/mobile/departments", response_model=List[DepartmentResponse])
async def mobile_get_all_departments(
        current_user: User = Depends(get_current_teacher_mobile),
        db: Session = Depends(get_db)
):
    return admin_service.get_all_departments(db)


@router.get("/mobile/specialities", response_model=List[SpecialityResponse])
async def mobile_get_all_specialities(
        current_user: User = Depends(get_current_teacher_mobile),
        db: Session = Depends(get_db)
):
    return admin_service.get_all_specialities(db)


@router.get("/mobile/profiles", response_model=List[ProfileResponse])
async def mobile_get_all_profiles(
        current_user: User = Depends(get_current_teacher_mobile),
        db: Session = Depends(get_db)
):
    return admin_service.get_all_profiles(db)


@router.get("/mobile/users", response_model=List[UserResponse])
async def mobile_get_all_users(
        admin: User = Depends(get_current_admin_mobile),
        db: Session = Depends(get_db)
):
    return admin_service.get_all_users(db)


@router.get("/mobile/stats")
async def mobile_get_system_stats(
        admin: User = Depends(get_current_admin_mobile),
        db: Session = Depends(get_db)
):
    return admin_service.get_system_stats(db)


@router.post("/mobile/users", status_code=201, response_model=UserResponse)
async def mobile_create_user(
        data: UserCreate,
        admin: User = Depends(get_current_admin_mobile),
        db: Session = Depends(get_db)
):
    try:
        return admin_service.create_user(data.dict(), db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/mobile/departments", status_code=201, response_model=DepartmentResponse)
async def mobile_create_department(
        data: DepartmentCreate,
        admin: User = Depends(get_current_admin_mobile),
        db: Session = Depends(get_db)
):
    return admin_service.create_department(data.dict(), db)


@router.post("/mobile/specialities", status_code=201, response_model=SpecialityResponse)
async def mobile_create_speciality(
        data: SpecialityCreate,
        admin: User = Depends(get_current_admin_mobile),
        db: Session = Depends(get_db)
):
    return admin_service.create_speciality(data.dict(), db)


@router.post("/mobile/profiles", status_code=201, response_model=ProfileResponse)
async def mobile_create_profile(
        data: ProfileCreate,
        admin: User = Depends(get_current_admin_mobile),
        db: Session = Depends(get_db)
):
    return admin_service.create_profile(data.dict(), db)


@router.delete("/mobile/users/{user_id}", response_model=DeleteResponse)
async def mobile_delete_user(
        user_id: int,
        admin: User = Depends(get_current_admin_mobile),
        db: Session = Depends(get_db)
):
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="Нельзя удалить самого себя")

    deleted = admin_service.delete_user(user_id, db)
    if not deleted:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    return {"message": "Пользователь удален"}


@router.delete("/mobile/departments/{dept_id}", response_model=DeleteResponse)
async def mobile_delete_department(
        dept_id: int,
        admin: User = Depends(get_current_admin_mobile),
        db: Session = Depends(get_db)
):
    deleted = admin_service.delete_department(dept_id, db)
    if not deleted:
        raise HTTPException(status_code=404, detail="Факультет не найден")

    return {"message": "Факультет удален"}


@router.delete("/mobile/specialities/{spec_id}", response_model=DeleteResponse)
async def mobile_delete_speciality(
        spec_id: int,
        admin: User = Depends(get_current_admin_mobile),
        db: Session = Depends(get_db)
):
    deleted = admin_service.delete_speciality(spec_id, db)
    if not deleted:
        raise HTTPException(status_code=404, detail="Специальность не найдена")

    return {"message": "Специальность удалена"}


@router.delete("/mobile/profiles/{profile_id}", response_model=DeleteResponse)
async def mobile_delete_profile(
        profile_id: int,
        admin: User = Depends(get_current_admin_mobile),
        db: Session = Depends(get_db)
):
    deleted = admin_service.delete_profile(profile_id, db)
    if not deleted:
        raise HTTPException(status_code=404, detail="Профиль не найден")

    return {"message": "Профиль удален"}


# ==================== ВЕБ-ЭНДПОИНТЫ ====================

@router.get("/web/departments", response_model=List[DepartmentResponse])
async def web_get_all_departments(
        request: Request,
        db: Session = Depends(get_db)
):
    current_user = await get_current_teacher_web(request, db)
    return admin_service.get_all_departments(db)


@router.get("/web/specialities", response_model=List[SpecialityResponse])
async def web_get_all_specialities(
        request: Request,
        db: Session = Depends(get_db)
):
    current_user = await get_current_teacher_web(request, db)
    return admin_service.get_all_specialities(db)


@router.get("/web/profiles", response_model=List[ProfileResponse])
async def web_get_all_profiles(
        request: Request,
        db: Session = Depends(get_db)
):
    current_user = await get_current_teacher_web(request, db)
    return admin_service.get_all_profiles(db)


@router.get("/web/users", response_model=List[UserResponse])
async def web_get_all_users(
        request: Request,
        db: Session = Depends(get_db)
):
    admin = await get_current_admin_web(request, db)
    return admin_service.get_all_users(db)


@router.get("/web/stats")
async def web_get_system_stats(
        request: Request,
        db: Session = Depends(get_db)
):
    admin = await get_current_admin_web(request, db)
    return admin_service.get_system_stats(db)


@router.get("/web/groups-statistics")
async def web_get_groups_statistics(
        request: Request,
        db: Session = Depends(get_db)
):
    admin = await get_current_admin_web(request, db)

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


@router.post("/web/users", status_code=201, response_model=UserResponse)
async def web_create_user(
        request: Request,
        data: UserCreate,
        db: Session = Depends(get_db)
):
    admin = await get_current_admin_web(request, db)
    try:
        return admin_service.create_user(data.dict(), db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/web/departments", status_code=201, response_model=DepartmentResponse)
async def web_create_department(
        request: Request,
        data: DepartmentCreate,
        db: Session = Depends(get_db)
):
    admin = await get_current_admin_web(request, db)
    return admin_service.create_department(data.dict(), db)


@router.post("/web/specialities", status_code=201, response_model=SpecialityResponse)
async def web_create_speciality(
        request: Request,
        data: SpecialityCreate,
        db: Session = Depends(get_db)
):
    admin = await get_current_admin_web(request, db)
    return admin_service.create_speciality(data.dict(), db)


@router.post("/web/profiles", status_code=201, response_model=ProfileResponse)
async def web_create_profile(
        request: Request,
        data: ProfileCreate,
        db: Session = Depends(get_db)
):
    admin = await get_current_admin_web(request, db)
    return admin_service.create_profile(data.dict(), db)


@router.delete("/web/users/{user_id}", response_model=DeleteResponse)
async def web_delete_user(
        request: Request,
        user_id: int,
        db: Session = Depends(get_db)
):
    admin = await get_current_admin_web(request, db)
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="Нельзя удалить самого себя")

    deleted = admin_service.delete_user(user_id, db)
    if not deleted:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    return {"message": "Пользователь удален"}


@router.delete("/web/departments/{dept_id}", response_model=DeleteResponse)
async def web_delete_department(
        request: Request,
        dept_id: int,
        db: Session = Depends(get_db)
):
    admin = await get_current_admin_web(request, db)
    deleted = admin_service.delete_department(dept_id, db)
    if not deleted:
        raise HTTPException(status_code=404, detail="Факультет не найден")

    return {"message": "Факультет удален"}


@router.delete("/web/specialities/{spec_id}", response_model=DeleteResponse)
async def web_delete_speciality(
        request: Request,
        spec_id: int,
        db: Session = Depends(get_db)
):
    admin = await get_current_admin_web(request, db)
    deleted = admin_service.delete_speciality(spec_id, db)
    if not deleted:
        raise HTTPException(status_code=404, detail="Специальность не найдена")

    return {"message": "Специальность удалена"}


@router.delete("/web/profiles/{profile_id}", response_model=DeleteResponse)
async def web_delete_profile(
        request: Request,
        profile_id: int,
        db: Session = Depends(get_db)
):
    admin = await get_current_admin_web(request, db)
    deleted = admin_service.delete_profile(profile_id, db)
    if not deleted:
        raise HTTPException(status_code=404, detail="Профиль не найден")

    return {"message": "Профиль удален"}
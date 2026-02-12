from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import List, Optional
from sqlalchemy.orm import Session

from services.auth_service import AuthService
from services.database_service import DatabaseService
from database.database import get_db

router = APIRouter()
auth_service = AuthService()
database_service = DatabaseService()
security = HTTPBearer()


def get_admin_user(credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    """Зависимость для получения администратора"""
    token = credentials.credentials
    try:
        user = auth_service.get_current_user(token, db)
        if user.get('role') != 'admin':
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Требуются права администратора"
            )
        return user
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )


@router.get("/teacher-requests")
async def get_teacher_requests(
        status: Optional[str] = None,
        admin_user: dict = Depends(get_admin_user),
        db: Session = Depends(get_db)
):
    """Получение списка заявок преподавателей"""
    try:
        requests = auth_service.get_teacher_requests(status, db)
        return {"requests": requests, "count": len(requests)}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка получения заявок: {str(e)}"
        )


@router.post("/approve-teacher/{request_id}")
async def approve_teacher_request(
        request_id: str,
        departments: Optional[List[str]] = None,
        admin_user: dict = Depends(get_admin_user),
        db: Session = Depends(get_db)
):
    """Одобрение заявки преподавателя"""
    try:
        result = auth_service.approve_teacher_request(
            request_id=request_id,
            admin_id=admin_user['id'],
            departments=departments,
            db=db
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка одобрения заявки: {str(e)}"
        )


@router.post("/reject-teacher/{request_id}")
async def reject_teacher_request(
        request_id: str,
        reason: str = "",
        admin_user: dict = Depends(get_admin_user),
        db: Session = Depends(get_db)
):
    """Отклонение заявки преподавателя"""
    try:
        result = auth_service.reject_teacher_request(
            request_id=request_id,
            admin_id=admin_user['id'],
            reason=reason,
            db=db
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка отклонения заявки: {str(e)}"
        )


@router.get("/users")
async def get_all_users(
        role: Optional[str] = None,
        active_only: bool = True,
        limit: int = 100,
        offset: int = 0,
        admin_user: dict = Depends(get_admin_user),
        db: Session = Depends(get_db)
):
    """Получение списка всех пользователей"""
    try:
        users = database_service.get_all_users(limit=limit, offset=offset)

        if role:
            users = [user for user in users if user.get('role') == role]
        if active_only:
            users = [user for user in users if user.get('is_active')]

        return {"users": users, "count": len(users)}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка получения пользователей: {str(e)}"
        )


@router.put("/users/{user_id}/activate")
async def activate_user(
        user_id: str,
        admin_user: dict = Depends(get_admin_user),
        db: Session = Depends(get_db)
):
    """Активация пользователя"""
    try:
        success = database_service.update_user(user_id, {"is_active": True})
        if not success:
            raise HTTPException(status_code=404, detail="Пользователь не найден")

        return {"message": "Пользователь активирован"}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка активации пользователя: {str(e)}"
        )


@router.put("/users/{user_id}/deactivate")
async def deactivate_user(
        user_id: str,
        admin_user: dict = Depends(get_admin_user),
        db: Session = Depends(get_db)
):
    """Деактивация пользователя"""
    try:
        success = database_service.update_user(user_id, {"is_active": False})
        if not success:
            raise HTTPException(status_code=404, detail="Пользователь не найден")

        return {"message": "Пользователь деактивирован"}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка деактивации пользователя: {str(e)}"
        )


@router.get("/statistics")
async def get_admin_statistics(
        admin_user: dict = Depends(get_admin_user),
        db: Session = Depends(get_db)
):
    """Получение статистики системы"""
    try:
        stats = database_service.get_statistics()
        return stats
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка получения статистики: {str(e)}"
        )


@router.get("/students")
async def get_all_students(
        department_id: Optional[str] = None,
        speciality_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        admin_user: dict = Depends(get_admin_user),
        db: Session = Depends(get_db)
):
    """Получение всех студентов (админ)"""
    try:
        students = database_service.get_all_students_filtered(
            department_id=department_id,
            speciality_id=speciality_id,
            status=status,
            limit=limit,
            offset=offset
        )
        return {"students": students, "count": len(students)}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка получения студентов: {str(e)}"
        )
from fastapi import APIRouter, Depends, HTTPException, Query, Body, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import List, Optional
from datetime import datetime, timedelta

from schemas import (
    StudentCreate, StudentResponse, StudentFilter,
    CommunicationCreate, CommunicationResponse, CommunicationUpdate,
    CommunicationStats, StudentWithCommunications, StudentUpdateRequest
)
from services.database_service import DatabaseService
from services.auth_service import AuthService
# TODO: Создать communication_service для PostgreSQL
# from services.communication_service_sql import CommunicationService
import os
import traceback

router = APIRouter()
database_service = DatabaseService()
auth_service = AuthService()
# TODO: Инициализируйте когда создадите
# communication_service = CommunicationService()
security = HTTPBearer()


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Получение текущего пользователя из JWT токена"""
    token = credentials.credentials
    print(f"🔐 Получен токен для проверки: {token[:50]}...")

    try:
        # Нужно получить сессию БД
        from database.database import get_db
        db_gen = get_db()
        db = next(db_gen)

        user = auth_service.get_current_user(token, db)
        print(f"✅ Токен валиден, пользователь: {user.get('email')}")

        # Закрываем сессию
        try:
            next(db_gen)
        except StopIteration:
            pass

        return user

    except ValueError as e:
        print(f"❌ Ошибка проверки токена: {e}")
        raise HTTPException(
            status_code=401,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"}
        )
    except Exception as e:
        print(f"❌ Неизвестная ошибка при проверки токена: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=401,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"}
        )


# ========== CRUD студентов ==========

@router.get("/my-students", response_model=List[StudentResponse])
async def get_my_students(
        current_user: dict = Depends(get_current_user)
):
    """Получение студентов доступных текущему преподавателю"""
    print(f"📋 Запрос студентов для пользователя: {current_user.get('email')}")

    if current_user.get('role') != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can access students")

    try:
        # Получаем доступные направления и специальности преподавателя
        teacher_departments = current_user.get('assigned_departments', [])
        teacher_specialities = current_user.get('assigned_specialities', [])

        # Если преподаватель имеет доступ ко всему ('all')
        if 'all' in teacher_departments and 'all' in teacher_specialities:
            # Видит всех студентов
            students = database_service.get_all_students_filtered(limit=100)
        else:
            # Видит студентов только по своим направлениям/специальностям
            students = database_service.get_students_by_departments(
                department_ids=teacher_departments if 'all' not in teacher_departments else None,
                speciality_ids=teacher_specialities if 'all' not in teacher_specialities else None,
                limit=100
            )

        print(f"✅ Найдено студентов: {len(students)}")
        return [StudentResponse(**student) for student in students]
    except Exception as e:
        print(f"❌ Ошибка получения студентов: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/", response_model=List[StudentResponse])
async def get_students(
        department_id: Optional[str] = Query(None),
        speciality_id: Optional[str] = Query(None),
        status: Optional[str] = Query(None),
        search: Optional[str] = Query(None),
        skip: int = Query(0, ge=0),
        limit: int = Query(20, ge=1, le=100),
        current_user: dict = Depends(get_current_user)
):
    """Получение студентов с фильтрами"""
    print(f"🔍 Запрос студентов, пользователь: {current_user.get('email')}")

    try:
        # Админ видит всех студентов
        if current_user.get('role') == "admin":
            if search:
                students = database_service.search_students(
                    search_term=search,
                    limit=limit
                )[skip:skip + limit]
            else:
                students = database_service.get_all_students_filtered(
                    department_id=department_id,
                    speciality_id=speciality_id,
                    status=status,
                    limit=limit,
                    offset=skip
                )

        # Преподаватель видит студентов по своим направлениям/специальностям
        elif current_user.get('role') == "teacher":
            # Получаем доступные направления и специальности преподавателя
            teacher_departments = current_user.get('assigned_departments', [])
            teacher_specialities = current_user.get('assigned_specialities', [])

            # Если преподаватель имеет доступ ко всему ('all')
            if 'all' in teacher_departments and 'all' in teacher_specialities:
                # Видит всех студентов
                students = database_service.get_all_students_filtered(
                    department_id=department_id,
                    speciality_id=speciality_id,
                    status=status,
                    limit=limit,
                    offset=skip
                )
            else:
                # Видит студентов только по своим направлениям/специальностям
                students = database_service.get_students_by_departments(
                    department_ids=teacher_departments if 'all' not in teacher_departments else None,
                    speciality_ids=teacher_specialities if 'all' not in teacher_specialities else None,
                    limit=limit,
                    offset=skip
                )

        else:
            raise HTTPException(status_code=403, detail="Access denied")

        print(f"✅ Возвращаю студентов: {len(students)}")
        return [StudentResponse(**student) for student in students]

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Ошибка при получении студентов: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{student_id}", response_model=StudentResponse)
async def get_student_by_id(
        student_id: str,
        current_user: dict = Depends(get_current_user)
):
    """Получение конкретного студента по ID"""
    print(f"👤 Запрос студента {student_id}, пользователь: {current_user.get('email')}")

    try:
        student = database_service.get_student_by_id(student_id)
        if not student:
            raise HTTPException(status_code=404, detail="Student not found")

        # Проверка прав доступа для преподавателя
        if current_user.get('role') == "teacher":
            teacher_departments = current_user.get('assigned_departments', [])
            teacher_specialities = current_user.get('assigned_specialities', [])

            student_department = student.get('department_id')
            student_speciality = student.get('speciality_id')

            # Проверяем доступ к направлению
            if student_department and 'all' not in teacher_departments:
                if student_department not in teacher_departments:
                    raise HTTPException(status_code=403, detail="Нет доступа к этому направлению")

            # Проверяем доступ к специальности
            if student_speciality and 'all' not in teacher_specialities:
                if student_speciality not in teacher_specialities:
                    raise HTTPException(status_code=403, detail="Нет доступа к этой специальности")

        return StudentResponse(**student)

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Ошибка получения студента: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/", response_model=StudentResponse)
async def create_student(
        student_data: StudentCreate,
        current_user: dict = Depends(get_current_user)
):
    """Создание нового студента"""
    print(f"➕ Создание студента, пользователь: {current_user.get('email')}")

    if current_user.get('role') not in ["admin", "teacher"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    try:
        student_dict = student_data.dict()

        # Проверяем, что преподаватель имеет доступ к направлению
        if current_user.get('role') == "teacher":
            teacher_departments = current_user.get('assigned_departments', [])
            teacher_specialities = current_user.get('assigned_specialities', [])

            student_department = student_dict.get('department_id')
            student_speciality = student_dict.get('speciality_id')

            # Проверяем доступ к направлению
            if student_department and 'all' not in teacher_departments:
                if student_department not in teacher_departments:
                    raise HTTPException(
                        status_code=403,
                        detail="У вас нет доступа к этому направлению"
                    )

            # Проверяем доступ к специальности
            if student_speciality and 'all' not in teacher_specialities:
                if student_speciality not in teacher_specialities:
                    raise HTTPException(
                        status_code=403,
                        detail="У вас нет доступа к этой специальности"
                    )

            # Присваиваем студента текущему преподавателю
            student_dict['assigned_teacher_id'] = current_user.get('id')

            # Устанавливаем priority_place = 1 если не указан
            if student_dict.get('priority_place') is None:
                student_dict['priority_place'] = 1

        # Для всех: если priority_place не указан, ставим 1
        if student_dict.get('priority_place') is None:
            student_dict['priority_place'] = 1

        # Если это админ и не указан преподаватель, оставляем пустым
        if current_user.get('role') == "admin" and 'assigned_teacher_id' not in student_dict:
            student_dict['assigned_teacher_id'] = None

        student_id = database_service.create_student(student_dict)
        print(f"✅ Студент создан с ID: {student_id}")

        student = database_service.get_student_by_id(student_id)
        if not student:
            raise HTTPException(status_code=500, detail="Failed to create student")

        return StudentResponse(**student)

    except ValueError as e:
        print(f"❌ Ошибка валидации: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Ошибка создания студента: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{student_id}", response_model=StudentResponse)
async def update_student(
        student_id: str,
        student_data: StudentUpdateRequest,
        current_user: dict = Depends(get_current_user)
):
    """Обновление данных студента"""
    print(f"✏️ Обновление студента {student_id}, пользователь: {current_user.get('email')}")

    try:
        # Проверяем существование студента
        existing_student = database_service.get_student_by_id(student_id)
        if not existing_student:
            raise HTTPException(status_code=404, detail="Student not found")

        # Проверка прав доступа для преподавателя
        if current_user.get('role') == "teacher":
            teacher_departments = current_user.get('assigned_departments', [])
            teacher_specialities = current_user.get('assigned_specialities', [])

            # Проверяем текущие доступы
            existing_department = existing_student.get('department_id')
            existing_speciality = existing_student.get('speciality_id')

            if existing_department and 'all' not in teacher_departments:
                if existing_department not in teacher_departments:
                    raise HTTPException(status_code=403, detail="Нет доступа к текущему направлению студента")

            if existing_speciality and 'all' not in teacher_specialities:
                if existing_speciality not in teacher_specialities:
                    raise HTTPException(status_code=403, detail="Нет доступа к текущей специальности студента")

            # Проверяем новые значения если они указаны
            student_dict = student_data.dict(exclude_unset=True)
            new_department = student_dict.get('department_id')
            new_speciality = student_dict.get('speciality_id')

            if new_department and 'all' not in teacher_departments:
                if new_department not in teacher_departments:
                    raise HTTPException(status_code=403, detail="Нет доступа к новому направлению")

            if new_speciality and 'all' not in teacher_specialities:
                if new_speciality not in teacher_specialities:
                    raise HTTPException(status_code=403, detail="Нет доступа к новой специальности")

            # Преподаватель может назначить студента только себе
            if 'assigned_teacher_id' in student_dict:
                if student_dict['assigned_teacher_id'] != current_user.get('id'):
                    raise HTTPException(status_code=403, detail="Можно назначить студента только себе")

        student_dict = student_data.dict(exclude_unset=True)

        success = database_service.update_student(student_id, student_dict)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to update student")

        updated_student = database_service.get_student_by_id(student_id)
        print(f"✅ Студент обновлен: {student_id}")
        return StudentResponse(**updated_student)

    except ValueError as e:
        print(f"❌ Ошибка валидации: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Ошибка обновления студента: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{student_id}")
async def delete_student(
        student_id: str,
        current_user: dict = Depends(get_current_user)
):
    """Удаление студента"""
    print(f"🗑️ Удаление студента {student_id}, пользователь: {current_user.get('email')}")

    try:
        # Проверяем существование студента
        student = database_service.get_student_by_id(student_id)
        if not student:
            raise HTTPException(status_code=404, detail="Student not found")

        # Проверка прав доступа для преподавателя
        if current_user.get('role') == "teacher":
            teacher_departments = current_user.get('assigned_departments', [])
            teacher_specialities = current_user.get('assigned_specialities', [])

            student_department = student.get('department_id')
            student_speciality = student.get('speciality_id')

            if student_department and 'all' not in teacher_departments:
                if student_department not in teacher_departments:
                    raise HTTPException(status_code=403, detail="Нет доступа к этому студенту")

            if student_speciality and 'all' not in teacher_specialities:
                if student_speciality not in teacher_specialities:
                    raise HTTPException(status_code=403, detail="Нет доступа к этому студенту")

        success = database_service.delete_student(student_id)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete student")

        print(f"✅ Студент удален: {student_id}")
        return {"message": "Student deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Ошибка удаления студента: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


# ========== История коммуникаций ==========

@router.post("/{student_id}/communications", response_model=CommunicationResponse)
async def create_communication(
        student_id: str,
        communication_data: CommunicationCreate,
        current_user: dict = Depends(get_current_user)
):
    """Создание записи о коммуникации со студентом"""
    print(f"💬 Создание коммуникации для студента {student_id}, пользователь: {current_user.get('email')}")

    try:
        # Проверяем, что студент существует
        student = database_service.get_student_by_id(student_id)
        if not student:
            raise HTTPException(status_code=404, detail="Student not found")

        # Проверяем права доступа для преподавателя
        if current_user.get('role') == "teacher":
            teacher_departments = current_user.get('assigned_departments', [])
            teacher_specialities = current_user.get('assigned_specialities', [])

            student_department = student.get('department_id')
            student_speciality = student.get('speciality_id')

            if student_department and 'all' not in teacher_departments:
                if student_department not in teacher_departments:
                    raise HTTPException(status_code=403, detail="Нет доступа к этому студенту")

            if student_speciality and 'all' not in teacher_specialities:
                if student_speciality not in teacher_specialities:
                    raise HTTPException(status_code=403, detail="Нет доступа к этому студенту")

        # Создаем коммуникацию
        comm_dict = communication_data.dict()
        comm_dict['student_id'] = student_id

        communication_id = database_service.create_communication(
            comm_dict,
            current_user['id']
        )

        # Получаем созданную запись
        communication = database_service.get_communication_by_id(communication_id)
        if not communication:
            raise HTTPException(status_code=500, detail="Failed to create communication")

        # Добавляем информацию о студенте
        communication['student_name'] = student.get('full_name')
        communication['student_phone'] = student.get('phone')

        print(f"✅ Коммуникация создана: {communication_id}")
        return CommunicationResponse(**communication)

    except ValueError as e:
        print(f"❌ Ошибка валидации: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Ошибка создания коммуникации: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{student_id}/communications", response_model=List[CommunicationResponse])
async def get_student_communications(
        student_id: str,
        communication_type: Optional[str] = Query(None),
        status: Optional[str] = Query(None),
        date_from: Optional[datetime] = Query(None),
        date_to: Optional[datetime] = Query(None),
        limit: int = Query(50, ge=1, le=100),
        skip: int = Query(0, ge=0),
        current_user: dict = Depends(get_current_user)
):
    """Получение истории коммуникаций со студентом"""
    print(f"📞 Получение коммуникаций студента {student_id}, пользователь: {current_user.get('email')}")

    try:
        # Проверяем, что студент существует
        student = database_service.get_student_by_id(student_id)
        if not student:
            raise HTTPException(status_code=404, detail="Student not found")

        # Проверяем права доступа для преподавателя
        if current_user.get('role') == "teacher":
            teacher_departments = current_user.get('assigned_departments', [])
            teacher_specialities = current_user.get('assigned_specialities', [])

            student_department = student.get('department_id')
            student_speciality = student.get('speciality_id')

            if student_department and 'all' not in teacher_departments:
                if student_department not in teacher_departments:
                    raise HTTPException(status_code=403, detail="Нет доступа к этому студенту")

            if student_speciality and 'all' not in teacher_specialities:
                if student_speciality not in teacher_specialities:
                    raise HTTPException(status_code=403, detail="Нет доступа к этому студенту")

        # Получаем коммуникации
        communications = database_service.get_communications_by_student(
            student_id=student_id,
            user_id=current_user['id'],
            limit=limit,
            offset=skip
        )

        # TODO: Добавить фильтрацию по дате в database_service
        if date_from or date_to:
            filtered_comms = []
            for comm in communications:
                comm_date = comm.get('date_time')
                if comm_date:
                    if date_from and comm_date < date_from:
                        continue
                    if date_to and comm_date > date_to:
                        continue
                    filtered_comms.append(comm)
            communications = filtered_comms

        # Фильтрация по типу и статусу
        if communication_type:
            communications = [c for c in communications if c.get('communication_type') == communication_type]
        if status:
            communications = [c for c in communications if c.get('status') == status]

        # Добавляем информацию о студенте
        for comm in communications:
            comm['student_name'] = student.get('full_name')
            comm['student_phone'] = student.get('phone')

        print(f"✅ Найдено коммуникаций: {len(communications)}")
        return [CommunicationResponse(**comm) for comm in communications]

    except ValueError as e:
        print(f"❌ Ошибка валидации: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Ошибка получения коммуникаций: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/communications/my", response_model=List[CommunicationResponse])
async def get_my_communications(
        communication_type: Optional[str] = Query(None),
        status: Optional[str] = Query(None),
        important_only: bool = Query(False),
        limit: int = Query(50, ge=1, le=100),
        skip: int = Query(0, ge=0),
        current_user: dict = Depends(get_current_user)
):
    """Получение всех коммуникаций текущего преподавателя"""
    print(f"📋 Получение моих коммуникаций, пользователь: {current_user.get('email')}")

    if current_user.get('role') != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can access communications")

    try:
        communications = database_service.get_communications_by_teacher(
            teacher_id=current_user['id'],
            limit=limit,
            offset=skip
        )

        # Фильтрация
        if communication_type:
            communications = [c for c in communications if c.get('communication_type') == communication_type]
        if status:
            communications = [c for c in communications if c.get('status') == status]
        if important_only:
            communications = [c for c in communications if c.get('is_important')]

        print(f"✅ Найдено коммуникаций: {len(communications)}")
        return [CommunicationResponse(**comm) for comm in communications]

    except Exception as e:
        print(f"❌ Ошибка получения коммуникаций: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/communications/stats", response_model=CommunicationStats)
async def get_communication_stats(
        days_back: int = Query(30, ge=1, le=365),
        current_user: dict = Depends(get_current_user)
):
    """Получение статистики по коммуникациям"""
    print(f"📊 Получение статистики коммуникаций, пользователь: {current_user.get('email')}")

    if current_user.get('role') != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can access stats")

    try:
        stats = database_service.get_communication_stats(
            teacher_id=current_user['id'],
            days_back=days_back
        )

        print(f"✅ Статистика получена")
        return CommunicationStats(**stats)

    except Exception as e:
        print(f"❌ Ошибка получения статистики: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/communications/{communication_id}", response_model=CommunicationResponse)
async def update_communication(
        communication_id: str,
        update_data: CommunicationUpdate,
        current_user: dict = Depends(get_current_user)
):
    """Обновление записи о коммуникации"""
    print(f"✏️ Обновление коммуникации {communication_id}, пользователь: {current_user.get('email')}")

    try:
        success = database_service.update_communication(
            communication_id=communication_id,
            update_data=update_data.dict(exclude_unset=True),
            user_id=current_user['id']
        )

        if not success:
            raise HTTPException(status_code=500, detail="Failed to update communication")

        # Получаем обновленную запись
        communication = database_service.get_communication_by_id(communication_id)
        if not communication:
            raise HTTPException(status_code=404, detail="Communication not found")

        print(f"✅ Коммуникация обновлена: {communication_id}")
        return CommunicationResponse(**communication)

    except ValueError as e:
        print(f"❌ Ошибка валидации: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Ошибка обновления коммуникации: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/communications/{communication_id}")
async def delete_communication(
        communication_id: str,
        current_user: dict = Depends(get_current_user)
):
    """Удаление записи о коммуникации"""
    print(f"🗑️ Удаление коммуникации {communication_id}, пользователь: {current_user.get('email')}")

    try:
        success = database_service.delete_communication(
            communication_id=communication_id,
            user_id=current_user['id']
        )

        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete communication")

        print(f"✅ Коммуникация удалена: {communication_id}")
        return {"message": "Communication deleted successfully"}

    except ValueError as e:
        print(f"❌ Ошибка валидации: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Ошибка удаления коммуникации: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


# ========== Расширенные возможности ==========

@router.get("/{student_id}/with-communications", response_model=StudentWithCommunications)
async def get_student_with_communications(
        student_id: str,
        limit: int = Query(10, ge=1, le=50),
        current_user: dict = Depends(get_current_user)
):
    """Получение студента с последними коммуникациями"""
    print(f"👤📞 Получение студента {student_id} с коммуникациями, пользователь: {current_user.get('email')}")

    try:
        # Получаем студента
        student = database_service.get_student_by_id(student_id)
        if not student:
            raise HTTPException(status_code=404, detail="Student not found")

        # Проверка прав доступа для преподавателя
        if current_user.get('role') == "teacher":
            teacher_departments = current_user.get('assigned_departments', [])
            teacher_specialities = current_user.get('assigned_specialities', [])

            student_department = student.get('department_id')
            student_speciality = student.get('speciality_id')

            if student_department and 'all' not in teacher_departments:
                if student_department not in teacher_departments:
                    raise HTTPException(status_code=403, detail="Нет доступа к этому студенту")

            if student_speciality and 'all' not in teacher_specialities:
                if student_speciality not in teacher_specialities:
                    raise HTTPException(status_code=403, detail="Нет доступа к этому студенту")

        # Получаем последние коммуникации
        communications = database_service.get_communications_by_student(
            student_id=student_id,
            user_id=current_user['id'],
            limit=limit
        )

        # Определяем дату последней коммуникации
        last_communication = None
        if communications:
            dates = [comm.get('date_time') for comm in communications if comm.get('date_time')]
            if dates:
                last_communication = max(dates)

        print(f"✅ Студент с коммуникациями получен")
        return StudentWithCommunications(
            student=StudentResponse(**student),
            communications=[CommunicationResponse(**comm) for comm in communications],
            total_communications=len(communications),
            last_communication=last_communication
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Ошибка получения студента с коммуникациями: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search/by-phone/{phone}")
async def search_student_by_phone(
        phone: str,
        current_user: dict = Depends(get_current_user)
):
    """Поиск студента по номеру телефона"""
    print(f"🔍 Поиск студента по телефону {phone}, пользователь: {current_user.get('email')}")

    try:
        # Ищем студентов
        students = database_service.search_students(search_term=phone, limit=10)

        # Фильтруем по точному совпадению телефона
        exact_matches = [
            student for student in students
            if student.get('phone') == phone
        ]

        # Фильтруем по доступным направлениям для преподавателя
        if current_user.get('role') == "teacher":
            teacher_departments = current_user.get('assigned_departments', [])
            teacher_specialities = current_user.get('assigned_specialities', [])

            if 'all' not in teacher_departments or 'all' not in teacher_specialities:
                accessible_matches = []
                for student in exact_matches:
                    student_department = student.get('department_id')
                    student_speciality = student.get('speciality_id')

                    department_ok = True
                    speciality_ok = True

                    if student_department and 'all' not in teacher_departments:
                        department_ok = student_department in teacher_departments

                    if student_speciality and 'all' not in teacher_specialities:
                        speciality_ok = student_speciality in teacher_specialities

                    if department_ok and speciality_ok:
                        accessible_matches.append(student)

                exact_matches = accessible_matches

        print(f"✅ Найдено совпадений: {len(exact_matches)}")
        return {"students": exact_matches}

    except Exception as e:
        print(f"❌ Ошибка поиска: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


# ========== Статистика ==========

@router.get("/stats/my")
async def get_my_stats(
        current_user: dict = Depends(get_current_user)
):
    """Получение статистики текущего преподавателя"""
    print(f"📊 Получение моей статистики, пользователь: {current_user.get('email')}")

    if current_user.get('role') != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can access stats")

    try:
        # Получаем студентов преподавателя
        students = database_service.get_students_by_teacher(
            teacher_id=current_user['id'],
            limit=1000
        )

        # Получаем коммуникации
        communications = database_service.get_communications_by_teacher(
            teacher_id=current_user['id'],
            limit=1000
        )

        # Считаем статистику
        stats = {
            "total_students": len(students),
            "active_students": sum(1 for s in students if s.get('status') == 'active'),
            "inactive_students": sum(1 for s in students if s.get('status') == 'inactive'),
            "total_communications": len(communications),
            "recent_communications": len([c for c in communications
                                          if isinstance(c.get('date_time'), datetime)
                                          and c.get('date_time') > datetime.utcnow() - timedelta(days=7)]),
            "students_by_department": {},
            "students_by_speciality": {}
        }

        # Получаем информацию о пользователе
        user_info = database_service.get_user_by_id(current_user['id'])

        if user_info:
            stats["max_students"] = user_info.get('max_students', 20)
            stats["current_students_count"] = user_info.get('current_students_count', 0)
        else:
            stats["max_students"] = 20
            stats["current_students_count"] = len(students)

        # Считаем по направлениям
        for student in students:
            department_id = student.get('department_id', 'Не указано')
            if department_id:
                stats['students_by_department'][department_id] = stats['students_by_department'].get(department_id,
                                                                                                     0) + 1

            speciality_id = student.get('speciality_id', 'Не указано')
            if speciality_id:
                stats['students_by_speciality'][speciality_id] = stats['students_by_speciality'].get(speciality_id,
                                                                                                     0) + 1

        print(f"✅ Статистика получена")
        return {
            "status": "success",
            "stats": stats,
            "user": {
                "id": current_user.get('id'),
                "email": current_user.get('email'),
                "full_name": current_user.get('full_name')
            }
        }

    except Exception as e:
        print(f"❌ Ошибка получения статистики: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


# ========== Пагинация ==========

@router.get("/paginated/my", response_model=List[StudentResponse])
async def get_my_students_paginated(
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
        current_user: dict = Depends(get_current_user)
):
    """Получение студентов текущего преподавателя с пагинацией"""
    print(f"📄 Пагинация студентов, страница {page}, пользователь: {current_user.get('email')}")

    if current_user.get('role') != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can access students")

    try:
        skip = (page - 1) * page_size

        students = database_service.get_students_by_teacher(
            teacher_id=current_user['id'],
            limit=page_size,
            offset=skip
        )

        print(f"✅ Страница {page}: {len(students)} студентов")
        return [StudentResponse(**student) for student in students]
    except Exception as e:
        print(f"❌ Ошибка пагинации студентов: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))
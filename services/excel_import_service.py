import pandas as pd
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional, Set
from datetime import datetime
import re

from database.schema import (
    Student, StudentApplication, Profile,
    StudentStatus, ContactStatus, MeetingStatus, CallStatus,
    DecisionStatus, DocumentsStatus, StudyForm, StudyBasis,
    ApplicationStatus
)


class ExcelImportService:

    def __init__(self, db: Session, user_id: int):
        self.db = db
        self.user_id = user_id
        self.column_mapping = {
            'фио': 'full_name',
            'ффио': 'full_name',
            'фамилия имя отчество': 'full_name',
            'ф.и.о.': 'full_name',
            'full_name': 'full_name',
            'телефон': 'phone',
            'phone': 'phone',
            'профиль': 'profile_name',
            'образовательная программа': 'profile_name',
            'обр.программа': 'profile_name',
            'program': 'profile_name',
            'направление': 'profile_name',
            'баллы': 'score',
            'сумма баллов': 'score',
            'score': 'score',
            'егэ': 'score',
            'приоритет': 'priority',
            'priority': 'priority',
            'форма обучения': 'study_form',
            'форма': 'study_form',
            'основа обучения': 'study_basis',
            'основа': 'study_basis',
            'вид мест': 'study_basis',
            'id поступающего': 'russian_student_id',
            'russian_student_id': 'russian_student_id',
            'идентификатор': 'russian_student_id',
            'id студента': 'russian_student_id',
            'уникальный код поступающего': 'russian_student_id',  # ← ДОБАВИТЬ ЭТУ СТРОКУ
            'уникальный код': 'russian_student_id',  # ← И ЭТУ НА ВСЯКИЙ СЛУЧАЙ
            'почта': 'email',
            'email': 'email'
        }
        self.study_form_mapping = {
            'очная': StudyForm.FULL_TIME,
            'очная форма': StudyForm.FULL_TIME,
            'full-time': StudyForm.FULL_TIME,
            'очно-заочная': StudyForm.PART_TIME,
            'очно-заочная форма': StudyForm.PART_TIME,
            'part-time': StudyForm.PART_TIME,
            'заочная': StudyForm.CORRESPONDENCE,
            'заочная форма': StudyForm.CORRESPONDENCE,
            'correspondence': StudyForm.CORRESPONDENCE,
        }
        self.study_basis_mapping = {
            'бюджетная': StudyBasis.BUDGET,
            'бюджет': StudyBasis.BUDGET,
            'бюджетная основа': StudyBasis.BUDGET,
            'бюджетные места': StudyBasis.BUDGET,
            'платная': StudyBasis.PAID,
            'платное': StudyBasis.PAID,
            'платные места': StudyBasis.PAID,
            'коммерческая': StudyBasis.PAID,
            'целевая': StudyBasis.TARGET,
            'целевое': StudyBasis.TARGET,
            'целевые места': StudyBasis.TARGET,
        }

    async def import_from_dataframe(
            self,
            df: pd.DataFrame,
            create_missing_profiles: bool = False,
            duplicate_strategy: str = 'skip',
            replace_ids: Set[int] = set()
    ) -> Dict[str, Any]:
        df = self._normalize_columns(df)
        missing_columns = []
        if 'full_name' not in df.columns:
            missing_columns.append('ФИО')
        if 'phone' not in df.columns:
            missing_columns.append('Телефон')
        if 'russian_student_id' not in df.columns:
            missing_columns.append('ID поступающего')

        if missing_columns:
            return {
                'success': False,
                'total_rows': len(df),
                'created_students': 0,
                'updated_students': 0,
                'created_applications': 0,
                'errors': [{"row": 0, "error": f"Отсутствуют обязательные колонки: {', '.join(missing_columns)}"}],
                'warnings': [],
                'message': f"Ошибка: в файле нет обязательных колонок: {', '.join(missing_columns)}"
            }
        created_students = 0
        updated_students = 0
        created_applications = 0
        errors = []
        warnings = []
        for idx, row in df.iterrows():
            row_num = idx + 2

            try:
                result = await self._process_row(
                    row=row,
                    row_num=row_num,
                    create_missing_profiles=create_missing_profiles,
                    duplicate_strategy=duplicate_strategy,
                    replace_ids=replace_ids
                )

                if result.get('error'):
                    errors.append({
                        "row": row_num,
                        "error": result['error']
                    })
                else:
                    if result.get('created'):
                        created_students += 1
                    if result.get('updated'):
                        updated_students += 1

                    created_applications += result.get('applications_created', 0)

                    if result.get('warnings'):
                        warnings.extend([
                            {"row": row_num, "warning": w}
                            for w in result['warnings']
                        ])

            except Exception as e:
                errors.append({
                    "row": row_num,
                    "error": f"Ошибка обработки строки: {str(e)}"
                })

        # Коммитим все изменения, если не было критических ошибок импорта строк
        if not errors:
            self.db.commit()
        else:
            self.db.rollback()

        return {
            'success': len(errors) == 0,
            'total_rows': len(df),
            'created_students': created_students,
            'updated_students': updated_students,
            'created_applications': created_applications,
            'errors': errors,
            'warnings': warnings,
            'message': f"Импорт завершен. Создано: {created_students}, Обновлено: {updated_students}, Заявлений: {created_applications}"
        }

    def _normalize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Нормализует названия колонок"""
        df.columns = df.columns.str.strip().str.lower()
        rename_dict = {}
        for col in df.columns:
            if col in self.column_mapping:
                rename_dict[col] = self.column_mapping[col]
        if rename_dict:
            df = df.rename(columns=rename_dict)
        return df

    async def _process_row(
            self,
            row: pd.Series,
            row_num: int,
            create_missing_profiles: bool,
            duplicate_strategy: str,  # Новый параметр (получаем из роутера)
            replace_ids: Set[int]  # Новый параметр (получаем из роутера)
    ) -> Dict[str, Any]:
        """Обрабатывает одну строку Excel"""

        result = {
            'created': False,
            'updated': False,
            'applications_created': 0,
            'warnings': [],
            'error': None
        }

        # 1. ФИО (ОБЯЗАТЕЛЬНО)
        full_name = self._get_value(row, 'full_name')
        if not full_name:
            result['error'] = "ФИО обязательно"
            return result

        # 2. Телефон (ОБЯЗАТЕЛЬНО)
        phone_raw = self._get_value(row, 'phone')
        if not phone_raw:
            result['error'] = "Телефон обязателен"
            return result

        # 3. Russian Student ID (ОБЯЗАТЕЛЬНО)
        russian_student_id_raw = self._get_value(row, 'russian_student_id')
        if russian_student_id_raw is None:
            result['error'] = "ID поступающего обязателен"
            return result

        try:
            russian_student_id = int(float(russian_student_id_raw))
            if russian_student_id <= 0:
                result['error'] = "ID должен быть положительным числом"
                return result
        except (ValueError, TypeError):
            result['error'] = "ID должен быть числом"
            return result

        email_raw = self._get_value(row, 'email')
        email = str(email_raw).strip() if email_raw else None

        # --- НОВАЯ ЛОГИКА ОБРАБОТКИ ДУБЛИКАТОВ ---
        existing_student = self.db.query(Student).filter(
            Student.russian_student_id == russian_student_id
        ).first()

        if existing_student:
            # --- ЛОГИКА ДЛЯ СУЩЕСТВУЮЩИХ СТУДЕНТОВ ---

            if duplicate_strategy == 'skip':
                result['error'] = f"Дубликат ID {russian_student_id}. Строка пропущена согласно стратегии."
                return result

            elif duplicate_strategy == 'replace_all':
                # Просто идем дальше на ветку обновления (заменяем)
                pass

            elif duplicate_strategy == 'replace_selected':
                if russian_student_id not in replace_ids:
                    result['error'] = f"Дубликат ID {russian_student_id} не выбран для замены. Строка пропущена."
                    return result
                # Если ID в списке - идем дальше на ветку обновления

            # --- ВЕТКА ОБНОВЛЕНИЯ / ЗАМЕНЫ ---
            result['updated'] = True

            existing_student.full_name = str(full_name).strip()
            existing_student.phone = self._normalize_phone(str(phone_raw))

            # Обновляем email если указан или изменился
            if email:
                additional_contacts = existing_student.additional_contacts or {}
                if additional_contacts.get('email') != email:
                    additional_contacts['email'] = email
                    existing_student.additional_contacts = additional_contacts

            study_form_new = self._parse_study_form(row)
            if study_form_new is not None:  # Обновляем только если в файле указано значение
                existing_student.study_form = study_form_new

            study_basis_new = self._parse_study_basis(row)
            if study_basis_new is not None:
                existing_student.study_basis = study_basis_new

            existing_student.updated_at = datetime.utcnow()
            self.db.flush()

            student_for_apps = existing_student

        else:
            result['created'] = True

            study_form_new = self._parse_study_form(row)
            study_basis_new = self._parse_study_basis(row)

            additional_contacts = {}
            if email:
                additional_contacts['email'] = email

            new_student = Student(
                russian_student_id=russian_student_id,
                full_name=str(full_name).strip(),
                phone=self._normalize_phone(str(phone_raw)),
                additional_contacts=additional_contacts if additional_contacts else None,
                study_form=study_form_new,
                study_basis=study_basis_new,
                status=StudentStatus.ACTIVE,
                kurator_id=self.user_id,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            self.db.add(new_student)
            self.db.flush()

            student_for_apps = new_student

        # 6. Заявление (опционально) - логика не изменилась
        profile_name_val = self._get_value(row, 'profile_name')
        if profile_name_val and str(profile_name_val).strip():
            await self._process_application(
                student=student_for_apps,
                profile_name=str(profile_name_val).strip(),
                row=row,
                create_missing_profiles=create_missing_profiles,
                result=result
            )

        return result


async def _process_application(
        self,
        student: Student,
        profile_name: str,
        row: pd.Series,
        create_missing_profiles: bool,
        result: Dict[str, Any]
):
    """Обрабатывает заявление студента на профиль"""

    profile = self.db.query(Profile).filter(
        Profile.name.ilike(f"%{profile_name}%")
    ).first()

    if not profile:
        profile = self.db.query(Profile).filter(
            Profile.name.ilike(profile_name)
        ).first()

    if not profile:
        result['warnings'].append(f"Не найден профиль '{profile_name}'")
        return

    # Проверяем существующее заявление на этот же профиль для этого студента
    existing_application = self.db.query(StudentApplication).filter(
        StudentApplication.student_id == student.id,
        StudentApplication.profile_id == profile.id
    ).first()

    if existing_application:
        result['warnings'].append(f"Заявление на профиль '{profile_name}' уже существует")
        return

    score_raw = self._get_value(row, 'score')
    total_score = None
    if score_raw is not None:
        try:
            total_score = int(float(score_raw))
        except (ValueError, TypeError):
            result['warnings'].append(f"Не удалось распознать баллы: {score_raw}")

    priority_raw = self._get_value(row, 'priority')
    priority_value = None
    if priority_raw is not None:
        try:
            priority_value = int(float(priority_raw))
            priority_value = max(1, min(10, priority_value))  # Ограничиваем от 1 до 10
        except (ValueError, TypeError):
            priority_value = 1

    study_form_for_apps = self._parse_study_form(row) or student.study_form or profile.study_form
    study_basis_for_apps = self._parse_study_basis(row) or student.study_basis or profile.study_basis

    application = StudentApplication(
        student_id=student.id,
        department_id=profile.speciality.department_id if profile.speciality else None,
        speciality_id=profile.speciality_id,
        profile_id=profile.id,
        total_score=total_score,
        priority=priority_value,
        study_form=study_form_for_apps,
        study_basis=study_basis_for_apps,
        study_level=profile.study_level,
        application_status=ApplicationStatus.PENDING,
        consent_status=False,
        participation=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )

    self.db.add(application)

    # Увеличиваем счетчик только если приложение успешно создано и добавлено в сессию
    try:
        self.db.flush()
        result['applications_created'] += 1
    except Exception as e:
        result['warnings'].append(f"Ошибка при создании заявления: {str(e)}")


def _parse_study_form(self, row: pd.Series) -> Optional[StudyForm]:
    """Парсит форму обучения"""
    value = self._get_value(row, 'study_form')
    if not value:
        return None

    str_value = str(value).strip().lower()
    for key, form in self.study_form_mapping.items():
        if key in str_value or str_value in key:  # Улучшенный поиск
            return form
    return None


def _parse_study_basis(self, row: pd.Series) -> Optional[StudyBasis]:
    """Парсит основу обучения"""
    value = self._get_value(row, 'study_basis')
    if not value:
        return None

    str_value = str(value).strip().lower()
    for key, basis in self.study_basis_mapping.items():
        if key in str_value or str_value in key:
            return basis
    return None


def _get_value(self, row: pd.Series, key: str) -> Any:
    if key in row and pd.notna(row[key]):
        return row[key]
    return None


def _normalize_phone(self, phone: str) -> str:
    digits = re.sub(r'\D', '', phone)
    if len(digits) == 11 and digits.startswith('8'):
        digits = '+7' + digits[1:]

    if len(digits) == 11 and digits.startswith('7'):
        return '+' + digits[1:]
    return phone
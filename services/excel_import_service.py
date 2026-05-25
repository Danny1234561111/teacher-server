import pandas as pd
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional, Set
from datetime import datetime
import re

from database.schema import (
    Student, StudentApplication, Profile,
    StudentStatus, StudyForm, StudyBasis,
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
            'russian_student_id': 'russian_student_id',
            'идентификатор': 'russian_student_id',
            'id студента': 'russian_student_id',
            'уникальный код поступающего': 'russian_student_id',
            'уникальный код': 'russian_student_id',
            'id поступающего': 'russian_student_id',
            'ид поступающего': 'russian_student_id',
            'почта': 'email',
            'email': 'email'
        }
        self.study_form_mapping = {
            'очная': StudyForm.FULL_TIME,
            'очная форма': StudyForm.FULL_TIME,
            'очная форма обучения': StudyForm.FULL_TIME,
            'full-time': StudyForm.FULL_TIME,
            'очно-заочная': StudyForm.PART_TIME,
            'очно-заочная форма': StudyForm.PART_TIME,
            'part-time': StudyForm.PART_TIME,
            'заочная': StudyForm.CORRESPONDENCE,
            'заочная форма': StudyForm.CORRESPONDENCE,
            'заочная форма обучения': StudyForm.CORRESPONDENCE,
            'correspondence': StudyForm.CORRESPONDENCE,
        }
        self.study_basis_mapping = {
            'бюджетная': StudyBasis.BUDGET,
            'бюджет': StudyBasis.BUDGET,
            'бюджетная основа': StudyBasis.BUDGET,
            'бюджетные места': StudyBasis.BUDGET,
            'основные места в рамках кцп': StudyBasis.BUDGET,
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
        # Нормализуем колонки
        df = self._normalize_columns(df)

        # Проверяем обязательные колонки
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
                'message': f"Ошибка: в файле нет обязательных колонок",
                'duplicates_found': None
            }

        # Преобразуем DataFrame в список словарей
        records = df.to_dict(orient='records')

        # Сначала собираем ВСЕ ID из файла для проверки дубликатов
        all_ids = []
        id_to_row_map = {}  # Для хранения соответствия ID -> строка (первые вхождения)

        for idx, row_dict in enumerate(records):
            russian_student_id_raw = row_dict.get('russian_student_id')
            if pd.isna(russian_student_id_raw) or russian_student_id_raw is None:
                continue

            try:
                if isinstance(russian_student_id_raw, str):
                    cleaned = re.sub(r'[^\d]', '', russian_student_id_raw)
                    student_id = int(cleaned) if cleaned else None
                else:
                    student_id = int(float(russian_student_id_raw))

                if student_id and student_id > 0:
                    all_ids.append(student_id)
                    if student_id not in id_to_row_map:
                        id_to_row_map[student_id] = idx
            except (ValueError, TypeError):
                continue

        # Находим дубликаты в БД
        existing_students = self.db.query(Student).filter(
            Student.russian_student_id.in_(set(all_ids))
        ).all()

        duplicates_found = [
            {"id": s.russian_student_id, "full_name": s.full_name}
            for s in existing_students
        ]

        # Если стратегия SKIP и есть дубликаты - возвращаем ошибку со списком дубликатов
        if duplicate_strategy == 'skip' and duplicates_found:
            return {
                'success': False,
                'total_rows': len(df),
                'created_students': 0,
                'updated_students': 0,
                'created_applications': 0,
                'errors': [
                    {"row": 0, "error": f"Найдено {len(duplicates_found)} дубликатов. Используйте стратегию замены."}],
                'warnings': [],
                'message': "Импорт прерван: найдены дубликаты",
                'duplicates_found': duplicates_found
            }

        created_students = 0
        updated_students = 0
        created_applications = 0
        errors = []
        warnings = []

        for idx, row_dict in enumerate(records):
            row_num = idx + 2

            try:
                result = await self._process_row_dict(
                    row_dict=row_dict,
                    row_num=row_num,
                    create_missing_profiles=create_missing_profiles,
                    duplicate_strategy=duplicate_strategy,
                    replace_ids=replace_ids,
                    duplicates_found=duplicates_found  # Передаем список дубликатов
                )

                if result.get('error'):
                    errors.append({"row": row_num, "error": result['error']})
                else:
                    if result.get('created'):
                        created_students += 1
                    if result.get('updated'):
                        updated_students += 1
                    created_applications += result.get('applications_created', 0)
                    if result.get('warnings'):
                        warnings.extend([{"row": row_num, "warning": w} for w in result['warnings']])

            except Exception as e:
                errors.append({"row": row_num, "error": f"Ошибка: {str(e)}"})

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
            'message': f"Импорт завершен. Создано: {created_students}, Обновлено: {updated_students}, Заявлений: {created_applications}",
            'duplicates_found': None  # Не возвращаем дубликаты при успешном импорте
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

    async def _process_row_dict(
            self,
            row_dict: Dict[str, Any],
            row_num: int,
            create_missing_profiles: bool,
            duplicate_strategy: str,
            replace_ids: Set[int],
            duplicates_found: List[Dict] = None
    ) -> Dict[str, Any]:
        """Обрабатывает одну строку из словаря"""

        result = {
            'created': False,
            'updated': False,
            'applications_created': 0,
            'warnings': [],
            'error': None
        }

        # Безопасно получаем значения из словаря
        full_name = row_dict.get('full_name')
        phone_raw = row_dict.get('phone')
        russian_student_id_raw = row_dict.get('russian_student_id')
        email_raw = row_dict.get('email')
        profile_name_val = row_dict.get('profile_name')
        score_raw = row_dict.get('score')
        priority_raw = row_dict.get('priority')
        study_form_val = row_dict.get('study_form')
        study_basis_val = row_dict.get('study_basis')

        # Проверяем NaN
        if pd.isna(full_name) or not full_name or not str(full_name).strip():
            result['error'] = "ФИО обязательно"
            return result

        if pd.isna(phone_raw) or not phone_raw or not str(phone_raw).strip():
            result['error'] = "Телефон обязателен"
            return result

        if pd.isna(russian_student_id_raw) or russian_student_id_raw is None:
            result['error'] = "ID поступающего обязателен"
            return result

        # Парсим ID
        try:
            if isinstance(russian_student_id_raw, str):
                cleaned = re.sub(r'[^\d]', '', russian_student_id_raw)
                russian_student_id = int(cleaned) if cleaned else None
            else:
                russian_student_id = int(float(russian_student_id_raw))

            if russian_student_id is None or russian_student_id <= 0:
                result['error'] = "ID должен быть положительным числом"
                return result
        except (ValueError, TypeError):
            result['error'] = f"ID должен быть числом, получено: {russian_student_id_raw}"
            return result

        # Email
        email = None
        if email_raw and not pd.isna(email_raw):
            email = str(email_raw).strip()

        # Проверка на дубликаты
        existing_student = self.db.query(Student).filter(
            Student.russian_student_id == russian_student_id
        ).first()

        if existing_student:
            if duplicate_strategy == 'skip':
                result['error'] = f"Дубликат ID {russian_student_id}. Строка пропущена."
                return result
            elif duplicate_strategy == 'replace_selected':
                if russian_student_id not in replace_ids:
                    result['error'] = f"Дубликат ID {russian_student_id} не выбран для замены. Строка пропущена."
                    return result

            # Обновление существующего
            result['updated'] = True
            existing_student.full_name = str(full_name).strip()
            existing_student.phone = self._normalize_phone(str(phone_raw))

            if email:
                additional_contacts = existing_student.additional_contacts or {}
                additional_contacts['email'] = email
                existing_student.additional_contacts = additional_contacts

            if study_form_val and not pd.isna(study_form_val):
                parsed_form = self._parse_study_form(str(study_form_val))
                if parsed_form:
                    existing_student.study_form = parsed_form

            if study_basis_val and not pd.isna(study_basis_val):
                parsed_basis = self._parse_study_basis(str(study_basis_val))
                if parsed_basis:
                    existing_student.study_basis = parsed_basis

            existing_student.updated_at = datetime.utcnow()
            self.db.flush()
            student_for_apps = existing_student

        else:
            # Создание нового
            result['created'] = True

            study_form_parsed = None
            if study_form_val and not pd.isna(study_form_val):
                study_form_parsed = self._parse_study_form(str(study_form_val))

            study_basis_parsed = None
            if study_basis_val and not pd.isna(study_basis_val):
                study_basis_parsed = self._parse_study_basis(str(study_basis_val))

            additional_contacts = {}
            if email:
                additional_contacts['email'] = email

            new_student = Student(
                russian_student_id=russian_student_id,
                full_name=str(full_name).strip(),
                phone=self._normalize_phone(str(phone_raw)),
                additional_contacts=additional_contacts if additional_contacts else None,
                study_form=study_form_parsed,
                study_basis=study_basis_parsed,
                status=StudentStatus.ACTIVE,
                kurator_id=self.user_id,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            self.db.add(new_student)
            self.db.flush()
            student_for_apps = new_student

        # Обработка заявления
        if profile_name_val and not pd.isna(profile_name_val) and str(profile_name_val).strip():
            await self._process_application_dict(
                student=student_for_apps,
                profile_name=str(profile_name_val).strip(),
                score_raw=score_raw,
                priority_raw=priority_raw,
                study_form_val=study_form_val,
                study_basis_val=study_basis_val,
                create_missing_profiles=create_missing_profiles,
                result=result
            )

        return result

    async def _process_application_dict(
            self,
            student: Student,
            profile_name: str,
            score_raw,
            priority_raw,
            study_form_val,
            study_basis_val,
            create_missing_profiles: bool,
            result: Dict[str, Any]
    ):
        """Обрабатывает заявление из словаря"""

        # Поиск профиля
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

        # Проверка существующего заявления
        existing_application = self.db.query(StudentApplication).filter(
            StudentApplication.student_id == student.id,
            StudentApplication.profile_id == profile.id
        ).first()

        if existing_application:
            result['warnings'].append(f"Заявление на профиль '{profile_name}' уже существует")
            return

        # Парсим баллы
        total_score = None
        if score_raw and not pd.isna(score_raw):
            try:
                total_score = int(float(score_raw))
            except (ValueError, TypeError):
                result['warnings'].append(f"Не удалось распознать баллы: {score_raw}")

        # Парсим приоритет
        priority_value = 1
        if priority_raw and not pd.isna(priority_raw):
            try:
                priority_value = int(float(priority_raw))
                priority_value = max(1, min(10, priority_value))
            except (ValueError, TypeError):
                pass

        # Форма и основа обучения
        study_form_for_apps = None
        if study_form_val and not pd.isna(study_form_val):
            study_form_for_apps = self._parse_study_form(str(study_form_val))
        if not study_form_for_apps:
            study_form_for_apps = student.study_form or profile.study_form

        study_basis_for_apps = None
        if study_basis_val and not pd.isna(study_basis_val):
            study_basis_for_apps = self._parse_study_basis(str(study_basis_val))
        if not study_basis_for_apps:
            study_basis_for_apps = student.study_basis or profile.study_basis

        # Создаем заявление
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

        try:
            self.db.flush()
            result['applications_created'] += 1
        except Exception as e:
            result['warnings'].append(f"Ошибка при создании заявления: {str(e)}")

    def _parse_study_form(self, value: Any) -> Optional[StudyForm]:
        """Парсит форму обучения"""
        if not value or pd.isna(value):
            return None
        str_value = str(value).strip().lower()
        for key, form in self.study_form_mapping.items():
            if key in str_value:
                return form
        return None

    def _parse_study_basis(self, value: Any) -> Optional[StudyBasis]:
        """Парсит основу обучения"""
        if not value or pd.isna(value):
            return None
        str_value = str(value).strip().lower()
        for key, basis in self.study_basis_mapping.items():
            if key in str_value:
                return basis
        return None

    def _normalize_phone(self, phone: str) -> str:
        """Нормализует номер телефона"""
        digits = re.sub(r'\D', '', phone)
        if len(digits) == 11 and digits.startswith('8'):
            return '+7' + digits[1:]
        elif len(digits) == 11 and digits.startswith('7'):
            return '+' + digits
        elif len(digits) == 10:
            return '+7' + digits
        return phone
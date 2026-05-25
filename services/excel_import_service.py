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
            'заочная': StudyForm.CORRESPONDENCE,
            'заочная форма': StudyForm.CORRESPONDENCE,
            'очно-заочная': StudyForm.PART_TIME,
        }
        self.study_basis_mapping = {
            'бюджетная': StudyBasis.BUDGET,
            'бюджет': StudyBasis.BUDGET,
            'бюджетные места': StudyBasis.BUDGET,
            'основные места в рамках кцп': StudyBasis.BUDGET,
            'платная': StudyBasis.PAID,
            'платное': StudyBasis.PAID,
            'платные места': StudyBasis.PAID,
            'целевая': StudyBasis.TARGET,
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
                'errors': [{"row": 0, "error": f"Отсутствуют колонки: {', '.join(missing_columns)}"}],
                'warnings': [],
                'message': "Ошибка: нет обязательных колонок",
                'duplicates_found': None
            }

        # Проверка дубликатов для стратегии skip
        ids_from_file = []
        for val in df['russian_student_id'].dropna():
            try:
                if isinstance(val, str):
                    cleaned = re.sub(r'[^\d]', '', val)
                    if cleaned:
                        ids_from_file.append(int(cleaned))
                else:
                    ids_from_file.append(int(float(val)))
            except (ValueError, TypeError):
                continue

        existing_students = self.db.query(Student).filter(
            Student.russian_student_id.in_(set(ids_from_file))
        ).all()

        duplicates_found = [{"id": s.russian_student_id, "full_name": s.full_name} for s in existing_students]

        if duplicate_strategy == 'skip' and duplicates_found:
            return {
                'success': False,
                'total_rows': len(df),
                'created_students': 0,
                'updated_students': 0,
                'created_applications': 0,
                'errors': [{"row": 0, "error": "Найдены дубликаты"}],
                'warnings': [],
                'message': "Импорт прерван: найдены дубликаты",
                'duplicates_found': duplicates_found
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
                    errors.append({"row": row_num, "error": result['error']})
                else:
                    if result.get('created'):
                        created_students += 1
                    if result.get('updated'):
                        updated_students += 1
                    created_applications += result.get('applications_created', 0)
                    for w in result.get('warnings', []):
                        warnings.append({"row": row_num, "warning": w})
            except Exception as e:
                errors.append({"row": row_num, "error": str(e)})

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
            'duplicates_found': duplicates_found if duplicate_strategy == 'skip' else None
        }

    def _normalize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
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
            duplicate_strategy: str,
            replace_ids: Set[int]
    ) -> Dict[str, Any]:
        result = {'created': False, 'updated': False, 'applications_created': 0, 'warnings': [], 'error': None}

        # Получаем значения (key in row.index - ЭТО ВАЖНО!)
        full_name = row['full_name'] if 'full_name' in row.index and pd.notna(row['full_name']) else None
        phone_raw = row['phone'] if 'phone' in row.index and pd.notna(row['phone']) else None
        russian_student_id_raw = row['russian_student_id'] if 'russian_student_id' in row.index and pd.notna(
            row['russian_student_id']) else None
        email_raw = row['email'] if 'email' in row.index and pd.notna(row['email']) else None
        profile_name_val = row['profile_name'] if 'profile_name' in row.index and pd.notna(
            row['profile_name']) else None
        score_raw = row['score'] if 'score' in row.index and pd.notna(row['score']) else None
        priority_raw = row['priority'] if 'priority' in row.index and pd.notna(row['priority']) else None
        study_form_val = row['study_form'] if 'study_form' in row.index and pd.notna(row['study_form']) else None
        study_basis_val = row['study_basis'] if 'study_basis' in row.index and pd.notna(row['study_basis']) else None

        if not full_name or not str(full_name).strip():
            result['error'] = "ФИО обязательно"
            return result

        if not phone_raw or not str(phone_raw).strip():
            result['error'] = "Телефон обязателен"
            return result

        if russian_student_id_raw is None:
            result['error'] = "ID обязателен"
            return result

        try:
            if isinstance(russian_student_id_raw, str):
                cleaned = re.sub(r'[^\d]', '', russian_student_id_raw)
                russian_student_id = int(cleaned) if cleaned else None
            else:
                russian_student_id = int(float(russian_student_id_raw))
            if not russian_student_id or russian_student_id <= 0:
                result['error'] = "ID должен быть положительным числом"
                return result
        except (ValueError, TypeError):
            result['error'] = f"ID должен быть числом: {russian_student_id_raw}"
            return result

        email = str(email_raw).strip() if email_raw else None

        existing_student = self.db.query(Student).filter(Student.russian_student_id == russian_student_id).first()

        if existing_student:
            if duplicate_strategy == 'skip':
                result['error'] = f"Дубликат ID {russian_student_id}"
                return result
            elif duplicate_strategy == 'replace_selected' and russian_student_id not in replace_ids:
                result['error'] = f"Дубликат ID {russian_student_id} не выбран для замены"
                return result

            result['updated'] = True
            existing_student.full_name = str(full_name).strip()
            existing_student.phone = self._normalize_phone(str(phone_raw))
            if email:
                additional_contacts = existing_student.additional_contacts or {}
                additional_contacts['email'] = email
                existing_student.additional_contacts = additional_contacts
            if study_form_val:
                existing_student.study_form = self._parse_study_form(str(study_form_val))
            if study_basis_val:
                existing_student.study_basis = self._parse_study_basis(str(study_basis_val))
            existing_student.updated_at = datetime.utcnow()
            self.db.flush()
            student_for_apps = existing_student
        else:
            result['created'] = True
            new_student = Student(
                russian_student_id=russian_student_id,
                full_name=str(full_name).strip(),
                phone=self._normalize_phone(str(phone_raw)),
                additional_contacts={'email': email} if email else None,
                study_form=self._parse_study_form(study_form_val) if study_form_val else None,
                study_basis=self._parse_study_basis(study_basis_val) if study_basis_val else None,
                status=StudentStatus.ACTIVE,
                kurator_id=self.user_id,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            self.db.add(new_student)
            self.db.flush()
            student_for_apps = new_student

        if profile_name_val and str(profile_name_val).strip():
            await self._process_application(
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

    async def _process_application(
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
        profile = self.db.query(Profile).filter(Profile.name.ilike(f"%{profile_name}%")).first()
        if not profile:
            result['warnings'].append(f"Не найден профиль '{profile_name}'")
            return

        existing = self.db.query(StudentApplication).filter(
            StudentApplication.student_id == student.id,
            StudentApplication.profile_id == profile.id
        ).first()
        if existing:
            result['warnings'].append(f"Заявление на '{profile_name}' уже существует")
            return

        total_score = None
        if score_raw:
            try:
                total_score = int(float(score_raw))
            except:
                pass

        priority = 1
        if priority_raw:
            try:
                priority = max(1, min(10, int(float(priority_raw))))
            except:
                pass

        application = StudentApplication(
            student_id=student.id,
            department_id=profile.speciality.department_id if profile.speciality else None,
            speciality_id=profile.speciality_id,
            profile_id=profile.id,
            total_score=total_score,
            priority=priority,
            study_form=self._parse_study_form(study_form_val) if study_form_val else profile.study_form,
            study_basis=self._parse_study_basis(study_basis_val) if study_basis_val else profile.study_basis,
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
            result['warnings'].append(f"Ошибка создания заявления: {str(e)}")

    def _parse_study_form(self, value) -> Optional[StudyForm]:
        if not value:
            return None
        str_value = str(value).strip().lower()
        for key, form in self.study_form_mapping.items():
            if key in str_value:
                return form
        return None

    def _parse_study_basis(self, value) -> Optional[StudyBasis]:
        if not value:
            return None
        str_value = str(value).strip().lower()
        for key, basis in self.study_basis_mapping.items():
            if key in str_value:
                return basis
        return None

    def _normalize_phone(self, phone: str) -> str:
        digits = re.sub(r'\D', '', phone)
        if len(digits) == 11 and digits.startswith('8'):
            return '+7' + digits[1:]
        elif len(digits) == 11 and digits.startswith('7'):
            return '+' + digits
        return phone